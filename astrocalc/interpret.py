"""Chart interpretation.

Pipeline (positions are never produced here - they come from build_chart):
  1. chart_facts(chart)   deterministic: Big Three, element/modality balance, chart ruler, stelliums,
                          angular planets, tightest aspects, retrogrades, uncertainty flags.
  2. template_reading()   deterministic plain-English reading from meanings.py (always available).
  3. ai_reading()         optional: a specialised astrologer prompt turns the SAME facts into richer prose.
                          The output is checked by validate_claims(); any placement claim that disagrees
                          with the chart (wrong sign / house, any degree figure, houses when the birth time
                          is unknown) rejects the AI text and the template reading is returned instead.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from . import llm
from . import meanings as M
from .constants import SIGNS

PERSONAL = ["sun", "moon", "mercury", "venus", "mars"]
CORE_PLANETS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
# weights for element / modality balance (luminaries and Ascendant count double)
BALANCE_WEIGHTS = {"sun": 2, "moon": 2, "asc": 2, "mercury": 1, "venus": 1, "mars": 1, "jupiter": 1,
                   "saturn": 1, "uranus": 0.5, "neptune": 0.5, "pluto": 0.5}
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}


def _ord(n: int) -> str:
    return ORDINAL.get(n, f"{n}th")


def _pts(chart: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in chart["points"]}


def _sign_options(chart: dict[str, Any], pid: str) -> list[str]:
    """Signs a point could be in. With unknown birth time, a fast point may span two signs over the day."""
    p = _pts(chart).get(pid)
    if not p:
        return []
    unc = ((chart.get("uncertainty") or {}).get("points") or {}).get(pid)
    if unc and unc.get("sign_changes"):
        return list(unc["signs"])
    return [p["sign"]]


# ------------------------------------------------------------------ 1. facts
def chart_facts(chart: dict[str, Any]) -> dict[str, Any]:
    pts = _pts(chart)
    known = chart["time_known"]

    def place(pid: str) -> dict[str, Any] | None:
        p = pts.get(pid)
        if not p:
            return None
        opts = _sign_options(chart, pid)
        d = {"id": pid, "label": p["label"], "sign": p["sign"], "sign_options": opts,
             "sign_certain": len(opts) == 1, "house": p.get("house") if known else None,
             "retrograde": bool((p.get("motion") or {}).get("retrograde")) and pid not in ("north_node", "south_node"),
             "theme": M.PLANET_THEME.get(pid), "sign_style": M.SIGN_STYLE[p["sign"]],
             "house_area": M.HOUSE_AREA.get(p.get("house")) if known and p.get("house") else None}
        return d

    placements = [x for x in (place(pid) for pid in CORE_PLANETS + ["chiron", "north_node", "lilith", "asc", "mc",
                                                                     "fortune"]) if x]

    elements, modalities = Counter(), Counter()
    for pid, w in BALANCE_WEIGHTS.items():
        if pid in pts and (pid != "asc" or known):
            elements[M.ELEMENT[pts[pid]["sign"]]] += w
            modalities[M.MODALITY[pts[pid]["sign"]]] += w
    dom_el = max(elements, key=elements.get)
    low_el = [e for e in ("fire", "earth", "air", "water") if elements.get(e, 0) <= 1]
    dom_mod = max(modalities, key=modalities.get)

    ruler = None
    if known and "asc" in pts:
        rid = M.RULER[pts["asc"]["sign"]]
        r = pts[rid]
        ruler = {"id": rid, "label": r["label"], "sign": r["sign"], "house": r.get("house"),
                 "why": f"{rid.title()} rules {pts['asc']['sign']}, your rising sign"}

    sign_counts = Counter(pts[p]["sign"] for p in CORE_PLANETS)
    stelliums = [{"sign": s, "planets": [pts[p]["label"] for p in CORE_PLANETS if pts[p]["sign"] == s]}
                 for s, n in sign_counts.items() if n >= 3]
    house_stelliums, angular = [], []
    if known:
        hc = Counter(pts[p]["house"] for p in CORE_PLANETS)
        house_stelliums = [{"house": h, "area": M.HOUSE_AREA[h],
                            "planets": [pts[p]["label"] for p in CORE_PLANETS if pts[p]["house"] == h]}
                           for h, n in hc.items() if n >= 3]
        angular = [pts[p]["label"] for p in CORE_PLANETS if pts[p]["house"] in (1, 4, 7, 10)]

    main_ids = set(CORE_PLANETS + ["asc", "mc", "chiron", "north_node"])
    asp = [a for a in chart["aspects"] if a["a"] in main_ids and a["b"] in main_ids
           and not (a.get("occurs") == "part_of_day")]
    asp.sort(key=lambda a: (0 if (a["a"] in PERSONAL or a["b"] in PERSONAL or a["a"] == "asc") else 1, a["orb"]))
    top_aspects = [{"a": a["a_label"], "b": a["b_label"], "type": a["type"], "orb": a["orb_formatted"],
                    "status": a.get("status"), "verb": M.ASPECT_TEXT[a["type"]][0],
                    "meaning": M.ASPECT_TEXT[a["type"]][1]} for a in asp[:8]]

    retro = [pts[p]["label"] for p in CORE_PLANETS[2:] if (pts[p].get("motion") or {}).get("retrograde")]
    uncertain = []
    if not known:
        uncertain = [pts[p]["label"] for p in (chart.get("uncertainty") or {}).get("uncertain_points", []) if p in pts]

    compact = [f"{p['label']}: " + (p["sign"] if p["sign_certain"] else " or ".join(p["sign_options"]))
               + (f", {_ord(p['house'])} house" if p.get("house") else "") + (", retrograde" if p["retrograde"] else "")
               for p in placements]
    return {
        "placements_checklist": compact,
        "time_known": known,
        "big_three": {"sun": place("sun"), "moon": place("moon"), "rising": place("asc") if known else None},
        "placements": placements,
        "elements": dict(elements), "dominant_element": dom_el, "dominant_element_meaning": M.ELEMENT_TEXT[dom_el],
        "weak_elements": low_el,
        "modalities": dict(modalities), "dominant_modality": dom_mod,
        "dominant_modality_meaning": M.MODALITY_TEXT[dom_mod],
        "chart_ruler": ruler, "sign_stelliums": stelliums, "house_stelliums": house_stelliums,
        "angular_planets": angular, "top_aspects": top_aspects, "retrograde_planets": retro,
        "uncertain_points": uncertain,
        "settings": {"zodiac": chart["settings"]["zodiac"],
                     "houses": (chart.get("houses") or {}).get("system_label")},
    }


# ------------------------------------------------------------------ 2. deterministic template
def _pl_sentence(p: dict[str, Any]) -> str:
    sign = p["sign"] if p["sign_certain"] else " or ".join(p["sign_options"]) + " (depends on birth time)"
    s = f"**{p['label']} in {sign}**"
    if p.get("house"):
        s += f", {_ord(p['house'])} house"
    art = "an" if p["sign_style"][0] in "aeiou" else "a"
    s += f" - {p['theme']}, expressed in {art} {p['sign_style']} way"
    if p.get("house_area"):
        s += f", played out mostly through {p['house_area']}"
    if p.get("retrograde"):
        s += ". It was retrograde at birth, so this side of you tends to work inwardly and get revisited over time"
    return s + "."


def template_reading(f: dict[str, Any]) -> dict[str, Any]:
    by = {p["id"]: p for p in f["placements"]}
    sun, moon, rising = f["big_three"]["sun"], f["big_three"]["moon"], f["big_three"]["rising"]
    moon_sign = moon["sign"] if moon["sign_certain"] else "/".join(moon["sign_options"])
    head = f"{sun['sign']} Sun, {moon_sign} Moon" + (f", {rising['sign']} rising" if rising else "")
    summary = (f"{head}. At heart you are {M.SIGN_STYLE[sun['sign']]}; emotionally you need what a "
               f"{moon_sign} Moon needs" + (f", and people first meet someone {M.SIGN_STYLE[rising['sign']]}"
                                            if rising else "")
               + f". Your chart leans towards {f['dominant_element']} - {f['dominant_element_meaning']} - and "
                 f"towards {f['dominant_modality_meaning']}.")
    sections = [
        {"title": "Your core: Sun, Moon" + (" and Rising" if rising else ""),
         "body": "\n".join(_pl_sentence(by[p]) for p in ("sun", "moon", "asc") if p in by)},
        {"title": "Mind, love and drive",
         "body": "\n".join(_pl_sentence(by[p]) for p in ("mercury", "venus", "mars"))},
        {"title": "Growth and tests",
         "body": "\n".join(_pl_sentence(by[p]) for p in ("jupiter", "saturn"))},
    ]
    if f["top_aspects"]:
        sections.append({"title": "Your strongest inner patterns", "body": "\n".join(
            f"**{a['a']} {a['verb']} {a['b']}** ({a['type']}, orb {a['orb']}): {a['meaning']}."
            for a in f["top_aspects"][:5])})
    focus = []
    if f["chart_ruler"]:
        r = f["chart_ruler"]
        focus.append(f"Your chart ruler is **{r['label']}** in {r['sign']}"
                     + (f" in the {_ord(r['house'])} house" if r.get("house") else "")
                     + f" ({r['why']}) - its themes colour your whole life path.")
    for s in f["sign_stelliums"]:
        focus.append(f"A cluster of planets in **{s['sign']}** ({', '.join(s['planets'])}) makes "
                     f"{s['sign']} qualities - {M.SIGN_STYLE[s['sign']]} - a big part of who you are.")
    for h in f["house_stelliums"]:
        focus.append(f"Several planets in your **{_ord(h['house'])} house** ({', '.join(h['planets'])}) put "
                     f"{h['area']} at the centre of your life.")
    if f["angular_planets"]:
        focus.append(f"Planets in the angular houses - 1st, 4th, 7th and 10th ({', '.join(f['angular_planets'])}) - "
                     "are especially visible in your personality and life.")
    if f["weak_elements"]:
        focus.append(f"Little {' or '.join(f['weak_elements'])} in the chart: qualities like "
                     + "; ".join(M.ELEMENT_TEXT[e].split(' and a need')[0] for e in f["weak_elements"])
                     + " may take conscious effort - or be what you seek in others.")
    if focus:
        sections.append({"title": "Where your life focuses", "body": "\n".join(focus)})
    if not f["time_known"]:
        sections.append({"title": "What we can't say without a birth time", "body":
                         "Your rising sign, houses and chart angles depend on the exact birth time, so they are left "
                         "out. " + (f"These placements could be in either of two signs: {', '.join(f['uncertain_points'])}."
                                    if f["uncertain_points"] else "")})
    return {"summary": summary, "sections": sections}


# ------------------------------------------------------------------ 3. AI writer + guardrail
SYSTEM_PROMPT = """You are a senior professional astrologer and a gifted plain-English writer.
You turn a pre-calculated natal chart into a reading that a complete beginner understands and enjoys.

HARD RULES
- Use ONLY the placements, houses and aspects in the FACTS JSON. placements_checklist is the source of truth:
  before writing "<Planet> in <Sign>", check it there. A house cluster does NOT mean the planets share a sign. Never add, move or guess a planet, sign,
  house, aspect or degree. Do not write any degree figures.
- If a fact has sign_certain=false, say it could be either sign. If time_known=false, never mention
  houses, the Ascendant/rising sign or the Midheaven.
- Plain English. When you use an astrology word (e.g. "trine", "house"), explain it in a few words the
  first time. No fatalism; no medical, legal or financial advice; no predictions of specific events.
- Second person ("you"), warm, specific, hook-first. Make the reader recognise themselves; mention both
  gifts and growth edges.
- When you name a placement, write it exactly as "<Planet> in <Sign>" (e.g. "Venus in Leo") and houses as
  "<Planet> in the 5th house".

OUTPUT: a single JSON object, nothing else:
{"summary": "3-4 sentence hook that captures the essence of the chart",
 "sections": [{"title": "...", "body": "..."}]}
Sections, in order: "Your core self", "Your emotional world", "How you think and talk",
"Love and attraction", "Drive and ambition", "Your growth path", "Your strongest patterns" (the top
aspects), and "Where your life focuses" (skip if time_known=false). 80-160 words per section. Use "\\n" to
separate paragraphs; **bold** is allowed for placement names."""


PLANET_NAMES = {"Sun": "sun", "Moon": "moon", "Mercury": "mercury", "Venus": "venus", "Mars": "mars",
                "Jupiter": "jupiter", "Saturn": "saturn", "Uranus": "uranus", "Neptune": "neptune",
                "Pluto": "pluto", "Chiron": "chiron", "North Node": "north_node", "South Node": "south_node",
                "Lilith": "lilith", "Ascendant": "asc", "Rising": "asc", "Midheaven": "mc"}
WORD_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
            "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12}
_PN = "|".join(sorted(map(re.escape, PLANET_NAMES), key=len, reverse=True))
_SG = "|".join(SIGNS)
_GAP = rf"(?:(?!\b(?:{_PN})\b)[^.;:\n]){{0,25}}?"  # gap that does not cross another planet name
RE_IN_SIGN = re.compile(rf"\b(your |their |his |her )?({_PN})\b{_GAP}\bin ({_SG})\b")
RE_SIGN_PLANET = re.compile(rf"\b(your |their )?({_SG})[- ]({_PN})\b", re.I)
RE_HOUSE = re.compile(rf"\b({_PN})\b{_GAP}\b(?:in|of|through) (?:your |the )?(\d{{1,2}})(?:st|nd|rd|th)[- ]house"
                      rf"|\b({_PN})\b{_GAP}\b(?:in|of|through) (?:your |the )?({'|'.join(WORD_ORD)})[- ]house",
                      re.I)
RE_DEGREE = re.compile(r"\d+\s*°|\d+ degrees")


def validate_claims(text: str, chart: dict[str, Any], partner_signs: dict[str, set[str]] | None = None
                    ) -> list[str]:
    """Return a list of contradictions between free text and the calculated chart.

    partner_signs: for compatibility text, claims about "their X" are checked against the set of signs the
    recommended partner dates actually have.
    """
    pts = _pts(chart)
    known = chart["time_known"]
    bad: list[str] = []
    allowed_orbs = {a["orb_formatted"] for a in chart["aspects"]}
    stripped = re.sub(r"orb (\d+°\d{2}′)", lambda m: "" if m.group(1) in allowed_orbs else m.group(0), text)
    if RE_DEGREE.search(stripped):  # positions are never written as degrees; only real aspect orbs may appear
        bad.append(f"degree figure stated: {RE_DEGREE.search(stripped).group(0)!r}")

    def check(owner: str | None, planet: str, sign: str, snippet: str):
        planet = next(k for k in PLANET_NAMES if k.lower() == planet.lower())
        sign = next(x for x in SIGNS if x.lower() == sign.lower())
        pid = PLANET_NAMES[planet]
        owner = (owner or "").strip().lower()
        if owner == "their":
            if partner_signs is not None and pid in partner_signs and sign not in partner_signs[pid]:
                bad.append(f"partner {planet} in {sign} not in recommended dates: {snippet!r}")
            return
        if pid in ("asc", "mc") and not known:
            bad.append(f"{planet} mentioned although birth time is unknown: {snippet!r}")
            return
        if pid not in pts:
            return
        if sign not in _sign_options(chart, pid):
            if partner_signs is not None and pid in partner_signs and sign in partner_signs[pid] and owner != "your":
                return
            bad.append(f"{planet} in {sign} contradicts chart ({pts[pid]['sign']}): {snippet!r}")

    for m in RE_IN_SIGN.finditer(text):
        check(m.group(1), m.group(2), m.group(3), m.group(0))
    for m in RE_SIGN_PLANET.finditer(text):
        check(m.group(1), m.group(3), m.group(2), m.group(0))
    for m in RE_HOUSE.finditer(text):
        planet = m.group(1) or m.group(3)
        planet = next(k for k in PLANET_NAMES if k.lower() == planet.lower())
        num = int(m.group(2)) if m.group(2) else WORD_ORD[m.group(4).lower()]
        pid = PLANET_NAMES[planet]
        if partner_signs is not None and re.search(r"\btheir\b", m.group(0), re.I):
            continue
        if not known:
            bad.append(f"house placement stated although birth time is unknown: {m.group(0)!r}")
        elif pid in pts and pts[pid].get("house") != num:
            bad.append(f"{planet} in house {num} contradicts chart (house {pts[pid].get('house')}): {m.group(0)!r}")
    return bad


def _as_text(reading: dict[str, Any]) -> str:
    return reading.get("summary", "") + "\n" + "\n".join(
        f"{s.get('title', '')}\n{s.get('body', '')}" for s in reading.get("sections", []))


def _clean_ai(obj: dict[str, Any]) -> dict[str, Any]:
    secs = [{"title": str(s.get("title", ""))[:120], "body": str(s.get("body", ""))[:2500]}
            for s in obj.get("sections", []) if isinstance(s, dict) and s.get("body")]
    if not secs or not obj.get("summary"):
        raise llm.AIUnavailable("AI response missing summary/sections")
    return {"summary": str(obj["summary"])[:1200], "sections": secs[:10]}


def generate(system: str, facts: dict[str, Any], chart: dict[str, Any], fallback: dict[str, Any],
             use_ai: bool, partner_signs: dict[str, set[str]] | None = None) -> dict[str, Any]:
    """Run the AI writer with guardrail + one corrective retry; fall back to the template."""
    meta: dict[str, Any] = {"source": "template", "provider": None, "model": None, "guardrail": None}
    if not use_ai:
        return {**fallback, **meta, "note": "AI writing disabled for this request; deterministic text shown."}
    if not llm.provider():
        return {**fallback, **meta, "note": "No AI key configured on the server; deterministic text shown."}
    user = "FACTS (calculated with Swiss Ephemeris; authoritative):\n" + json.dumps(facts, ensure_ascii=False)
    problems: list[str] = []
    for attempt in range(2):
        prompt = user if not problems else (user + "\n\nYour previous draft contradicted the facts: "
                                            + "; ".join(problems[:8]) + ". Correct placements: "
                                            + "; ".join(facts.get("placements_checklist")
                                                        or facts.get("user", {}).get("placements_checklist", []))
                                            + ". Rewrite the whole JSON and fix these.")
        try:
            obj, prov, model = llm.complete_json(system, prompt)
            reading = _clean_ai(obj)
        except llm.AIUnavailable as exc:
            return {**fallback, **meta, "note": f"AI writer unavailable ({str(exc)[:160]}); deterministic text shown."}
        problems = validate_claims(_as_text(reading), chart, partner_signs)
        if not problems:
            return {**reading, "source": "ai", "provider": prov, "model": model,
                    "guardrail": {"checked": True, "attempts": attempt + 1, "violations": []}}
    return {**fallback, **meta, "guardrail": {"checked": True, "attempts": 2, "violations": problems[:8]},
            "note": "AI text contradicted the calculated chart and was discarded; deterministic text shown."}


def interpret(chart: dict[str, Any], use_ai: bool = True) -> dict[str, Any]:
    facts = chart_facts(chart)
    reading = generate(SYSTEM_PROMPT, facts, chart, template_reading(facts), use_ai)
    return {"facts": facts, "reading": reading, "disclaimer": M.DISCLAIMER}


# ------------------------------------------------------------------ ideal-match profile
MATCH_PROMPT = """You are a senior relationship astrologer and a warm, plain-English writer.
You receive (1) facts about the user's natal chart and (2) the result of a deterministic synastry scan that
ranked partner birth dates and Sun signs by compatibility with the user. Write the user's "ideal match"
profile so a beginner understands who they click with and why.

HARD RULES
- Use ONLY the facts and scan results given. Never invent a placement, a sign, a date, a score or a degree.
  Do not write degree figures or specific calendar dates (the app shows the date table itself); you may
  refer to windows as "your #1 window", "#2" etc. and name their Sun signs.
- When you mention the partner's planets write "their <Planet> in <Sign>" using only signs listed for that
  window; the user's own placements as "your <Planet> in <Sign>".
- Plain English; explain any astrology word briefly. Respectful and inclusive: no gender assumptions.
  No guarantees - compatibility is potential, not destiny.

OUTPUT: a single JSON object, nothing else:
{"summary": "2-3 sentence hook describing the person they are most compatible with",
 "sections": [{"title": "...", "body": "..."}]}
Sections in order: "What you need in a partner" (from the user's Moon, Venus, Mars and 7th-house facts if
known), "Your ideal match, described" (personality portrait), "Your most compatible horoscopes" (top 3-4 Sun
signs from sun_sign_ranking, why each works, and one sign that is harder for you), "Your best birth-date
windows" (one short paragraph per window, #1 first, using its reasons and cautions), "How to make it work".
80-160 words per section; use "\\n" between paragraphs; **bold** allowed."""


def match_template(f: dict[str, Any], res: dict[str, Any]) -> dict[str, Any]:
    by = {p["id"]: p for p in f["placements"]}
    top = res["sun_sign_ranking"][:3]
    low = res["sun_sign_ranking"][-1]
    moon, venus, mars = by["moon"], by["venus"], by["mars"]
    summary = (f"Your strongest chemistry is with **{top[0]['sign']}**, **{top[1]['sign']}** and **{top[2]['sign']}** "
               f"Suns - people who are {top[0]['style']}. The scan found {len(res['windows'])} birth-date windows "
               "where a partner's planets line up especially well with yours.")
    need = (f"With your **Moon in {moon['sign'] if moon['sign_certain'] else ' or '.join(moon['sign_options'])}** "
            f"you need someone who meets your emotional style ({moon['sign_style']}). Your **Venus in "
            f"{venus['sign']}** loves in a {venus['sign_style']} way, and your **Mars in {mars['sign']}** "
            f"is drawn to energy that is {mars['sign_style']}.")
    signs = "\n".join(f"**{i + 1}. {s['sign']}** ({s['element']}, score {s['score']:.0f}/100) - "
                      f"{s['style']}." for i, s in enumerate(res["sun_sign_ranking"][:4]))
    signs += f"\nHarder match: **{low['sign']}** - it forms fewer easy contacts with your chart."
    wins = []
    for i, w in enumerate(res["windows"]):
        line = (f"**#{i + 1}: {w['from']} to {w['to']}** ({'/'.join(w['sun_signs'])} Sun, match strength "
                f"{w['match_strength']}/100, top {w['top_percent_of_days']}% of days). " + " ".join(r + "." for r in w["reasons"][:3]))
        if w["cautions"]:
            line += " Watch out: " + w["cautions"][0] + "."
        wins.append(line)
    return {"summary": summary, "sections": [
        {"title": "What you need in a partner", "body": need},
        {"title": "Your most compatible horoscopes", "body": signs},
        {"title": "Your best birth-date windows", "body": "\n".join(wins) or "No strong windows in this range."},
    ]}


def match_profile(chart: dict[str, Any], res: dict[str, Any], use_ai: bool = True) -> dict[str, Any]:
    f = chart_facts(chart)
    partner_signs: dict[str, set[str]] = {}
    for w in res["windows"]:
        for key, pid in (("sun_signs", "sun"), ("venus_signs", "venus"), ("mars_signs", "mars"),
                         ("mercury_signs", "mercury"), ("moon_signs_best_dates", "moon")):
            partner_signs.setdefault(pid, set()).update(w[key])
    partner_signs["sun"].update(s["sign"] for s in res["sun_sign_ranking"])
    facts = {"user": {k: f[k] for k in ("placements_checklist", "time_known", "big_three", "placements", "dominant_element",
                                        "dominant_modality")},
             "scan": {"windows": [{k: v for k, v in w.items() if k not in ("from", "to", "best_dates", "peak_date")}
                                  | {"rank": i + 1} for i, w in enumerate(res["windows"])],
                      "sun_sign_ranking": res["sun_sign_ranking"]}}
    return generate(MATCH_PROMPT, facts, chart, match_template(f, res), use_ai, partner_signs)
