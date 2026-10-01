"""Fetch reference positions from Astrodienst's public swetest service (astro.com/cgi/swetest.cgi).

swetest is the Swiss Ephemeris authors' own command-line reference program; the web
form runs it on Astrodienst's servers. We store the raw output plus parsed decimal
values in tests/fixtures/swetest_reference.json so the test-suite runs offline.

Usage: python scripts/fetch_reference.py
"""
import html, json, os, re, urllib.parse, urllib.request

OUT = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "swetest_reference.json")

# id, UT date (d.m.y), UT time, lon, lat, house letter, sidereal mode (swetest -sidN) or None
CASES = [
    ("cairo_1987_placidus", "6.7.1987", "21:30:00", 31.25, 30.0666667, "P", None),
    ("cairo_1987_wholesign_lahiri", "6.7.1987", "21:30:00", 31.25, 30.0666667, "W", 1),
    ("cairo_1987_equal", "6.7.1987", "21:30:00", 31.25, 30.0666667, "A", None),
    ("cairo_1987_placidus_faganbradley", "6.7.1987", "21:30:00", 31.25, 30.0666667, "P", 0),
    ("newyork_1990_placidus", "15.1.1990", "19:45:00", -74.006, 40.7128, "P", None),
    ("sydney_1975_placidus", "10.11.1975", "19:15:00", 151.2093, -33.8688, "P", None),
    ("reykjavik_2000_placidus", "21.6.2000", "12:00:00", -21.9426, 64.1466, "P", None),
    ("tromso_1995_porphyry", "25.12.1995", "07:00:00", 18.9553, 69.6496, "O", None),
    ("london_1850_placidus", "1.3.1850", "12:00:30", -0.1276, 51.5072, "P", None),
    ("tokyo_2150_koch", "1.1.2150", "00:00:00", 139.6917, 35.6895, "K", None),
    ("paris_1650_regiomontanus", "15.4.1650", "09:00:00", 2.3522, 48.8566, "R", None),
    ("rio_2500_campanus", "1.8.2500", "18:00:00", -43.1729, -22.9068, "C", None),
]
NAMES = {"Sun": "sun", "Moon": "moon", "Mercury": "mercury", "Venus": "venus", "Mars": "mars",
         "Jupiter": "jupiter", "Saturn": "saturn", "Uranus": "uranus", "Neptune": "neptune", "Pluto": "pluto",
         "Chiron": "chiron", "mean Node": "mean_node", "true Node": "true_node", "mean Apogee": "lilith_mean",
         "osc. Apogee": "lilith_osculating", "intp. Apogee": "lilith_interpolated", "Ascendant": "asc",
         "MC": "mc", "ARMC": "armc", "Vertex": "vertex"}


def fetch(date, time, lon, lat, hsys, sid):
    arg = f"-ut{time} -house{lon},{lat},{hsys}" + (f" -sid{sid}" if sid is not None else "")
    q = urllib.parse.urlencode({"b": date, "n": "1", "s": "1", "p": "p", "e": "-eswe", "f": "Pls", "arg": arg})
    with urllib.request.urlopen("https://www.astro.com/cgi/swetest.cgi?" + q, timeout=60) as r:
        page = r.read().decode("utf-8", "replace")
    pre = re.findall(r"<pre[^>]*>(.*?)</pre>", page, re.S)
    return html.unescape(re.sub("<[^>]+>", "", pre[0])).strip()


def parse(raw):
    vals, cusps = {}, {}
    for line in raw.splitlines():
        m = re.match(r"^house\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)", line)
        if m:
            cusps[int(m.group(1))] = float(m.group(2))
            continue
        m = re.match(r"^(.+?)\s{2,}(-?[\d.]+)\s+(-?[\d.]+)\s*$", line)
        if m and m.group(1).strip() in NAMES:
            vals[NAMES[m.group(1).strip()]] = {"lon": float(m.group(2)), "speed": float(m.group(3))}
    ver = re.search(r"version (\S+)", raw)
    ay = re.search(r"ayanamsa =\s+(\d+)°\s*(\d+)'\s*([\d.]+)", raw)
    return {"points": vals, "cusps": [cusps[i] for i in range(1, 13)], "swetest_version": ver.group(1) if ver else None,
            "ayanamsa": (int(ay.group(1)) + int(ay.group(2)) / 60 + float(ay.group(3)) / 3600) if ay else None}


def main():
    out = []
    for cid, date, time, lon, lat, hsys, sid in CASES:
        raw = fetch(date, time, lon, lat, hsys, sid)
        out.append({"id": cid, "ut_date": date, "ut_time": time, "lon": lon, "lat": lat, "hsys": hsys, "sid": sid,
                    "raw": raw, **parse(raw)})
        print(cid, len(out[-1]["points"]), "points")
    with open(OUT, "w") as f:
        json.dump({"source": "https://www.astro.com/cgi/swetest.cgi", "cases": out}, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
