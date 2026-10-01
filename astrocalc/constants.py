"""Static definitions: signs, bodies, house systems, ayanamsas, defaults."""
from __future__ import annotations

import swisseph as swe

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
SIGN_ABBR = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]

# id -> (label, swisseph body number)
PLANETS = {
    "sun": ("Sun", swe.SUN), "moon": ("Moon", swe.MOON), "mercury": ("Mercury", swe.MERCURY),
    "venus": ("Venus", swe.VENUS), "mars": ("Mars", swe.MARS), "jupiter": ("Jupiter", swe.JUPITER),
    "saturn": ("Saturn", swe.SATURN), "uranus": ("Uranus", swe.URANUS), "neptune": ("Neptune", swe.NEPTUNE),
    "pluto": ("Pluto", swe.PLUTO), "chiron": ("Chiron", swe.CHIRON),
}
NODE_VARIANTS = {"true": swe.TRUE_NODE, "mean": swe.MEAN_NODE}
LILITH_VARIANTS = {"mean": swe.MEAN_APOG, "osculating": swe.OSCU_APOG, "interpolated": swe.INTP_APOG}

# Stationary threshold: a body is "stationary" when |longitude speed| < threshold (deg/day).
# Values are ~1 day of motion change around a typical station, i.e. the body is within
# roughly one day (Mercury..Mars) to a few days (outer bodies) of turning. Configurable.
STATIONARY_THRESHOLDS = {
    "mercury": 0.10, "venus": 0.03, "mars": 0.012, "jupiter": 0.002, "saturn": 0.001,
    "uranus": 0.0005, "neptune": 0.0003, "pluto": 0.0003, "chiron": 0.0008,
}

HOUSE_SYSTEMS = {
    "placidus": b"P", "whole_sign": b"W", "equal": b"A", "koch": b"K",
    "porphyry": b"O", "regiomontanus": b"R", "campanus": b"C",
}
HOUSE_LABELS = {
    "placidus": "Placidus", "whole_sign": "Whole Sign", "equal": "Equal (from Ascendant)", "koch": "Koch",
    "porphyry": "Porphyry", "regiomontanus": "Regiomontanus", "campanus": "Campanus",
}
# Systems that cannot be constructed inside the polar circles
POLAR_SENSITIVE = {"placidus", "koch"}

AYANAMSAS = {
    "lahiri": swe.SIDM_LAHIRI, "fagan_bradley": swe.SIDM_FAGAN_BRADLEY, "raman": swe.SIDM_RAMAN,
    "krishnamurti": swe.SIDM_KRISHNAMURTI, "yukteshwar": swe.SIDM_YUKTESHWAR, "true_chitra": swe.SIDM_TRUE_CITRA,
    "true_revati": swe.SIDM_TRUE_REVATI, "true_pushya": swe.SIDM_TRUE_PUSHYA, "deluce": swe.SIDM_DELUCE,
    "djwhal_khul": swe.SIDM_DJWHAL_KHUL, "sassanian": swe.SIDM_SASSANIAN, "galactic_center_0sag": swe.SIDM_GALCENT_0SAG,
    "j2000": swe.SIDM_J2000,
}

ASPECTS = {  # id -> (label, angle, symbol)
    "conjunction": ("Conjunction", 0.0, "☌"), "sextile": ("Sextile", 60.0, "⚹"), "square": ("Square", 90.0, "□"),
    "trine": ("Trine", 120.0, "△"), "opposition": ("Opposition", 180.0, "☍"),
}
DEFAULT_ORBS = {"conjunction": 8.0, "opposition": 8.0, "square": 7.0, "trine": 7.0, "sextile": 5.0}
DEFAULT_ASPECT_POINTS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune",
                         "pluto", "chiron", "north_node", "lilith", "asc", "mc"]
ALL_POINT_IDS = list(PLANETS) + ["north_node", "south_node", "lilith", "asc", "mc", "dsc", "ic", "vertex", "fortune"]
TIME_DEPENDENT = {"asc", "mc", "dsc", "ic", "vertex", "fortune"}
# Pairs that are geometrically fixed - never reported as aspects
# ASC–MC (and the other angle pairs) are frame relations, not planetary aspects; Astro-Seek-style
# tables don't list them, so they are excluded too.
FIXED_PAIRS = {frozenset(p) for p in (("asc", "dsc"), ("mc", "ic"), ("north_node", "south_node"),
                                      ("asc", "mc"), ("asc", "ic"), ("dsc", "mc"), ("dsc", "ic"))}

POINT_LABELS = {**{k: v[0] for k, v in PLANETS.items()}, "north_node": "North Node", "south_node": "South Node",
                "lilith": "Lilith", "asc": "Ascendant", "mc": "Midheaven", "dsc": "Descendant", "ic": "Imum Coeli",
                "vertex": "Vertex", "fortune": "Part of Fortune"}
POINT_ABBR = {"asc": "ASC", "mc": "MC", "dsc": "DSC", "ic": "IC", "north_node": "NN", "south_node": "SN"}

# Swiss Ephemeris data files bundled in ./ephe and the Gregorian years they cover.
EPHEMERIS_FILES = [
    ("sepl_12.se1", "semo_12.se1", "seas_12.se1", 1200, 1799),
    ("sepl_18.se1", "semo_18.se1", "seas_18.se1", 1800, 2399),
    ("sepl_24.se1", "semo_24.se1", "seas_24.se1", 2400, 2999),
]
SUPPORTED_YEARS = (1200, 2999)
