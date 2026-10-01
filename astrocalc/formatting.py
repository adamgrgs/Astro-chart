"""Deterministic degree formatting.

Convention (same as most astrology software): degrees and minutes are TRUNCATED,
never rounded, so 13°25′59.9″ displays as 13°25′ and a point at 29°59′59.9″ stays in
its sign. Arcseconds are truncated to whole seconds in `dms`.
"""
from __future__ import annotations

import math

from .constants import SIGN_ABBR, SIGNS


def _split(value: float) -> tuple[int, int, int]:
    # round to micro-arcseconds first so binary noise (e.g. 29.999999999998) can't flip a digit
    total = math.floor(round(abs(value) * 3600.0, 6))
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return int(d), int(m), int(s)


def sign_of(lon: float) -> dict:
    lon %= 360.0
    total = math.floor(round(lon * 3600.0, 6))
    idx = int(total // (30 * 3600)) % 12
    in_sign = lon - idx * 30.0
    if in_sign < 0:
        in_sign = 0.0
    d, m, s = _split(in_sign)
    return {"sign": SIGNS[idx], "sign_index": idx, "sign_abbr": SIGN_ABBR[idx],
            "degree_in_sign": round(in_sign, 7), "deg": d, "min": m, "sec": s,
            "dms": f"{d}°{m:02d}′{s:02d}″ {SIGNS[idx]}"}


def format_lon(lon: float, with_sign: bool = True) -> str:
    if not with_sign:
        d, m, s = _split(lon)
        return f"{'-' if lon < 0 else ''}{d}°{m:02d}′{s:02d}″"
    info = sign_of(lon)
    return f"{info['deg']}°{info['min']:02d}′ {info['sign']}"


def format_orb(orb: float) -> str:
    d, m, _ = _split(orb)
    return f"{d}°{m:02d}′"
