"""Request-level orchestration: input -> place -> UTC -> chart -> summaries."""
from __future__ import annotations

from typing import Any

from . import constants as C
from . import errors as E
from . import geo
from . import timeconv as T
from .aspects import find_aspects
from .engine import Settings, _LOCK, _bodies_at, ensure_thread_init, compute_chart, delta_t_seconds, library_info
from .formatting import format_lon, format_orb

API_VERSION = "1.0.0"


def _resolve_place(req: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    place = None
    if req.get("geonameid"):
        place = geo.get_place(int(req["geonameid"]))
    elif req.get("place"):
        res = geo.search_places(str(req["place"]), limit=5)
        warnings.extend(res["warnings"])
        if res["results"]:
            place = res["results"][0]
            if len(res["results"]) > 1:
                others = "; ".join(r["label"] for r in res["results"][1:4])
                warnings.append(f"Place query matched several places; using {place['label']} "
                                f"(largest/most relevant). Others: {others}. Pass geonameid to choose.")
        elif req.get("latitude") is None:
            raise E.ChartError(E.PLACE_NOT_FOUND, f"No place found for {req['place']!r}. Try 'City, Country' or "
                                                  "enter coordinates and timezone manually.")
    lat_o, lon_o = req.get("latitude"), req.get("longitude")
    if (lat_o is None) != (lon_o is None):
        raise E.ChartError(E.INVALID_INPUT, "Provide both latitude and longitude, or neither.")
    overridden = lat_o is not None
    lat = geo.parse_coord(lat_o, "lat") if overridden else (place["lat"] if place else None)
    lon = geo.parse_coord(lon_o, "lon") if overridden else (place["lon"] if place else None)

    tz_source = None
    tz = req.get("timezone") or None
    if tz:
        T.get_zone(tz)
        tz_source = "manual"
    elif req.get("utc_offset"):
        tz_source = "manual_utc_offset"
    elif overridden:
        tzinfo = geo.timezone_for(lat, lon)
        tz, tz_source = tzinfo["timezone"], tzinfo["backend"]
        if place and place.get("timezone") and place["timezone"] != tz:
            warnings.append(f"Manual coordinates fall in {tz}, not {place['timezone']} (the searched place).")
    elif place:
        tz, tz_source = place.get("timezone"), place["source"]
        if not tz:
            tzinfo = geo.timezone_for(lat, lon)
            tz, tz_source = tzinfo["timezone"], tzinfo["backend"]
    return {"name": place["label"] if place else req.get("place_label") or None,
            "geonameid": place["geonameid"] if place else None,
            "latitude": lat, "longitude": lon,
            "latitude_formatted": None if lat is None else _fmt_coord(lat, "NS"),
            "longitude_formatted": None if lon is None else _fmt_coord(lon, "EW"),
            "coordinates_source": "manual" if overridden else (place["source"] if place else None),
            "timezone": tz, "timezone_source": tz_source}


def _fmt_coord(v: float, hemis: str) -> str:
    h = hemis[0] if v >= 0 else hemis[1]
    total = round(abs(v) * 3600)
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{d}°{m:02d}′{s:02d}″{h}"


def _placement_line(p: dict[str, Any], time_known: bool, unc: dict[str, Any] | None = None) -> str:
    label = p["label"]
    if unc and unc.get("sign_changes"):
        pos = f"{unc['range_formatted']} (sign uncertain: {' / '.join(unc['signs'])})"
    elif unc and unc["id"] == "moon":
        pos = f"{p['formatted']} at noon (range {unc['range_formatted']})"
    else:
        pos = p["formatted"]
    flags = ""
    mot = p.get("motion") or {}
    if mot.get("stationary"):
        flags = " S" + ("R" if mot["retrograde"] else "D")
    elif mot.get("retrograde"):
        flags = " R"
    house = f", House {p['house']}" if time_known and p.get("house") else ""
    return f"{label}: {pos}{flags}{house}"


def _aspect_line(a: dict[str, Any]) -> str:
    st = f", {a['status']}" if a.get("status") else ""
    extra = ""
    if a.get("occurs") == "part_of_day":
        extra = " (only part of the day - depends on birth time)"
    return f"{a['a_label']} {a['label'].lower()} {a['b_label']} — orb {a['orb_formatted']}{st}{extra}"


def _unknown_time_analysis(y, mo, d, kw, settings: Settings) -> dict[str, Any]:
    start, noon, end = T.local_day_bounds(y, mo, d, **kw)
    steps = 24
    samples = [start.jd_ut + (end.jd_ut - start.jd_ut) * i / steps for i in range(steps + 1)]
    with _LOCK:
        import swisseph as swe
        ensure_thread_init()
        try:
            if settings.zodiac == "sidereal":
                swe.set_sid_mode(C.AYANAMSAS[settings.ayanamsa], 0, 0)
            snaps = [_bodies_at(jd, settings) for jd in samples]
        finally:
            swe.set_sid_mode(swe.SIDM_FAGAN_BRADLEY, 0, 0)
    ids = [p for p in settings.aspect_points if p not in C.TIME_DEPENDENT]
    per_point = {}
    for pid in snaps[0]:
        lons = [s[pid]["longitude"] for s in snaps]
        first, last = lons[0], lons[-1]
        signs = list(dict.fromkeys(s[pid]["sign"] for s in snaps))
        motions = list(dict.fromkeys(s[pid].get("motion", {}).get("status") for s in snaps))
        per_point[pid] = {
            "id": pid, "start": format_lon(first), "end": format_lon(last),
            "range_formatted": f"{format_lon(first)} – {format_lon(last)}",
            "span_deg": round(abs(((last - first + 180) % 360) - 180), 4),
            "signs": signs, "sign_changes": len(signs) > 1, "motion_changes": len(motions) > 1,
        }
    # Aspects across the day: hourly samples (Moon orb windows are >=10 h at a 5° orb, so none are missed)
    found: dict[tuple, list] = {}
    for s in snaps:
        for a in find_aspects(s, ids, settings.orbs):
            found.setdefault((a["a"], a["b"], a["type"]), []).append(a)
    return {"window": {"start": start.to_dict(), "noon": noon.to_dict(), "end": end.to_dict()},
            "points": per_point, "aspect_hits": found, "samples": len(samples), "noon_jd": noon.jd_ut,
            "noon_resolution": noon}


def build_chart(req: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    settings = Settings.from_dict(req.get("settings"))
    y, mo, d = T.parse_date(str(req.get("date", "")))
    calendar = (req.get("calendar") or "gregorian").lower()
    T.validate_civil_date(y, mo, d, calendar)
    gy = y if calendar == "gregorian" else T.julian_to_gregorian(y, mo, d)[0]
    lo, hi = C.SUPPORTED_YEARS
    if not lo <= gy <= hi:
        raise E.ChartError(E.UNSUPPORTED_DATE,
                           f"Year {gy} is outside the supported range {lo}–{hi} (bundled Swiss Ephemeris files "
                           "sepl/semo/seas _12, _18, _24). Add more .se1 files to extend it.",
                           {"supported_years": [lo, hi]})
    time_unknown = bool(req.get("time_unknown")) or not req.get("time")
    loc = _resolve_place(req, warnings)
    if not time_unknown and (loc["latitude"] is None or loc["longitude"] is None):
        raise E.ChartError(E.INVALID_INPUT, "Birthplace (or latitude/longitude) is required.")
    if not loc["timezone"] and not req.get("utc_offset"):
        raise E.ChartError(E.UNKNOWN_TIMEZONE, "Could not determine a timezone; provide timezone or utc_offset.")
    kw = dict(calendar=calendar, tz_name=loc["timezone"], utc_offset=req.get("utc_offset") or None,
              longitude=loc["longitude"], ambiguous=(req.get("ambiguous_time") or "reject"),
              nonexistent=(req.get("nonexistent_time") or "reject"), lmt=(req.get("lmt") or "birthplace"))

    uncertainty = None
    if time_unknown:
        ut = _unknown_time_analysis(y, mo, d, kw, settings)
        tres = ut["noon_resolution"]
        warnings.extend(tres.warnings)
        chart = compute_chart(jd_ut=tres.jd_ut, lat=loc["latitude"], lon=loc["longitude"], settings=settings,
                              time_known=False, warnings=warnings)
        # replace noon-only aspects with day-wide analysis
        aspects = []
        for (a, b, typ), hits in ut["aspect_hits"].items():
            noon_hit = next((h for h in chart["aspects"] if (h["a"], h["b"], h["type"]) == (a, b, typ)), None)
            base = dict(noon_hit or hits[len(hits) // 2])
            orbs_ = [h["orb"] for h in hits]
            base.update(occurs="all_day" if len(hits) == ut["samples"] else "part_of_day",
                        orb_range=[round(min(orbs_), 4), round(max(orbs_), 4)],
                        orb_range_formatted=f"{format_orb(min(orbs_))}–{format_orb(max(orbs_))}",
                        status=base["status"] if noon_hit else None, at_noon=noon_hit is not None)
            aspects.append(base)
        order = {p: i for i, p in enumerate(settings.aspect_points)}
        aspects.sort(key=lambda x: (order.get(x["a"], 99), order.get(x["b"], 99)))
        chart["aspects"] = aspects
        uncertain = [pid for pid, u in ut["points"].items() if u["sign_changes"] or pid == "moon"]
        uncertainty = {
            "note": "Birth time unknown: positions are computed for 12:00 local time. Houses, angles (ASC, MC, "
                    "DSC, IC), Vertex and Part of Fortune are omitted because they change roughly 1° every "
                    "4 minutes. Ranges below cover the whole local civil day.",
            "omitted": sorted(C.TIME_DEPENDENT) + ["house placements"],
            "uncertain_points": uncertain,
            "points": ut["points"], "day_window": ut["window"],
            "aspect_sampling": f"{ut['samples']} samples across the day (hourly)",
        }
        time_info = tres.to_dict()
        time_info["assumed_time"] = "12:00 (noon, time unknown)"
    else:
        h, mi, sec = T.parse_time(str(req["time"]))
        tres = T.resolve_local_time(y, mo, d, h, mi, sec, **kw)
        warnings.extend(tres.warnings)
        chart = compute_chart(jd_ut=tres.jd_ut, lat=loc["latitude"], lon=loc["longitude"], settings=settings,
                              time_known=True, warnings=warnings)
        time_info = tres.to_dict()

    points = chart["points"]
    order = [p for p in C.ALL_POINT_IDS if p in points]
    unc_pts = (uncertainty or {}).get("points", {})
    placement_lines = [_placement_line(points[p], not time_unknown, unc_pts.get(p)) for p in order]
    aspect_lines = [_aspect_line(a) for a in chart["aspects"]]
    header = [f"Natal chart — {req.get('date')} {'time unknown' if time_unknown else req.get('time')} "
              f"({calendar}), {loc['name'] or ''} {loc['latitude_formatted'] or ''} {loc['longitude_formatted'] or ''}".strip(),
              f"UTC {time_info['utc']} (offset {time_info['utc_offset']}"
              + (f", {time_info['abbreviation']}" if time_info.get("abbreviation") else "") + ")",
              f"Zodiac: {settings.zodiac}"
              + (f" ({chart['ayanamsa']['name']} {chart['ayanamsa']['formatted']})" if chart["ayanamsa"] else "")
              + (f"; Houses: {chart['houses']['system_label']}" if chart["houses"] else "; Houses: none (time unknown)")
              + f"; Node: {settings.node}; Lilith: {settings.lilith}"]
    house_lines = [f"House {c['house']}: {c['formatted']}" for c in chart["houses"]["cusps"]] if chart["houses"] else []
    summary_text = "\n".join(header + ["", "PLACEMENTS"] + placement_lines +
                             (["", "HOUSE CUSPS"] + house_lines if house_lines else []) +
                             ["", "ASPECTS"] + (aspect_lines or ["(none within orbs)"]))
    return {
        "api_version": API_VERSION,
        "input": {k: req.get(k) for k in ("date", "time", "time_unknown", "calendar", "place", "geonameid",
                                          "latitude", "longitude", "timezone", "utc_offset",
                                          "ambiguous_time", "nonexistent_time", "lmt")},
        "settings": settings.to_dict(),
        "location": loc,
        "time": time_info,
        "time_known": not time_unknown,
        "delta_t_seconds": round(delta_t_seconds(tres.jd_ut), 3),
        "points": [points[p] for p in order],
        "houses": chart["houses"],
        "aspects": chart["aspects"],
        "variants": chart["variants"],
        "ayanamsa": chart["ayanamsa"],
        "uncertainty": uncertainty,
        "summaries": {"placements": "\n".join(placement_lines), "aspects": "\n".join(aspect_lines),
                      "houses": "\n".join(house_lines), "full_text": summary_text},
        "engine": {**library_info(), "ephemeris_files_used": chart["ephemeris_files"],
                   "frame": "geocentric, apparent positions, ecliptic and equinox of date",
                   "time_scale": "UT (civil UTC treated as UT1; |UT1−UTC| < 0.9 s)"},
        "warnings": list(dict.fromkeys(warnings)),
    }
