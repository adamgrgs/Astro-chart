"""Major aspects with actual orbs and applying/separating status.

Applying/separating is computed from instantaneous longitudinal speeds (deg/day) of
both points: if the orb |separation − aspect angle| is shrinking the aspect is
`applying`, if growing `separating`. Angles (ASC/MC/...) use their true speeds from
the house calculation, so aspects to angles get a status too. If the orb rate is
below 1e-7 °/day the status is `stationary`; |orb| < 1e-6° is `exact`.
"""
from __future__ import annotations

from typing import Any

from .constants import ASPECTS, FIXED_PAIRS
from .formatting import format_orb


def _delta(a: float, b: float) -> float:
    return ((b - a + 180.0) % 360.0) - 180.0


def aspect_between(pa: dict[str, Any], pb: dict[str, Any], orbs: dict[str, float]) -> dict[str, Any] | None:
    la, lb = pa["longitude"], pb["longitude"]
    d = _delta(la, lb)
    sep = abs(d)
    best = None
    for aid, (label, angle, symbol) in ASPECTS.items():
        limit = orbs.get(aid)
        if limit is None:
            continue
        orb = abs(sep - angle)
        if orb <= limit and (best is None or orb < best[1]):
            best = (aid, orb, angle, label, symbol, limit)
    if not best:
        return None
    aid, orb, angle, label, symbol, limit = best
    va, vb = pa.get("speed_deg_per_day"), pb.get("speed_deg_per_day")
    status, rate = None, None
    if va is not None and vb is not None:
        sign_d = 1.0 if d >= 0 else -1.0
        dsep = sign_d * (vb - va)
        signed_orb = sep - angle
        rate = (1.0 if signed_orb >= 0 else -1.0) * dsep
        if orb < 1e-6:
            status = "exact"
        elif abs(rate) < 1e-7:
            status = "stationary"
        else:
            status = "applying" if rate < 0 else "separating"
    return {
        "a": pa["id"], "b": pb["id"], "a_label": pa["label"], "b_label": pb["label"],
        "type": aid, "label": label, "symbol": symbol, "angle": angle,
        "separation": round(sep, 7), "orb": round(orb, 7), "orb_formatted": format_orb(orb),
        "orb_limit": limit, "status": status,
        "orb_rate_deg_per_day": None if rate is None else round(rate, 7),
    }


def find_aspects(points: dict[str, dict[str, Any]], ids: list[str], orbs: dict[str, float]) -> list[dict[str, Any]]:
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if frozenset((a, b)) in FIXED_PAIRS:
                continue
            asp = aspect_between(points[a], points[b], orbs)
            if asp:
                out.append(asp)
    return out
