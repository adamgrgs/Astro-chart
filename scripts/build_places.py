"""Build data/places.tsv.gz from the GeoNames dump (CC BY 4.0).

Usage:  python scripts/build_places.py   (downloads cities5000.zip, admin1CodesASCII.txt, countryInfo.txt)
The offline index is the no-account fallback; with GEONAMES_USERNAME set, the live
GeoNames search API is used first.
"""
import csv, gzip, io, os, sys, urllib.request, zipfile

BASE = "https://download.geonames.org/export/dump/"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "places.tsv.gz")


def fetch(name: str) -> bytes:
    with urllib.request.urlopen(BASE + name, timeout=120) as r:
        return r.read()


def main() -> None:
    admin1 = {}
    for line in fetch("admin1CodesASCII.txt").decode().splitlines():
        p = line.split("\t")
        if len(p) >= 3:
            admin1[p[0]] = p[2] or p[1]
    countries = {}
    for line in fetch("countryInfo.txt").decode().splitlines():
        if line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) > 4:
            countries[p[0]] = p[4]
    z = zipfile.ZipFile(io.BytesIO(fetch("cities5000.zip")))
    rows = []
    for line in z.read("cities5000.txt").decode().splitlines():
        p = line.split("\t")
        gid, name, ascii_, alts, lat, lon, cc, a1, pop, tz = p[0], p[1], p[2], p[3], p[4], p[5], p[8], p[10], p[14], p[17]
        alt_ascii = sorted({a for a in alts.split(",") if a and a.isascii() and a not in (name, ascii_)})[:25]
        rows.append([gid, name, ascii_, "|".join(alt_ascii), cc, countries.get(cc, cc),
                     admin1.get(f"{cc}.{a1}", ""), lat, lon, tz, pop or "0"])
    rows.sort(key=lambda r: -int(r[10]))
    with gzip.open(OUT, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["geonameid", "name", "asciiname", "alternates", "country_code", "country", "admin1",
                    "lat", "lon", "timezone", "population"])
        w.writerows(rows)
    print(f"wrote {len(rows)} places -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
