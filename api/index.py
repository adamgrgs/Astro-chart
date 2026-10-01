"""HTTP API (FastAPI). Deployed as a single Vercel Python function; also runs under uvicorn/Docker.

Secrets (GEONAMES_USERNAME) are read from the server environment only and never sent to clients.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from astrocalc import API_VERSION, ChartError, build_chart  # noqa: E402
from astrocalc import constants as C  # noqa: E402
from astrocalc import geo  # noqa: E402
from astrocalc.engine import library_info  # noqa: E402

SOURCE_URL = os.environ.get("SOURCE_URL", "https://github.com/adamgrgs/Astro-chart")

app = FastAPI(title="Natal Chart Calculator API", version=API_VERSION,
              description="Deterministic natal chart calculations (Swiss Ephemeris, IANA tzdb, GeoNames). "
                          f"AGPL-3.0 - source: {SOURCE_URL}")


class ChartSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zodiac: Literal["tropical", "sidereal"] | None = None
    ayanamsa: str | None = Field(None, description=f"Required for sidereal. One of {sorted(C.AYANAMSAS)}")
    house_system: Literal[tuple(C.HOUSE_SYSTEMS)] | None = None  # type: ignore[valid-type]
    polar_fallback: Literal["none", "porphyry", "whole_sign", "equal"] | None = None
    node: Literal["true", "mean"] | None = None
    lilith: Literal["mean", "osculating", "interpolated"] | None = None
    fortune: Literal["sect", "day"] | None = None
    orbs: dict[str, float] | None = None
    aspect_points: list[str] | None = None
    stationary_thresholds: dict[str, float] | None = None


class ChartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str = Field(..., examples=["1987-07-07"], description="Local civil date YYYY-MM-DD")
    time: str | None = Field(None, examples=["00:30"], description="Local clock time HH:MM[:SS]; omit if unknown")
    time_unknown: bool = False
    calendar: Literal["gregorian", "julian"] = "gregorian"
    place: str | None = Field(None, examples=["Cairo, Egypt"], description="Place search text")
    geonameid: int | None = Field(None, description="Exact GeoNames id (from /api/places)")
    place_label: str | None = None
    latitude: float | str | None = Field(None, description="Override: decimal or DMS, e.g. 30°04′N")
    longitude: float | str | None = Field(None, description="Override: decimal or DMS, e.g. 31°15′E")
    timezone: str | None = Field(None, description="Override: IANA zone, e.g. Africa/Cairo")
    utc_offset: str | None = Field(None, description="Override: fixed offset, e.g. +03:00 (bypasses tz rules)")
    ambiguous_time: Literal["reject", "earlier", "later"] = "reject"
    nonexistent_time: Literal["reject", "shift_forward", "shift_backward"] = "reject"
    lmt: Literal["birthplace", "zone"] = "birthplace"
    settings: ChartSettingsIn | None = None


@app.exception_handler(ChartError)
async def chart_error_handler(_: Request, exc: ChartError):
    return JSONResponse(status_code=exc.status, content=exc.to_dict())


@app.post("/api/chart")
def chart(req: ChartRequest) -> dict[str, Any]:
    data = req.model_dump()
    data["settings"] = req.settings.model_dump(exclude_none=True) if req.settings else {}
    return build_chart(data)


@app.get("/api/places")
def places(q: str = Query(..., min_length=2, max_length=120), limit: int = Query(8, ge=1, le=20)):
    return geo.search_places(q, limit)


@app.get("/api/timezone")
def timezone(lat: str, lon: str):
    la, lo = geo.parse_coord(lat, "lat"), geo.parse_coord(lon, "lon")
    return {"latitude": la, "longitude": lo, **geo.timezone_for(la, lo)}


@app.get("/api/meta")
def meta():
    return {
        "api_version": API_VERSION, "source": SOURCE_URL, **library_info(),
        "geocoder": "geonames_api" if geo.geonames_username() else "geonames_offline_cities5000",
        "options": {
            "house_systems": C.HOUSE_LABELS, "ayanamsas": sorted(C.AYANAMSAS),
            "node": ["true", "mean"], "lilith": ["mean", "osculating", "interpolated"],
            "fortune": {"sect": "Day: ASC + Moon − Sun; Night: ASC + Sun − Moon", "day": "Always ASC + Moon − Sun"},
            "aspects": {k: {"label": v[0], "angle": v[1]} for k, v in C.ASPECTS.items()},
            "default_orbs": C.DEFAULT_ORBS, "default_aspect_points": C.DEFAULT_ASPECT_POINTS,
            "points": C.POINT_LABELS, "stationary_thresholds_deg_per_day": C.STATIONARY_THRESHOLDS,
        },
        "attribution": ["Swiss Ephemeris © Astrodienst AG (AGPL-3.0)", "Place data © GeoNames (CC BY 4.0)",
                        "IANA Time Zone Database (public domain)"],
    }


@app.get("/api/health")
def health():
    info = library_info()
    ok = info["ephemeris_path_ok"]
    return JSONResponse(status_code=200 if ok else 503, content={"ok": ok, **info})


@app.get("/")
def index():
    return FileResponse(os.path.join(ROOT, "web", "index.html"), media_type="text/html")
