"""Birthplace resolution: place search, coordinates, and IANA timezone identification.

Two backends, chosen explicitly and reported in every response:
  * GeoNames web services (https://www.geonames.org) when the GEONAMES_USERNAME
    environment variable is set (server-side only - never sent to the browser).
  * Offline fallback: a bundled index of the GeoNames `cities5000` dump (every
    place with population >= 5000, ~70k rows, CC BY 4.0) plus `timezonefinder`
    for coordinate -> timezone lookups.
"""
from __future__ import annotations

import csv
import functools
import gzip
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from typing import Any

from . import errors as E

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "places.tsv.gz")
GEONAMES_BASE = os.environ.get("GEONAMES_BASE_URL", "https://secure.geonames.org")
TIMEOUT = float(os.environ.get("GEONAMES_TIMEOUT", "6"))


def geonames_username() -> str | None:
    u = os.environ.get("GEONAMES_USERNAME", "").strip()
    return u or None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


# ---------------------------------------------------------------- coordinates
_DMS_RE = re.compile(
    r"^\s*(?P<deg>\d{1,3}(?:\.\d+)?)\s*[°d:\s]?\s*(?P<h1>[NSEWnsew])?\s*(?:(?P<min>\d{1,2}(?:\.\d+)?)\s*['′m:\s]?\s*)?"
    r"(?:(?P<sec>\d{1,2}(?:\.\d+)?)\s*[\"″s]?\s*)?(?P<h2>[NSEWnsew])?\s*$"
)


def parse_coord(value: Any, kind: str) -> float:
    """Parse a latitude/longitude given as a number or DMS text ('30°04′N', '30N04', '31 15 E')."""
    limit = 90 if kind == "lat" else 180
    if isinstance(value, (int, float)):
        v = float(value)
    else:
        s = str(value).strip()
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
            v = float(s)
        else:
            m = _DMS_RE.match(s)
            if not m or (m.group("h1") and m.group("h2")):
                raise E.ChartError(E.INVALID_INPUT, f"Cannot parse {kind} {value!r}. Use decimal degrees or e.g. 30°04′N.")
            v = float(m.group("deg")) + float(m.group("min") or 0) / 60 + float(m.group("sec") or 0) / 3600
            hemi = (m.group("h1") or m.group("h2") or "").upper()
            if hemi:
                if (kind == "lat" and hemi not in "NS") or (kind == "lon" and hemi not in "EW"):
                    raise E.ChartError(E.INVALID_INPUT, f"Hemisphere {hemi!r} is not valid for {kind}.")
                if hemi in "SW":
                    v = -v
    if not -limit <= v <= limit:
        raise E.ChartError(E.INVALID_INPUT, f"{kind} {v} out of range ±{limit}.")
    return v


# ---------------------------------------------------------------- offline index
@functools.lru_cache(maxsize=1)
def _index() -> list[dict[str, Any]]:
    if not os.path.exists(DATA_FILE):
        raise E.ChartError(E.GEOCODER_UNAVAILABLE, "Offline place index missing (data/places.tsv.gz).", status=503)
    rows = []
    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            alts = [a for a in r["alternates"].split("|") if a]
            rows.append({
                "geonameid": int(r["geonameid"]), "name": r["name"], "country_code": r["country_code"],
                "country": r["country"], "admin1": r["admin1"], "lat": float(r["lat"]), "lon": float(r["lon"]),
                "timezone": r["timezone"], "population": int(r["population"]),
                "_n": _norm(r["name"]), "_a": _norm(r["asciiname"]), "_alts": [_norm(a) for a in alts],
                "_q": " ".join(filter(None, (_norm(r["admin1"]), _norm(r["country"]), r["country_code"].lower()))),
            })
    return rows


def _public(r: dict[str, Any], source: str) -> dict[str, Any]:
    out = {k: v for k, v in r.items() if not k.startswith("_")}
    parts = [out["name"]]
    for x in (out.get("admin1"), out.get("country")):
        if x and x not in parts:
            parts.append(x)
    label = ", ".join(parts)
    out.update(label=label, source=source)
    return out


def search_offline(query: str, limit: int = 10) -> list[dict[str, Any]]:
    parts = [p for p in (x.strip() for x in query.split(",")) if p]
    if not parts:
        return []
    name_q = _norm(parts[0])
    quals = [_norm(p) for p in parts[1:]]
    scored = []
    for r in _index():
        if name_q in (r["_n"], r["_a"]):
            s = 0
        elif name_q in r["_alts"]:
            s = 1
        elif r["_n"].startswith(name_q) or r["_a"].startswith(name_q):
            s = 2
        elif any(a.startswith(name_q) for a in r["_alts"]):
            s = 3
        else:
            continue
        if quals and not all(q and q in r["_q"] for q in quals):
            continue
        scored.append((s, -r["population"], r))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [_public(r, "geonames_offline_cities5000") for _, _, r in scored[:limit]]


def get_offline(geonameid: int) -> dict[str, Any] | None:
    for r in _index():
        if r["geonameid"] == geonameid:
            return _public(r, "geonames_offline_cities5000")
    return None


# ---------------------------------------------------------------- GeoNames web service
def _geonames_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    user = geonames_username()
    if not user:
        raise E.ChartError(E.GEOCODER_UNAVAILABLE, "GEONAMES_USERNAME is not configured.", status=503)
    url = f"{GEONAMES_BASE}/{path}?" + urllib.parse.urlencode({**params, "username": user})
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:  # network / HTTP failure
        raise E.ChartError(E.GEOCODER_UNAVAILABLE, f"GeoNames request failed: {type(exc).__name__}", status=503)
    if "status" in data:  # GeoNames reports errors in-band (e.g. credit limits, bad user)
        st = data["status"]
        raise E.ChartError(E.GEOCODER_UNAVAILABLE, f"GeoNames error {st.get('value')}: {st.get('message')}",
                           {"geonames_status": st.get("value")}, status=503)
    return data


def search_geonames(query: str, limit: int = 10) -> list[dict[str, Any]]:
    data = _geonames_get("searchJSON", {"q": query, "maxRows": limit, "featureClass": "P",
                                        "style": "FULL", "orderby": "relevance"})
    out = []
    for g in data.get("geonames", []):
        tz = (g.get("timezone") or {}).get("timeZoneId")
        r = {"geonameid": g.get("geonameId"), "name": g.get("name"), "country_code": g.get("countryCode"),
             "country": g.get("countryName"), "admin1": g.get("adminName1", ""), "lat": float(g["lat"]),
             "lon": float(g["lng"]), "timezone": tz, "population": int(g.get("population") or 0)}
        out.append(_public(r, "geonames_api"))
    return out


def get_geonames(geonameid: int) -> dict[str, Any]:
    g = _geonames_get("getJSON", {"geonameId": geonameid, "style": "FULL"})
    r = {"geonameid": g.get("geonameId"), "name": g.get("name"), "country_code": g.get("countryCode"),
         "country": g.get("countryName"), "admin1": g.get("adminName1", ""), "lat": float(g["lat"]),
         "lon": float(g["lng"]), "timezone": (g.get("timezone") or {}).get("timeZoneId"),
         "population": int(g.get("population") or 0)}
    return _public(r, "geonames_api")


# ---------------------------------------------------------------- public API
def search_places(query: str, limit: int = 10) -> dict[str, Any]:
    """Search places; returns {'results': [...], 'backend': ..., 'warnings': [...]}."""
    warnings: list[str] = []
    if geonames_username():
        try:
            return {"results": search_geonames(query, limit), "backend": "geonames_api", "warnings": warnings}
        except E.ChartError as exc:
            warnings.append(f"{exc.message} Fell back to the offline GeoNames index.")
    return {"results": search_offline(query, limit), "backend": "geonames_offline_cities5000", "warnings": warnings}


def get_place(geonameid: int) -> dict[str, Any]:
    if geonames_username():
        try:
            return get_geonames(geonameid)
        except E.ChartError:
            pass
    r = get_offline(geonameid)
    if not r:
        raise E.ChartError(E.PLACE_NOT_FOUND, f"GeoNames id {geonameid} not found.")
    return r


@functools.lru_cache(maxsize=1)
def _tzf():
    from timezonefinder import TimezoneFinder
    return TimezoneFinder()


def timezone_for(lat: float, lon: float) -> dict[str, Any]:
    """Identify the IANA zone for coordinates."""
    if geonames_username():
        try:
            d = _geonames_get("timezoneJSON", {"lat": lat, "lng": lon})
            if d.get("timezoneId"):
                return {"timezone": d["timezoneId"], "backend": "geonames_api"}
        except E.ChartError:
            pass
    tz = _tzf().timezone_at(lat=lat, lng=lon)
    if not tz:
        raise E.ChartError(E.UNKNOWN_TIMEZONE, f"No timezone found for {lat}, {lon}. Provide timezone or utc_offset.")
    return {"timezone": tz, "backend": "timezonefinder"}
