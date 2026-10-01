"""Time conversion, error handling, settings and unknown-time behaviour."""
import os
import tempfile

import pytest
import swisseph as swe

from astrocalc import ChartError, build_chart
from astrocalc import engine
from astrocalc.formatting import format_lon, sign_of
from astrocalc.timeconv import resolve_local_time

CAIRO = {"place": "Cairo, Egypt", "latitude": "30°04′N", "longitude": "31°15′E"}


def code(exc_info):
    return exc_info.value.code


# ------------------------------------------------------------- required Cairo test case
def test_cairo_1987_historical_offset():
    r = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
    t = r["time"]
    # IANA tzdb 'Rule Egypt 1984 1988 May 1 1:00 -> Oct 1 3:00' => Egyptian summer time (UTC+3) in July 1987
    assert t["utc_offset"] == "+03:00" and t["abbreviation"] == "EEST" and t["dst"] is True
    assert t["utc"] == "1987-07-06T21:30:00Z"
    assert r["location"]["timezone"] == "Africa/Cairo"
    assert abs(r["location"]["latitude"] - 30.0666667) < 1e-6 and abs(r["location"]["longitude"] - 31.25) < 1e-9
    p = {x["id"]: x for x in r["points"]}
    assert p["sun"]["formatted"] == "14°16′ Cancer" and p["sun"]["house"] == 4
    assert p["moon"]["formatted"] == "15°32′ Scorpio"
    assert p["asc"]["formatted"] == "11°42′ Aries" and p["mc"]["formatted"] == "7°25′ Capricorn"
    assert p["mercury"]["motion"]["retrograde"] and p["saturn"]["motion"]["retrograde"]
    assert p["fortune"]["sect"] == "night"  # Sun in the 4th house at 00:30
    assert p["fortune"]["formula"] == "ASC + Sun − Moon"


def test_cairo_winter_is_plus2():
    r = build_chart({"date": "1987-01-07", "time": "00:30", **CAIRO})
    assert r["time"]["utc_offset"] == "+02:00" and r["time"]["dst"] is False


def test_cairo_spring_gap_is_rejected_then_resolvable():
    with pytest.raises(ChartError) as e:
        build_chart({"date": "1987-05-01", "time": "01:30", **CAIRO})
    assert code(e) == "NONEXISTENT_LOCAL_TIME"
    assert set(e.value.details["options"]) == {"shift_forward", "shift_backward"}
    r = build_chart({"date": "1987-05-01", "time": "01:30", "nonexistent_time": "shift_forward", **CAIRO})
    assert r["time"]["utc"] == "1987-04-30T23:30:00Z"


def test_cairo_autumn_overlap_is_ambiguous():
    with pytest.raises(ChartError) as e:
        build_chart({"date": "1987-10-01", "time": "02:30", **CAIRO})
    assert code(e) == "AMBIGUOUS_LOCAL_TIME"
    early = build_chart({"date": "1987-10-01", "time": "02:30", "ambiguous_time": "earlier", **CAIRO})
    late = build_chart({"date": "1987-10-01", "time": "02:30", "ambiguous_time": "later", **CAIRO})
    assert early["time"]["utc"] == "1987-09-30T23:30:00Z" and late["time"]["utc"] == "1987-10-01T00:30:00Z"


def test_new_york_dst_edges():
    with pytest.raises(ChartError) as e:
        resolve_local_time(2021, 11, 7, 1, 30, 0, tz_name="America/New_York")
    assert code(e) == "AMBIGUOUS_LOCAL_TIME"
    with pytest.raises(ChartError) as e:
        resolve_local_time(2021, 3, 14, 2, 30, 0, tz_name="America/New_York")
    assert code(e) == "NONEXISTENT_LOCAL_TIME"
    assert resolve_local_time(1990, 1, 15, 14, 45, 0, tz_name="America/New_York").offset_seconds == -5 * 3600


def test_lmt_uses_birthplace_longitude():
    t = resolve_local_time(1840, 3, 1, 12, 0, 0, tz_name="Europe/London", longitude=-0.1276)
    assert t.source == "birthplace_lmt" and abs(t.offset_seconds - (-0.1276 * 240)) < 1e-9
    z = resolve_local_time(1840, 3, 1, 12, 0, 0, tz_name="Europe/London", longitude=-0.1276, lmt="zone")
    assert z.tz_abbrev == "LMT" and z.offset_seconds == -75  # tzdb: London LMT -0:01:15


def test_manual_overrides():
    r = build_chart({"date": "1987-07-07", "time": "00:30", "latitude": 30.0667, "longitude": 31.25,
                     "utc_offset": "+02:00"})
    assert r["time"]["source"] == "manual_utc_offset" and r["time"]["utc"] == "1987-07-06T22:30:00Z"
    r = build_chart({"date": "1987-07-07", "time": "00:30", "latitude": 30.0667, "longitude": 31.25,
                     "timezone": "Africa/Cairo"})
    assert r["location"]["timezone_source"] == "manual" and r["time"]["utc_offset"] == "+03:00"
    with pytest.raises(ChartError) as e:
        build_chart({"date": "1987-07-07", "time": "00:30", "latitude": 30, "longitude": 31, "timezone": "Mars/Base"})
    assert code(e) == "UNKNOWN_TIMEZONE"


def test_julian_calendar():
    # 1600-01-01 Julian == 1600-01-11 Gregorian
    j = resolve_local_time(1600, 1, 1, 12, 0, 0, calendar="julian", utc_offset="+00:00")
    g = resolve_local_time(1600, 1, 11, 12, 0, 0, calendar="gregorian", utc_offset="+00:00")
    assert abs(j.jd_ut - g.jd_ut) < 1e-9


# ------------------------------------------------------------- explicit failures
def test_unsupported_dates():
    for d in ("1100-01-01", "3100-01-01"):
        with pytest.raises(ChartError) as e:
            build_chart({"date": d, "time": "12:00", "latitude": 0, "longitude": 0, "utc_offset": "+00:00"})
        assert code(e) == "UNSUPPORTED_DATE"


def test_invalid_inputs():
    for bad in ({"date": "1987-02-30", "time": "12:00"}, {"date": "1987-07-07", "time": "25:00"},
                {"date": "07/07/1987", "time": "12:00"}):
        with pytest.raises(ChartError) as e:
            build_chart({**bad, "latitude": 0, "longitude": 0, "utc_offset": "+00:00"})
        assert code(e) == "INVALID_INPUT"


def test_missing_ephemeris_file_is_explicit(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        real = engine.EPHE_PATH
        monkeypatch.setattr(engine, "EPHE_PATH", d)
        try:
            with pytest.raises(ChartError) as e:
                build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
            assert code(e) == "MISSING_EPHEMERIS"
        finally:
            monkeypatch.setattr(engine, "EPHE_PATH", real)
    assert build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})["points"][0]["id"] == "sun"


def test_polar_placidus_fails_explicitly_and_fallback_works():
    req = {"date": "1995-12-25", "time": "08:00", "place": "Tromso, Norway"}
    with pytest.raises(ChartError) as e:
        build_chart(req)
    assert code(e) == "HOUSE_SYSTEM_FAILED" and "porphyry" in e.value.details["fallback_options"]
    r = build_chart({**req, "settings": {"polar_fallback": "porphyry"}})
    assert r["houses"]["system"] == "porphyry" and any("polar_fallback" in w for w in r["warnings"])
    r = build_chart({**req, "settings": {"house_system": "whole_sign"}})
    assert r["houses"]["system"] == "whole_sign"


def test_sidereal_requires_explicit_ayanamsa():
    with pytest.raises(ChartError) as e:
        build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO, "settings": {"zodiac": "sidereal"}})
    assert code(e) == "AYANAMSA_REQUIRED"
    r = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO,
                     "settings": {"zodiac": "sidereal", "ayanamsa": "lahiri"}})
    assert r["ayanamsa"]["name"].lower().startswith("lahiri")
    trop = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
    diff = (trop["points"][0]["longitude"] - r["points"][0]["longitude"]) % 360
    assert abs(diff - r["ayanamsa"]["value"]) < 1e-6


# ------------------------------------------------------------- house systems
def test_whole_sign_and_equal_cusps():
    ws = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO, "settings": {"house_system": "whole_sign"}})
    assert [c["longitude"] for c in ws["houses"]["cusps"]] == [i * 30.0 for i in range(12)]  # ASC in Aries
    eq = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO, "settings": {"house_system": "equal"}})
    asc = next(p for p in eq["points"] if p["id"] == "asc")["longitude"]
    for i, c in enumerate(eq["houses"]["cusps"]):
        assert abs(((c["longitude"] - (asc + 30 * i)) + 180) % 360 - 180) < 1e-6


# ------------------------------------------------------------- unknown time
def test_unknown_time_omits_time_dependent_points():
    r = build_chart({"date": "1990-12-22", "time_unknown": True, "place": "New York, United States"})
    ids = {p["id"] for p in r["points"]}
    assert not ids & {"asc", "mc", "dsc", "ic", "vertex", "fortune"}
    assert r["houses"] is None and all("house" not in p for p in r["points"])
    assert "moon" in r["uncertainty"]["uncertain_points"]
    # Sun enters Capricorn 1990-12-22 03:07 UT (22:07 EST on the 21st) -> stays Capricorn all of local Dec 22
    assert "sun" not in r["uncertainty"]["uncertain_points"]
    r2 = build_chart({"date": "1990-12-21", "time_unknown": True, "place": "New York, United States"})
    assert "sun" in r2["uncertainty"]["uncertain_points"]
    assert r2["uncertainty"]["points"]["sun"]["signs"] == ["Sagittarius", "Capricorn"]
    assert all(a["a"] not in ("asc", "mc") and a["b"] not in ("asc", "mc") for a in r["aspects"])
    assert all(a["occurs"] in ("all_day", "part_of_day") for a in r["aspects"])


# ------------------------------------------------------------- motion, aspects, fortune
def test_stationary_threshold():
    # Mercury station retrograde 2023-04-21 ~08:35 UT
    r = build_chart({"date": "2023-04-21", "time": "08:35", "latitude": 51.5, "longitude": 0, "utc_offset": "+00:00"})
    merc = next(p for p in r["points"] if p["id"] == "mercury")
    assert merc["motion"]["stationary"] and merc["motion"]["status"].startswith("stationary")
    assert merc["motion"]["stationary_threshold_deg_per_day"] == 0.10


def test_aspect_status_and_orbs():
    r = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
    by = {(a["a"], a["b"]): a for a in r["aspects"]}
    st = by[("sun", "moon")]
    assert st["type"] == "trine" and st["status"] == "separating"  # Moon (faster) moving away from exact trine
    assert abs(st["orb"] - abs(st["separation"] - 120)) < 1e-9
    tight = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO,
                         "settings": {"orbs": {"conjunction": 1, "opposition": 1, "square": 1, "trine": 1,
                                               "sextile": 1}}})
    assert all(a["orb"] <= 1 for a in tight["aspects"]) and len(tight["aspects"]) < len(r["aspects"])


def test_fortune_day_and_night_formulas():
    night = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
    day = build_chart({"date": "1987-07-07", "time": "12:30", **CAIRO})
    p = lambda ch, k: next(x for x in ch["points"] if x["id"] == k)["longitude"]
    assert next(x for x in day["points"] if x["id"] == "fortune")["sect"] == "day"
    assert abs((p(day, "asc") + p(day, "moon") - p(day, "sun")) % 360 - p(day, "fortune")) < 1e-6
    assert abs((p(night, "asc") + p(night, "sun") - p(night, "moon")) % 360 - p(night, "fortune")) < 1e-6
    forced = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO, "settings": {"fortune": "day"}})
    assert abs((p(forced, "asc") + p(forced, "moon") - p(forced, "sun")) % 360 - p(forced, "fortune")) < 1e-6


def test_truncation_formatting():
    assert format_lon(13 + 25 / 60 + 59.9 / 3600) == "13°25′ Aries"
    assert sign_of(29.9999999)["sign"] == "Aries"
    assert sign_of(30.0)["sign"] == "Taurus"


def test_deterministic():
    a = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
    b = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
    assert a == b


def test_copyable_summaries():
    r = build_chart({"date": "1987-07-07", "time": "00:30", **CAIRO})
    s = r["summaries"]
    assert "Sun: 14°16′ Cancer, House 4" in s["placements"]
    assert "Mercury: 10°04′ Cancer R, House 4" in s["placements"]
    assert "Sun trine Moon — orb 1°15′, separating" in s["aspects"]
    assert s["full_text"].startswith("Natal chart")
