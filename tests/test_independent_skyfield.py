"""Independent cross-check: Swiss Ephemeris vs NASA JPL DE421 via Skyfield (a separate code base).

Dev-only: skipped unless skyfield is installed and DE421_PATH points to de421.bsp
(https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de421.bsp, valid 1900-2050).
"""
import os

import pytest
import swisseph as swe

from astrocalc.engine import Settings, compute_chart

skyfield = pytest.importorskip("skyfield")
DE421 = os.environ.get("DE421_PATH", "")
pytestmark = pytest.mark.skipif(not os.path.exists(DE421), reason="DE421_PATH not set")

BODIES = {"sun": "sun", "moon": "moon", "mercury": "mercury", "venus": "venus", "mars": "mars barycenter",
          "jupiter": "jupiter barycenter", "saturn": "saturn barycenter", "uranus": "uranus barycenter",
          "neptune": "neptune barycenter", "pluto": "pluto barycenter"}
MOMENTS = [(1987, 7, 6, 21, 30, 0), (1990, 1, 15, 19, 45, 0), (1975, 11, 10, 19, 15, 0), (2000, 6, 21, 12, 0, 0),
           (1947, 8, 15, 0, 0, 0), (2033, 3, 1, 6, 0, 0)]


@pytest.mark.parametrize("moment", MOMENTS)
def test_vs_jpl_de421(moment):
    from skyfield.api import load
    from skyfield.framelib import ecliptic_frame
    ts = load.timescale(builtin=True)
    eph = load(DE421)
    t = ts.ut1(*moment)  # UT1 (= the UT used by swe.calc_ut); avoids pre-1972 UTC conventions
    earth = eph["earth"]
    y, mo, d, h, mi, s = moment
    ch = compute_chart(jd_ut=swe.julday(y, mo, d, h + mi / 60 + s / 3600), lat=None, lon=None,
                       settings=Settings(), time_known=False)
    for pid, name in BODIES.items():
        lat, lon, _ = earth.at(t).observe(eph[name]).apparent().frame_latlon(ecliptic_frame)
        diff = abs(((ch["points"][pid]["longitude"] - lon.degrees + 180) % 360) - 180) * 3600
        limit = 2.0 if pid == "moon" else 1.0  # arcseconds; covers ΔT and nutation-model differences
        assert diff < limit, f"{pid}: {diff:.3f} arcsec"


def test_report_max(capsys):
    from skyfield.api import load
    from skyfield.framelib import ecliptic_frame
    ts, eph = load.timescale(builtin=True), load(DE421)
    worst = {}
    for (y, mo, d, h, mi, s) in MOMENTS:
        t = ts.ut1(y, mo, d, h, mi, s)
        ch = compute_chart(jd_ut=swe.julday(y, mo, d, h + mi / 60 + s / 3600), lat=None, lon=None,
                           settings=Settings(), time_known=False)
        for pid, name in BODIES.items():
            lon = eph["earth"].at(t).observe(eph[name]).apparent().frame_latlon(ecliptic_frame)[1].degrees
            diff = abs(((ch["points"][pid]["longitude"] - lon + 180) % 360) - 180) * 3600
            worst[pid] = max(worst.get(pid, 0), diff)
    print("max |SE − JPL DE421| arcsec:", {k: round(v, 3) for k, v in worst.items()})
