"""Positions vs Astrodienst's swetest (the Swiss Ephemeris reference program) with matching settings."""
import json, os

import pytest
import swisseph as swe

from astrocalc.engine import Settings, compute_chart

FIX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "swetest_reference.json")))
HSYS = {"P": "placidus", "W": "whole_sign", "A": "equal", "K": "koch", "O": "porphyry", "R": "regiomontanus",
        "C": "campanus"}
SID = {1: "lahiri", 0: "fagan_bradley"}
TOL_DEG = 1.0 / 3600 / 10  # 0.1 arcsecond
TOL_SPEED = 1e-5          # deg/day


def angdiff(a, b):
    return abs(((a - b + 180) % 360) - 180)


def run_case(c):
    d, m, y = (int(x) for x in c["ut_date"].split("."))
    hh, mm, ss = (int(x) for x in c["ut_time"].split(":"))
    jd = swe.julday(y, m, d, hh + mm / 60 + ss / 3600)
    s = Settings.from_dict({"house_system": HSYS[c["hsys"]],
                            **({"zodiac": "sidereal", "ayanamsa": SID[c["sid"]]} if c["sid"] is not None else {})})
    return compute_chart(jd_ut=jd, lat=c["lat"], lon=c["lon"], settings=s)


@pytest.mark.parametrize("case", FIX["cases"], ids=[c["id"] for c in FIX["cases"]])
def test_matches_swetest(case):
    ch = run_case(case)
    pts, ref = ch["points"], case["points"]
    checks = {k: pts[k] for k in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus",
                                   "neptune", "pluto", "chiron", "asc", "mc", "vertex")}
    for pid, p in checks.items():
        assert angdiff(p["longitude"], ref[pid]["lon"]) < TOL_DEG, (pid, p["longitude"], ref[pid]["lon"])
        if pid not in ("asc", "mc", "vertex"):
            assert abs(p["speed_deg_per_day"] - ref[pid]["speed"]) < TOL_SPEED, pid
            assert (p["speed_deg_per_day"] < 0) == (ref[pid]["speed"] < 0), pid
    v = ch["variants"]
    assert angdiff(v["north_node"]["true"]["longitude"], ref["true_node"]["lon"]) < TOL_DEG
    assert angdiff(v["north_node"]["mean"]["longitude"], ref["mean_node"]["lon"]) < TOL_DEG
    for k in ("mean", "osculating", "interpolated"):
        assert angdiff(v["lilith"][k]["longitude"], ref[f"lilith_{k}"]["lon"]) < TOL_DEG, k
    assert angdiff(pts["north_node"]["longitude"], ref["true_node"]["lon"]) < TOL_DEG  # default = true node
    assert angdiff(pts["lilith"]["longitude"], ref["lilith_mean"]["lon"]) < TOL_DEG    # default = mean Lilith
    for i, cusp in enumerate(ch["houses"]["cusps"]):
        assert angdiff(cusp["longitude"], case["cusps"][i]) < TOL_DEG, (i + 1, cusp["longitude"], case["cusps"][i])
    if case["sid"] is not None:
        assert abs(ch["ayanamsa"]["value"] - case["ayanamsa"]) < TOL_DEG


def test_max_deviation_report(capsys):
    worst = 0.0
    for c in FIX["cases"]:
        ch = run_case(c)
        for pid in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto",
                    "chiron", "asc", "mc", "vertex"):
            worst = max(worst, angdiff(ch["points"][pid]["longitude"], c["points"][pid]["lon"]))
    print(f"max deviation vs swetest: {worst * 3600:.5f} arcsec")
    assert worst < TOL_DEG
