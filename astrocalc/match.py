"""Ideal-match finder (synastry scan) - fully deterministic.

Method
------
For every calendar day in a birth-year window around the user (default ±10 years, never after
today), compute a candidate partner's planets at 12:00 UT with the same Swiss Ephemeris settings.
Score classic synastry contacts between candidate planets and the user's natal points:

  score = Σ  pair_weight × aspect_quality × closeness,   closeness = 1 − orb / max_orb

* Pair weights favour the traditional relationship indicators (Sun–Moon, Venus–Mars, Moon–Moon,
  Sun–Venus, Moon–Venus, contacts to the Ascendant when the birth time is known ...).
* Aspect quality: trine +1.0, sextile +0.7, conjunction +1.0 (+0.3 for Mars/Saturn), opposition
  +0.4 (attraction with tension), square −0.6 (Saturn: −1.0).
* The candidate's birth time is unknown, so their Moon (≈13°/day) carries ±6.5° of uncertainty. Moon
  contacts are therefore scored separately ("moon bonus") and only used to pick the best single days
  inside a window; the windows themselves come from the slow planets (Sun, Mercury, Venus, Mars,
  Jupiter, Saturn), which move little within a day.
* Match strength = window peak score as a % of the best day found; also reported as "top X% of days".

Output: top birth-date windows (contiguous days in the top 10%), the candidate's Sun/Venus/Mars signs
for each window, the strongest reasons, and a ranking of the 12 Sun signs ("horoscopes") by average
score across the whole window. This is astrology, not a validated predictor of compatibility.
"""
from __future__ import annotations

import bisect
import datetime as dt
from typing import Any

import swisseph as swe

from . import constants as C
from . import meanings as M
from .engine import Settings, _LOCK, ensure_thread_init
from .formatting import sign_of

CAND = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
SLOW = [p for p in CAND if p != "moon"]
USER = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "asc"]

PAIR_WEIGHT = {
    frozenset(("sun", "moon")): 10, frozenset(("venus", "mars")): 9, frozenset(("moon",)): 7,
    frozenset(("sun", "venus")): 7, frozenset(("moon", "venus")): 7, frozenset(("venus",)): 6,
    frozenset(("sun",)): 5, frozenset(("sun", "asc")): 6, frozenset(("moon", "asc")): 6,
    frozenset(("venus", "asc")): 6, frozenset(("mars", "asc")): 4, frozenset(("sun", "mars")): 4,
    frozenset(("moon", "mars")): 4, frozenset(("mercury",)): 4, frozenset(("sun", "mercury")): 3,
    frozenset(("moon", "mercury")): 3, frozenset(("venus", "mercury")): 3, frozenset(("mars",)): 3,
    frozenset(("jupiter", "sun")): 4, frozenset(("jupiter", "moon")): 4, frozenset(("jupiter", "venus")): 4,
    frozenset(("saturn", "sun")): 3, frozenset(("saturn", "moon")): 3, frozenset(("saturn", "venus")): 3,
}
ASPECT_ANGLES = {"conjunction": 0, "sextile": 60, "square": 90, "trine": 120, "opposition": 180}
LUMINARY_ORB, OTHER_ORB, CAND_MOON_EXTRA = 6.0, 4.0, 6.5

REASON = {
    frozenset(("sun", "moon")): "core identity meets emotional needs - the classic sign of feeling 'at home' together",
    frozenset(("venus", "mars")): "romantic and physical chemistry",
    frozenset(("moon",)): "you process feelings the same way and feel instinctively understood",
    frozenset(("sun", "venus")): "genuine affection and admiration for who the other person is",
    frozenset(("moon", "venus")): "tenderness, care and emotional warmth",
    frozenset(("venus",)): "shared tastes, values and ways of showing love",
    frozenset(("sun",)): "compatible life goals and sense of self",
    frozenset(("sun", "asc")): "an instant 'I get you' when you first meet",
    frozenset(("moon", "asc")): "feeling comfortable in each other's company straight away",
    frozenset(("venus", "asc")): "strong attraction to how the other person looks and carries themselves",
    frozenset(("mars", "asc")): "energising, spark-filled attraction",
    frozenset(("sun", "mars")): "you motivate each other to act",
    frozenset(("moon", "mars")): "passion with emotional intensity",
    frozenset(("mercury",)): "easy conversation - you think on the same wavelength",
    frozenset(("sun", "mercury")): "they understand what you are really saying",
    frozenset(("moon", "mercury")): "you can talk about feelings openly",
    frozenset(("venus", "mercury")): "sweet, affectionate communication",
    frozenset(("mars",)): "shared energy and drive",
    frozenset(("jupiter", "sun")): "you bring out each other's optimism and growth",
    frozenset(("jupiter", "moon")): "generosity and emotional support",
    frozenset(("jupiter", "venus")): "fun, abundance and good times together",
    frozenset(("saturn", "sun")): "commitment and staying power",
    frozenset(("saturn", "moon")): "loyalty and long-term security",
    frozenset(("saturn", "venus")): "a love that is built to last",
}


def _quality(a: str, b: str, asp: str) -> float:
    harsh = "saturn" in (a, b) or (a == "mars" and b == "mars")
    return {"trine": 1.0, "sextile": 0.7, "conjunction": 0.3 if harsh else 1.0,
            "opposition": -0.6 if "saturn" in (a, b) else 0.4,
            "square": -1.0 if "saturn" in (a, b) else -0.6}[asp]


def _contacts(cand: dict[str, float], user: dict[str, float], moon_extra: float = 0.0
              ) -> list[tuple[float, str, str, str, float]]:
    out = []
    for cp, clon in cand.items():
        for up, ulon in user.items():
            key = frozenset((cp, up))
            w = PAIR_WEIGHT.get(key)
            if not w:
                continue
            max_orb = LUMINARY_ORB if ("sun" in key or "moon" in key or "asc" in key) else OTHER_ORB
            if cp == "moon":
                max_orb += moon_extra
            sep = abs(((clon - ulon + 180) % 360) - 180)
            for asp, ang in ASPECT_ANGLES.items():
                orb = abs(sep - ang)
                if orb <= max_orb:
                    out.append((w * _quality(cp, up, asp) * (1 - orb / max_orb), cp, up, asp, orb))
                    break
    return out


def _flags(settings: Settings) -> int:
    f = swe.FLG_SWIEPH
    if settings.zodiac == "sidereal":
        f |= swe.FLG_SIDEREAL
    return f


def _scan(start: dt.date, end: dt.date, settings: Settings) -> list[tuple[dt.date, dict[str, float]]]:
    flags = _flags(settings)
    bodies = {p: C.PLANETS[p][1] for p in CAND}
    days = []
    with _LOCK:
        ensure_thread_init()
        if settings.zodiac == "sidereal":
            swe.set_sid_mode(C.AYANAMSAS[settings.ayanamsa], 0, 0)
        try:
            d = start
            while d <= end:
                jd = swe.julday(d.year, d.month, d.day, 12.0)
                days.append((d, {p: swe.calc_ut(jd, b, flags)[0][0] for p, b in bodies.items()}))
                d += dt.timedelta(days=1)
        finally:
            if settings.zodiac == "sidereal":
                swe.set_sid_mode(swe.SIDM_FAGAN_BRADLEY, 0, 0)
    return days


def _reason_text(cp: str, up: str, asp: str, score: float) -> str:
    who = f"Their {C.POINT_LABELS[cp]}"
    if cp == "moon":
        who += " (on the best dates; depends on their birth time)"
    if score < 0:
        verb = {"square": "squares", "opposition": "opposes", "conjunction": "sits on"}.get(asp, "challenges")
        return (f"{who} {verb} your {C.POINT_LABELS[up]} - friction around "
                f"\"{REASON[frozenset((cp, up))]}\" that needs patience")
    verb = {"trine": "flows with", "sextile": "supports", "conjunction": "meets", "opposition": "attracts"}[asp]
    return f"{who} {verb} your {C.POINT_LABELS[up]} - {REASON[frozenset((cp, up))]}"


def find_matches(chart: dict[str, Any], years_before: int = 10, years_after: int = 10, top: int = 6,
                 today: dt.date | None = None) -> dict[str, Any]:
    settings = Settings.from_dict(chart["settings"])
    pts = {p["id"]: p for p in chart["points"]}
    user = {p: pts[p]["longitude"] for p in USER if p in pts and (p != "asc" or chart["time_known"])}
    if not chart["time_known"]:
        user.pop("moon", None)  # user's Moon also uncertain by up to ±6.5°; keep it only if certain
        unc = ((chart.get("uncertainty") or {}).get("points") or {}).get("moon")
        if unc and unc.get("span_deg", 99) <= 14:
            user["moon"] = pts["moon"]["longitude"]
    by, bm, bd = map(int, chart["input"]["date"].split("-"))
    today = today or dt.date.today()
    lo_y, hi_y = C.SUPPORTED_YEARS
    start = dt.date(max(lo_y, by - years_before), 1, 1)
    end = min(dt.date(min(hi_y, by + years_after), 12, 31), today)
    if end <= start:
        raise ValueError("Search window is empty (the end is before the start or after today).")
    days = _scan(start, end, settings)

    rows = []
    for d, cand in days:
        slow = _contacts({p: cand[p] for p in SLOW}, user)
        moon = _contacts({"moon": cand["moon"]}, user, CAND_MOON_EXTRA)
        rows.append({"date": d, "cand": cand, "slow": slow, "moon": moon,
                     "slow_score": sum(c[0] for c in slow), "moon_score": sum(c[0] for c in moon) * 0.6})
    for r in rows:
        r["total"] = r["slow_score"] + r["moon_score"]
    slows = sorted(r["slow_score"] for r in rows)
    n = len(rows)
    for r in rows:
        r["top_share"] = (n - bisect.bisect_left(slows, r["slow_score"])) / n

    # windows: runs of days in the top 10% by slow score (gaps <= 2 days merged)
    thr = slows[int(n * 0.90)] if n > 10 else slows[-1]
    runs, cur, gap = [], [], 0
    for r in rows:
        if r["slow_score"] >= thr:
            cur.append(r)
            gap = 0
        elif cur:
            gap += 1
            if gap > 2:
                runs.append(cur)
                cur, gap = [], 0
    if cur:
        runs.append(cur)
    runs.sort(key=lambda run: max(x["slow_score"] for x in run), reverse=True)

    windows: list[dict[str, Any]] = []
    per_sign: dict[str, int] = {}
    best_slow = max(slows) or 1.0
    for run in runs:
        if len(windows) >= top:
            break
        peak = max(run, key=lambda x: x["slow_score"])
        psign = sign_of(peak["cand"]["sun"])["sign"]
        if per_sign.get(psign, 0) >= 2:  # keep the list varied: at most 2 windows per Sun sign
            continue
        per_sign[psign] = per_sign.get(psign, 0) + 1
        best_days = sorted(run, key=lambda x: x["total"], reverse=True)[:3]
        cand = peak["cand"]
        contacts = sorted(peak["slow"] + max(best_days, key=lambda x: x["total"])["moon"],
                          key=lambda c: c[0], reverse=True)
        reasons = [_reason_text(c[1], c[2], c[3], c[0]) for c in contacts if c[0] > 0][:4]
        cautions = [_reason_text(c[1], c[2], c[3], c[0]) for c in contacts if c[0] < 0][:2]
        signs = lambda p: list(dict.fromkeys(sign_of(x["cand"][p])["sign"] for x in run))  # noqa: E731
        windows.append({
            "from": run[0]["date"].isoformat(), "to": run[-1]["date"].isoformat(), "days": len(run),
            "peak_date": peak["date"].isoformat(),
            "best_dates": [x["date"].isoformat() for x in sorted(best_days, key=lambda x: x["date"])],
            "match_strength": round(100 * peak["slow_score"] / best_slow),
            "top_percent_of_days": round(100 * peak["top_share"], 2),
            "sun_signs": signs("sun"), "moon_signs_best_dates": list(dict.fromkeys(
                sign_of(x["cand"]["moon"])["sign"] for x in best_days)),
            "venus_signs": signs("venus"), "mars_signs": signs("mars"), "mercury_signs": signs("mercury"),
            "reasons": reasons, "cautions": cautions,
            "element": M.ELEMENT[sign_of(cand["sun"])["sign"]],
        })

    # Sun-sign ("horoscope") ranking: average slow score by candidate Sun sign
    agg: dict[str, list[float]] = {}
    for r in rows:
        agg.setdefault(sign_of(r["cand"]["sun"])["sign"], []).append(r["slow_score"])
    avg = {s: sum(v) / len(v) for s, v in agg.items()}
    lo, hi = min(avg.values()), max(avg.values())
    sign_rank = sorted(({"sign": s, "score": round(100 * (v - lo) / (hi - lo), 1) if hi > lo else 50.0,
                         "element": M.ELEMENT[s], "style": M.SIGN_STYLE[s]} for s, v in avg.items()),
                       key=lambda x: x["score"], reverse=True)
    return {
        "search": {"from": start.isoformat(), "to": end.isoformat(), "days_scanned": n,
                   "candidate_time": "12:00 UT (partner birth time unknown)",
                   "zodiac": settings.zodiac, "ayanamsa": settings.ayanamsa if settings.zodiac == "sidereal" else None,
                   "user_points_used": [C.POINT_LABELS[p] for p in user]},
        "windows": windows,
        "sun_sign_ranking": sign_rank,
        "method": {
            "score": "Σ pair_weight × aspect_quality × (1 − orb/max_orb) over partner→you contacts",
            "orbs": {"luminaries_and_ascendant": LUMINARY_ORB, "other": OTHER_ORB,
                     "partner_moon_extra_for_unknown_time": CAND_MOON_EXTRA},
            "aspect_quality": {"trine": 1.0, "sextile": 0.7, "conjunction": "1.0 (0.3 with Mars–Mars/Saturn)",
                               "opposition": "0.4 (−0.6 with Saturn)", "square": "−0.6 (−1.0 with Saturn)"},
            "windows": "contiguous days in the top 10% of slow-planet score; gaps ≤2 days merged",
            "match_strength": "window peak score as % of the best day in the whole scan (100 = best found)",
            "top_percent_of_days": "share of scanned days scoring at least as high as the window peak",
            "sign_ranking": "average slow-planet score of all scanned days with that Sun sign, scaled 0-100",
        },
    }
