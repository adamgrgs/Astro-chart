"""Natal chart engine - Swiss Ephemeris (pyswisseph) only. No estimation, no LLM.

All positions are geocentric, apparent, ecliptic-of-date longitudes computed by the
Swiss Ephemeris from its compressed JPL-based data files (./ephe). If a data file
is missing for the requested date the engine raises MISSING_EPHEMERIS rather than
silently falling back to the lower-precision built-in Moshier model.
"""
from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass, field
from typing import Any

import swisseph as swe

from . import constants as C
from . import errors as E
from . import timeconv as T
from .aspects import find_aspects
from .formatting import format_lon, sign_of

EPHE_PATH = os.environ.get("SE_EPHE_PATH") or os.path.join(os.path.dirname(__file__), "..", "ephe")
EPHE_PATH = os.path.abspath(EPHE_PATH)
swe.set_ephe_path(EPHE_PATH)

# The Swiss Ephemeris keeps its state (ephemeris path, sidereal mode, open files) in
# thread-local storage, so every worker thread must set the path itself; calls are
# additionally serialised so per-request settings can never leak between requests.
_LOCK = threading.RLock()
_TLS = threading.local()


def ensure_thread_init() -> None:
    if getattr(_TLS, "path", None) != EPHE_PATH:
        swe.set_ephe_path(EPHE_PATH)
        _TLS.path = EPHE_PATH


# ------------------------------------------------------------------ settings
@dataclass
class Settings:
    zodiac: str = "tropical"
    ayanamsa: str | None = None
    house_system: str = "placidus"
    polar_fallback: str = "none"  # none | porphyry | whole_sign | equal
    node: str = "true"
    lilith: str = "mean"
    fortune: str = "sect"  # sect (day/night) | day (always day formula)
    orbs: dict[str, float] = field(default_factory=lambda: dict(C.DEFAULT_ORBS))
    aspect_points: list[str] = field(default_factory=lambda: list(C.DEFAULT_ASPECT_POINTS))
    stationary_thresholds: dict[str, float] = field(default_factory=lambda: dict(C.STATIONARY_THRESHOLDS))

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Settings":
        d = dict(d or {})
        s = cls()
        for k in ("zodiac", "ayanamsa", "house_system", "polar_fallback", "node", "lilith", "fortune"):
            if d.get(k) is not None:
                setattr(s, k, str(d[k]).lower())
        if d.get("orbs"):
            for k, v in d["orbs"].items():
                if k not in C.ASPECTS:
                    raise E.ChartError(E.INVALID_INPUT, f"Unknown aspect {k!r} in orbs.")
                v = float(v)
                if not 0 <= v <= 30:
                    raise E.ChartError(E.INVALID_INPUT, f"Orb for {k} must be between 0 and 30 degrees.")
                s.orbs[k] = v
        if d.get("aspect_points"):
            bad = [p for p in d["aspect_points"] if p not in C.ALL_POINT_IDS]
            if bad:
                raise E.ChartError(E.INVALID_INPUT, f"Unknown aspect points {bad}.")
            s.aspect_points = list(dict.fromkeys(d["aspect_points"]))
        if d.get("stationary_thresholds"):
            for k, v in d["stationary_thresholds"].items():
                if k not in C.STATIONARY_THRESHOLDS:
                    raise E.ChartError(E.INVALID_INPUT, f"No stationary threshold applies to {k!r}.")
                s.stationary_thresholds[k] = abs(float(v))
        s.validate()
        return s

    def validate(self) -> None:
        def need(val, allowed, name):
            if val not in allowed:
                raise E.ChartError(E.INVALID_INPUT, f"{name} must be one of {sorted(allowed)}; got {val!r}.")
        need(self.zodiac, {"tropical", "sidereal"}, "zodiac")
        need(self.house_system, set(C.HOUSE_SYSTEMS), "house_system")
        need(self.polar_fallback, {"none", "porphyry", "whole_sign", "equal"}, "polar_fallback")
        need(self.node, set(C.NODE_VARIANTS), "node")
        need(self.lilith, set(C.LILITH_VARIANTS), "lilith")
        need(self.fortune, {"sect", "day"}, "fortune")
        if self.zodiac == "sidereal":
            if not self.ayanamsa:
                raise E.ChartError(E.AYANAMSA_REQUIRED, "Sidereal zodiac requires an explicit ayanamsa.",
                                   {"options": sorted(C.AYANAMSAS)})
            need(self.ayanamsa, set(C.AYANAMSAS), "ayanamsa")
        elif self.ayanamsa:
            raise E.ChartError(E.INVALID_INPUT, "ayanamsa is only valid with zodiac='sidereal'.")

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# ------------------------------------------------------------------ low level
def _flags(settings: Settings) -> int:
    f = swe.FLG_SWIEPH | swe.FLG_SPEED
    if settings.zodiac == "sidereal":
        f |= swe.FLG_SIDEREAL
    return f


def _calc(jd: float, body: int, flags: int, label: str) -> tuple[tuple[float, ...], int]:
    try:
        xx, ret = swe.calc_ut(jd, body, flags)
    except swe.Error as exc:
        msg = str(exc)
        if "not found" in msg:
            raise E.ChartError(E.MISSING_EPHEMERIS, f"Ephemeris data for {label} is not available for this date: {msg}",
                               {"ephe_path": "ephe/", "body": label}, status=500)
        raise E.ChartError(E.EPHEMERIS_ERROR, f"Swiss Ephemeris error for {label}: {msg}", status=500)
    if body not in (swe.MEAN_NODE, swe.MEAN_APOG) and not (ret & swe.FLG_SWIEPH):
        # SE fell back to the Moshier model because the data file was missing.
        raise E.ChartError(E.MISSING_EPHEMERIS,
                           f"Swiss Ephemeris data file for {label} is missing for this date (would have fallen back "
                           "to the lower-precision Moshier model). Install the matching .se1 files in ephe/.",
                           {"body": label}, status=500)
    return xx, ret


def _motion(pid: str, speed: float, thresholds: dict[str, float]) -> dict[str, Any]:
    retro = speed < 0
    thr = thresholds.get(pid)
    stationary = thr is not None and abs(speed) < thr
    if stationary:
        status = "stationary_retrograde" if retro else "stationary_direct"
    else:
        status = "retrograde" if retro else "direct"
    return {"retrograde": retro, "stationary": stationary, "status": status,
            "stationary_threshold_deg_per_day": thr}


def _point(pid: str, lon: float, lat: float | None, speed: float | None, decl: float | None = None,
           motion: dict[str, Any] | None = None, **extra) -> dict[str, Any]:
    lon = lon % 360.0
    p = {"id": pid, "label": C.POINT_LABELS[pid], "longitude": round(lon, 7), **sign_of(lon),
         "formatted": format_lon(lon), "latitude": None if lat is None else round(lat, 7),
         "declination": None if decl is None else round(decl, 7),
         "speed_deg_per_day": None if speed is None else round(speed, 7)}
    if motion:
        p["motion"] = motion
    p.update(extra)
    return p


def _house_of(lon: float, cusps: list[float]) -> int:
    lon %= 360.0
    for i in range(12):
        a, b = cusps[i], cusps[(i + 1) % 12]
        span = (b - a) % 360.0
        if (lon - a) % 360.0 < span or (span == 0 and lon == a):
            return i + 1
    return 12  # unreachable for valid cusps


def _houses(jd: float, lat: float, lon: float, settings: Settings, warnings: list[str]):
    hs = settings.house_system
    flags = swe.FLG_SIDEREAL if settings.zodiac == "sidereal" else 0
    if hs in C.POLAR_SENSITIVE and abs(lat) >= 66.0:
        # Placidus/Koch are undefined where some ecliptic degrees never rise or set.
        eps = swe.calc_ut(jd, swe.ECL_NUT, 0)[0][0]
        if abs(lat) > 90.0 - eps:
            if settings.polar_fallback == "none":
                raise E.ChartError(
                    E.HOUSE_SYSTEM_FAILED,
                    f"{C.HOUSE_LABELS[hs]} houses cannot be computed at latitude {lat:.4f}° (inside the polar "
                    f"circle, |lat| > 90° − obliquity = {90 - eps:.4f}°). Choose another house system or set "
                    "polar_fallback to porphyry, whole_sign or equal.",
                    {"latitude": lat, "polar_limit": round(90 - eps, 6), "house_system": hs,
                     "fallback_options": ["porphyry", "whole_sign", "equal"]})
            warnings.append(f"{C.HOUSE_LABELS[hs]} is undefined at this latitude; houses use "
                            f"{C.HOUSE_LABELS[settings.polar_fallback]} (polar_fallback).")
            hs = settings.polar_fallback
    try:
        cusps, ascmc, cusp_speed, ascmc_speed = swe.houses_ex2(jd, lat, lon, C.HOUSE_SYSTEMS[hs], flags)
    except swe.Error as exc:
        raise E.ChartError(E.HOUSE_SYSTEM_FAILED, f"House calculation failed ({C.HOUSE_LABELS[hs]}): {exc}",
                           {"latitude": lat, "house_system": hs})
    return hs, list(cusps[:12]), list(ascmc), list(cusp_speed[:12]), list(ascmc_speed)


def _ephemeris_files() -> list[dict[str, Any]]:
    out = []
    for ifno, kind in ((0, "planets"), (1, "moon"), (2, "asteroids")):
        try:
            path, start, end, denum = swe.get_current_file_data(ifno)
        except Exception:
            continue
        if path:
            out.append({"type": kind, "file": os.path.basename(path), "jpl_de": denum,
                        "start_jd": round(start, 1), "end_jd": round(end, 1)})
    return out


# ------------------------------------------------------------------ core computation
def _bodies_at(jd: float, settings: Settings) -> dict[str, dict[str, Any]]:
    """Time-independent-of-location points at a JD (planets, Chiron, nodes, Lilith)."""
    flags = _flags(settings)
    eq = flags | swe.FLG_EQUATORIAL
    out: dict[str, dict[str, Any]] = {}
    for pid, (label, body) in C.PLANETS.items():
        xx, _ = _calc(jd, body, flags, label)
        dec = _calc(jd, body, eq, label)[0][1]
        mot = _motion(pid, xx[3], settings.stationary_thresholds) if pid not in ("sun", "moon") else \
            {"retrograde": False, "stationary": False, "status": "direct", "stationary_threshold_deg_per_day": None}
        out[pid] = _point(pid, xx[0], xx[1], xx[3], dec, mot)
    node_body = C.NODE_VARIANTS[settings.node]
    xx, _ = _calc(jd, node_body, flags, "Lunar node")
    dec = _calc(jd, node_body, eq, "Lunar node")[0][1]
    nm = _motion("north_node", xx[3], {})
    out["north_node"] = _point("north_node", xx[0], xx[1], xx[3], dec, nm, variant=settings.node)
    out["south_node"] = _point("south_node", xx[0] + 180.0, -xx[1], xx[3], -dec, nm, variant=settings.node)
    lil_body = C.LILITH_VARIANTS[settings.lilith]
    xx, _ = _calc(jd, lil_body, flags, "Lilith")
    dec = _calc(jd, lil_body, eq, "Lilith")[0][1]
    out["lilith"] = _point("lilith", xx[0], xx[1], xx[3], dec, _motion("lilith", xx[3], {}), variant=settings.lilith)
    return out


def _variants(jd: float, settings: Settings) -> dict[str, Any]:
    flags = _flags(settings)
    nodes = {k: format_lon(_calc(jd, b, flags, "node")[0][0]) for k, b in C.NODE_VARIANTS.items()}
    nodes_lon = {k: round(_calc(jd, b, flags, "node")[0][0], 7) for k, b in C.NODE_VARIANTS.items()}
    lil = {k: round(_calc(jd, b, flags, "lilith")[0][0], 7) for k, b in C.LILITH_VARIANTS.items()}
    return {
        "north_node": {k: {"longitude": nodes_lon[k], "formatted": nodes[k]} for k in nodes},
        "lilith": {k: {"longitude": v, "formatted": format_lon(v)} for k, v in lil.items()},
    }


def compute_chart(*, jd_ut: float, lat: float | None, lon: float | None, settings: Settings,
                  time_known: bool = True, warnings: list[str] | None = None) -> dict[str, Any]:
    """Compute a chart at a UT Julian day. If time_known is False, angles/houses are omitted."""
    warnings = warnings if warnings is not None else []
    with _LOCK:
        ensure_thread_init()
        if settings.zodiac == "sidereal":
            swe.set_sid_mode(C.AYANAMSAS[settings.ayanamsa], 0, 0)
        try:
            points = _bodies_at(jd_ut, settings)
            houses = None
            if time_known:
                if lat is None or lon is None:
                    raise E.ChartError(E.INVALID_INPUT, "Coordinates are required for houses and angles.")
                hs_used, cusps, ascmc, cusp_speed, ascmc_speed = _houses(jd_ut, lat, lon, settings, warnings)
                asc, mc, armc, vertex = ascmc[0], ascmc[1], ascmc[2], ascmc[3]
                a_sp, m_sp, v_sp = ascmc_speed[0], ascmc_speed[1], ascmc_speed[3]
                points["asc"] = _point("asc", asc, None, a_sp)
                points["mc"] = _point("mc", mc, None, m_sp)
                points["dsc"] = _point("dsc", asc + 180, None, a_sp)
                points["ic"] = _point("ic", mc + 180, None, m_sp)
                points["vertex"] = _point("vertex", vertex, None, v_sp)
                # Sect: Sun above the horizon <=> its ecliptic longitude lies in the DSC->MC->ASC half.
                sun, moon = points["sun"]["longitude"], points["moon"]["longitude"]
                sun_alt = swe.azalt(jd_ut, swe.ECL2HOR, (lon, lat, 0), 0, 0,
                                    (swe.calc_ut(jd_ut, swe.SUN, swe.FLG_SWIEPH)[0][0],
                                     swe.calc_ut(jd_ut, swe.SUN, swe.FLG_SWIEPH)[0][1], 1))[1]
                is_day = ((sun - asc) % 360.0) >= 180.0
                use_day = is_day or settings.fortune == "day"
                if use_day:
                    pof = asc + moon - sun
                    pof_sp = a_sp + points["moon"]["speed_deg_per_day"] - points["sun"]["speed_deg_per_day"]
                    formula = "ASC + Moon − Sun"
                else:
                    pof = asc + sun - moon
                    pof_sp = a_sp + points["sun"]["speed_deg_per_day"] - points["moon"]["speed_deg_per_day"]
                    formula = "ASC + Sun − Moon"
                points["fortune"] = _point("fortune", pof, None, pof_sp, formula=formula,
                                           sect="day" if is_day else "night", fortune_mode=settings.fortune)
                if (is_day and sun_alt < 0) or (not is_day and sun_alt > 0):
                    warnings.append(f"Sun is within the ecliptic/horizon edge case (true altitude {sun_alt:.2f}°); "
                                    "sect uses the ecliptic ASC/DSC criterion.")
                for pid, p in points.items():
                    if pid in ("asc", "dsc"):
                        p["house"] = 1 if pid == "asc" else 7
                    else:
                        p["house"] = _house_of(p["longitude"], cusps)
                houses = {
                    "system": hs_used, "system_label": C.HOUSE_LABELS[hs_used],
                    "requested_system": settings.house_system,
                    "cusps": [{"house": i + 1, "longitude": round(c % 360, 7), **sign_of(c % 360),
                               "formatted": format_lon(c % 360)} for i, c in enumerate(cusps)],
                    "armc": round(armc, 7), "sun_altitude_deg": round(sun_alt, 4),
                    "sect": "day" if is_day else "night",
                }
            # "true" ayanamsa (includes nutation) is the value subtracted from apparent tropical positions;
            # it matches what swetest prints. The mean value (no nutation) is reported alongside.
            ayan = swe.get_ayanamsa_ex_ut(jd_ut, swe.FLG_SWIEPH)[1] if settings.zodiac == "sidereal" else None
            ayan_mean = swe.get_ayanamsa_ex_ut(jd_ut, swe.FLG_SWIEPH | swe.FLG_NONUT)[1] if ayan is not None else None
            ayan_name = swe.get_ayanamsa_name(C.AYANAMSAS[settings.ayanamsa]) if ayan is not None else None
            variants = _variants(jd_ut, settings)
            files = _ephemeris_files()
        finally:
            if settings.zodiac == "sidereal":
                swe.set_sid_mode(swe.SIDM_FAGAN_BRADLEY, 0, 0)  # reset global state to the library default
    aspect_ids = [p for p in settings.aspect_points if p in points]
    aspects = find_aspects(points, aspect_ids, settings.orbs)
    return {
        "points": points, "houses": houses, "aspects": aspects, "variants": variants,
        "ayanamsa": None if ayan is None else {"id": settings.ayanamsa, "name": ayan_name, "value": round(ayan, 7),
                                              "formatted": format_lon(ayan, with_sign=False),
                                              "mean_value": round(ayan_mean, 7),
                                              "note": "value includes nutation (true ayanamsa); mean_value excludes it"},
        "ephemeris_files": files, "warnings": warnings,
    }


def delta_t_seconds(jd_ut: float) -> float:
    with _LOCK:
        ensure_thread_init()
        return swe.deltat_ex(jd_ut, swe.FLG_SWIEPH) * 86400.0


def library_info() -> dict[str, Any]:
    present = sorted(f for f in os.listdir(EPHE_PATH) if f.endswith(".se1")) if os.path.isdir(EPHE_PATH) else []
    return {"swisseph_version": swe.version, "pyswisseph": getattr(swe, "__version__", None),
            "ephemeris_path_ok": bool(present), "ephemeris_files_present": present,
            "tzdata_version": T.TZDATA_VERSION, "supported_years": list(C.SUPPORTED_YEARS)}
