"""Historical local-time -> UTC conversion using IANA tzdb rules.

Determinism: we force zoneinfo to read the pinned `tzdata` Python package (the
IANA database shipped as a wheel) instead of whatever the host OS has, so the
same input yields the same UTC instant on every machine. The tzdb version is
reported in every chart response.
"""
from __future__ import annotations

import re
import zoneinfo
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import swisseph as swe
import tzdata

from . import errors as E

# Use only the bundled tzdata package (never the host's /usr/share/zoneinfo).
zoneinfo.reset_tzpath(to=[])
TZDATA_VERSION = tzdata.IANA_VERSION

AMBIGUOUS_POLICIES = ("reject", "earlier", "later")
NONEXISTENT_POLICIES = ("reject", "shift_forward", "shift_backward")
LMT_POLICIES = ("birthplace", "zone")
CALENDARS = ("gregorian", "julian")
GREGORIAN_REFORM = (1582, 10, 15)

_DATE_RE = re.compile(r"^\s*(-?\d{1,4})-(\d{1,2})-(\d{1,2})\s*$")
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?\s*$")
_OFFSET_RE = re.compile(r"^\s*(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?(?::?(\d{2}))?\s*$", re.I)


def parse_date(s: str) -> tuple[int, int, int]:
    m = _DATE_RE.match(s or "")
    if not m:
        raise E.ChartError(E.INVALID_INPUT, f"Date must be YYYY-MM-DD, got {s!r}.")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def parse_time(s: str) -> tuple[int, int, float]:
    m = _TIME_RE.match(s or "")
    if not m:
        raise E.ChartError(E.INVALID_INPUT, f"Time must be HH:MM or HH:MM:SS (24h), got {s!r}.")
    h, mi = int(m.group(1)), int(m.group(2))
    sec = float(m.group(3)) if m.group(3) else 0.0
    if not (0 <= h <= 23 and 0 <= mi <= 59 and 0 <= sec < 60):
        raise E.ChartError(E.INVALID_INPUT, f"Time out of range: {s!r}.")
    return h, mi, sec


def parse_utc_offset(s: str) -> int:
    """'+03:00', '-0530', 'UTC+2' -> offset in seconds east of UTC."""
    m = _OFFSET_RE.match(s or "")
    if not m:
        raise E.ChartError(E.INVALID_INPUT, f"UTC offset must look like +03:00 or -05:30, got {s!r}.")
    sign = 1 if m.group(1) == "+" else -1
    h, mi, se = int(m.group(2)), int(m.group(3) or 0), int(m.group(4) or 0)
    if h > 15 or mi > 59 or se > 59:
        raise E.ChartError(E.INVALID_INPUT, f"UTC offset out of range: {s!r}.")
    return sign * (h * 3600 + mi * 60 + se)


def fmt_offset(seconds: float) -> str:
    sign = "+" if seconds >= 0 else "-"
    s = abs(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    out = f"{sign}{h:02d}:{m:02d}"
    return out + (f":{sec:02d}" if sec else "")


def get_zone(name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, TypeError):
        raise E.ChartError(E.UNKNOWN_TIMEZONE, f"Unknown IANA timezone {name!r}.")


def julian_to_gregorian(y: int, m: int, d: int) -> tuple[int, int, int]:
    jd = swe.julday(y, m, d, 12.0, swe.JUL_CAL)
    gy, gm, gd, _ = swe.revjul(jd, swe.GREG_CAL)
    return gy, gm, gd


def validate_civil_date(y: int, m: int, d: int, calendar: str) -> None:
    if calendar not in CALENDARS:
        raise E.ChartError(E.INVALID_INPUT, f"calendar must be one of {CALENDARS}.")
    # swe.date_conversion validates the day-of-month for the chosen calendar
    ok, _jd, _ = swe.date_conversion(y, m, d, 12.0, b"g" if calendar == "gregorian" else b"j")
    if not ok:
        raise E.ChartError(E.INVALID_INPUT, f"{y:04d}-{m:02d}-{d:02d} is not a valid {calendar} date.")


@dataclass
class TimeResolution:
    utc: datetime  # naive UTC wall time (proleptic Gregorian)
    jd_ut: float
    offset_seconds: float
    source: str  # "iana" | "manual_utc_offset" | "birthplace_lmt"
    tz_name: str | None = None
    tz_abbrev: str | None = None
    dst: bool | None = None
    dst_seconds: float | None = None
    ambiguity: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "utc": self.utc.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            "julian_day_ut": round(self.jd_ut, 8),
            "utc_offset": fmt_offset(self.offset_seconds),
            "utc_offset_seconds": round(self.offset_seconds, 3),
            "source": self.source,
            "timezone": self.tz_name,
            "abbreviation": self.tz_abbrev,
            "dst": self.dst,
            "dst_offset": fmt_offset(self.dst_seconds) if self.dst_seconds is not None else None,
            "ambiguity": self.ambiguity,
            "tzdata_version": TZDATA_VERSION if self.source != "manual_utc_offset" else None,
        }


def _jd_from_utc(utc: datetime) -> float:
    hour = utc.hour + utc.minute / 60 + (utc.second + utc.microsecond / 1e6) / 3600
    return swe.julday(utc.year, utc.month, utc.day, hour, swe.GREG_CAL)


def _round_trips(local: datetime, aware: datetime) -> bool:
    back = aware.astimezone(timezone.utc).astimezone(aware.tzinfo).replace(tzinfo=None)
    return back == local


def resolve_local_time(
    y: int, mo: int, d: int, h: int, mi: int, sec: float,
    *, calendar: str = "gregorian", tz_name: str | None = None, utc_offset: str | None = None,
    longitude: float | None = None, ambiguous: str = "reject", nonexistent: str = "reject",
    lmt: str = "birthplace",
) -> TimeResolution:
    """Convert a civil local date/time to UTC.

    Precedence: an explicit `utc_offset` overrides timezone rules entirely; else the
    IANA zone `tz_name` is applied with explicit ambiguity / gap policies.
    """
    if ambiguous not in AMBIGUOUS_POLICIES:
        raise E.ChartError(E.INVALID_INPUT, f"ambiguous_time must be one of {AMBIGUOUS_POLICIES}.")
    if nonexistent not in NONEXISTENT_POLICIES:
        raise E.ChartError(E.INVALID_INPUT, f"nonexistent_time must be one of {NONEXISTENT_POLICIES}.")
    if lmt not in LMT_POLICIES:
        raise E.ChartError(E.INVALID_INPUT, f"lmt must be one of {LMT_POLICIES}.")
    validate_civil_date(y, mo, d, calendar)
    warnings: list[str] = []

    gy, gm, gd = (y, mo, d) if calendar == "gregorian" else julian_to_gregorian(y, mo, d)
    if calendar == "gregorian" and (y, mo, d) < GREGORIAN_REFORM:
        warnings.append(
            "Date is before the Gregorian reform (1582-10-15) and is being read as a proleptic "
            "Gregorian date. If the source record is Julian (Old Style), set calendar='julian'."
        )
    whole = int(sec)
    micro = int(round((sec - whole) * 1e6))
    local = datetime(gy, gm, gd, h, mi, whole, min(micro, 999999))

    if utc_offset:
        off = parse_utc_offset(utc_offset)
        utc = local - timedelta(seconds=off)
        return TimeResolution(utc, _jd_from_utc(utc), off, "manual_utc_offset", tz_name=None,
                              warnings=warnings + ["Manual UTC offset used; timezone/DST rules were not applied."])

    if not tz_name:
        raise E.ChartError(E.INVALID_INPUT, "A timezone (IANA name) or a manual UTC offset is required.")
    zone = get_zone(tz_name)
    a0 = local.replace(tzinfo=zone, fold=0)
    a1 = local.replace(tzinfo=zone, fold=1)
    off0, off1 = a0.utcoffset(), a1.utcoffset()
    rt0, rt1 = _round_trips(local, a0), _round_trips(local, a1)
    ambiguity = None

    if off0 != off1 and rt0 and rt1:
        opts = {
            "earlier": {"utc_offset": fmt_offset(off0.total_seconds()), "abbreviation": a0.tzname(),
                        "utc": (local - off0).strftime("%Y-%m-%dT%H:%M:%SZ")},
            "later": {"utc_offset": fmt_offset(off1.total_seconds()), "abbreviation": a1.tzname(),
                      "utc": (local - off1).strftime("%Y-%m-%dT%H:%M:%SZ")},
        }
        if ambiguous == "reject":
            raise E.ChartError(E.AMBIGUOUS_LOCAL_TIME,
                               f"{local:%Y-%m-%d %H:%M} occurs twice in {tz_name} (clocks were set back). "
                               "Choose ambiguous_time='earlier' (first occurrence) or 'later' (second).",
                               {"options": opts, "timezone": tz_name})
        chosen = a0 if ambiguous == "earlier" else a1
        ambiguity = {"type": "ambiguous", "resolved_as": ambiguous, "options": opts}
        warnings.append(f"Ambiguous local time resolved as the {ambiguous} occurrence ({chosen.tzname()}).")
    elif not (rt0 and rt1):
        # Wall time falls in a gap (clocks were set forward) - it never existed.
        opts = {
            "shift_forward": {"utc_offset": fmt_offset(off0.total_seconds()),
                              "utc": (local - off0).strftime("%Y-%m-%dT%H:%M:%SZ")},
            "shift_backward": {"utc_offset": fmt_offset(off1.total_seconds()),
                               "utc": (local - off1).strftime("%Y-%m-%dT%H:%M:%SZ")},
        }
        if nonexistent == "reject":
            raise E.ChartError(E.NONEXISTENT_LOCAL_TIME,
                               f"{local:%Y-%m-%d %H:%M} did not exist in {tz_name} (clocks were set forward). "
                               "Check the record, or choose nonexistent_time='shift_forward' (read with the "
                               "pre-change offset) or 'shift_backward' (post-change offset).",
                               {"options": opts, "timezone": tz_name})
        chosen = a0 if nonexistent == "shift_forward" else a1
        ambiguity = {"type": "nonexistent", "resolved_as": nonexistent, "options": opts}
        warnings.append(f"Nonexistent local time resolved with policy {nonexistent}.")
    else:
        chosen = a0

    off = chosen.utcoffset().total_seconds()
    abbrev = chosen.tzname()
    dst_td = chosen.dst()

    if abbrev == "LMT":
        if longitude is not None and lmt == "birthplace":
            off = longitude * 240.0  # 4 minutes of time per degree of longitude
            utc = local - timedelta(seconds=off)
            warnings.append(
                f"{tz_name} had no standard time on this date (tzdb LMT). Using the local mean time of the "
                f"birthplace longitude ({fmt_offset(off)}); set lmt='zone' to use the zone's reference-city LMT."
            )
            return TimeResolution(utc, _jd_from_utc(utc), off, "birthplace_lmt", tz_name, "LMT", None, None,
                                  ambiguity, warnings)
        warnings.append(f"Using {tz_name}'s reference-city local mean time ({fmt_offset(off)}).")

    if gy < 1970:
        warnings.append("IANA tzdb coverage before 1970 is best-effort; verify the offset against a "
                        "historical record if the birth time is critical.")
    utc = (chosen - chosen.utcoffset()).replace(tzinfo=None)
    return TimeResolution(utc, _jd_from_utc(utc), off, "iana", tz_name, abbrev,
                          bool(dst_td) if dst_td is not None else None,
                          dst_td.total_seconds() if dst_td is not None else None, ambiguity, warnings)


def local_day_bounds(y: int, mo: int, d: int, **kw) -> tuple[TimeResolution, TimeResolution, TimeResolution]:
    """For unknown birth time: (start 00:00, noon 12:00, end 23:59:59) of the local civil day.

    Gaps/overlaps at day edges are resolved deterministically (forward / earliest-start,
    later-end) so the window always covers the whole civil day.
    """
    kw_start = dict(kw, ambiguous="earlier", nonexistent="shift_forward")
    kw_end = dict(kw, ambiguous="later", nonexistent="shift_backward")
    kw_noon = dict(kw, ambiguous="earlier", nonexistent="shift_forward")
    return (resolve_local_time(y, mo, d, 0, 0, 0.0, **kw_start),
            resolve_local_time(y, mo, d, 12, 0, 0.0, **kw_noon),
            resolve_local_time(y, mo, d, 23, 59, 59.0, **kw_end))
