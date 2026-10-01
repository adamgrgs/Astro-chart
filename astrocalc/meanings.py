"""Fixed interpretive vocabulary (plain English).

These are the ONLY symbolic meanings the deterministic template reading uses, and they are
passed to the AI writer as context. They describe themes; they never contain positions -
positions always come from the Swiss Ephemeris calculation.
"""
from __future__ import annotations

ELEMENT = {s: e for e, signs in {
    "fire": ("Aries", "Leo", "Sagittarius"), "earth": ("Taurus", "Virgo", "Capricorn"),
    "air": ("Gemini", "Libra", "Aquarius"), "water": ("Cancer", "Scorpio", "Pisces")}.items() for s in signs}
MODALITY = {s: m for m, signs in {
    "cardinal": ("Aries", "Cancer", "Libra", "Capricorn"), "fixed": ("Taurus", "Leo", "Scorpio", "Aquarius"),
    "mutable": ("Gemini", "Virgo", "Sagittarius", "Pisces")}.items() for s in signs}

# Modern rulers (traditional ruler in brackets is noted in METHODS.md)
RULER = {"Aries": "mars", "Taurus": "venus", "Gemini": "mercury", "Cancer": "moon", "Leo": "sun",
         "Virgo": "mercury", "Libra": "venus", "Scorpio": "pluto", "Sagittarius": "jupiter",
         "Capricorn": "saturn", "Aquarius": "uranus", "Pisces": "neptune"}

ELEMENT_TEXT = {
    "fire": "drive, enthusiasm and a need to act on instinct",
    "earth": "practical sense, patience and a need for tangible results",
    "air": "ideas, conversation and a need for mental connection",
    "water": "feeling, intuition and a need for emotional depth",
}
MODALITY_TEXT = {
    "cardinal": "starting things and taking the initiative",
    "fixed": "staying power, loyalty and finishing what you start",
    "mutable": "adaptability, curiosity and going with the flow",
}

SIGN_STYLE = {
    "Aries": "bold, direct and quick to act", "Taurus": "steady, sensual and loyal",
    "Gemini": "curious, talkative and quick-witted", "Cancer": "protective, caring and deeply feeling",
    "Leo": "warm, expressive and proud", "Virgo": "precise, helpful and observant",
    "Libra": "diplomatic, charming and fairness-minded", "Scorpio": "intense, private and all-or-nothing",
    "Sagittarius": "adventurous, candid and freedom-loving", "Capricorn": "ambitious, disciplined and responsible",
    "Aquarius": "independent, original and future-minded", "Pisces": "imaginative, empathetic and gentle",
}

PLANET_THEME = {
    "sun": "your core identity and what makes you feel alive",
    "moon": "your emotional needs and what makes you feel safe",
    "mercury": "how you think, learn and communicate",
    "venus": "how you love, what you value and what you find beautiful",
    "mars": "how you go after what you want, and how you handle anger",
    "jupiter": "where you grow, find luck and feel generous",
    "saturn": "where you face tests, build discipline and earn lasting results",
    "uranus": "where you break rules and need freedom",
    "neptune": "where you dream, idealise and seek something greater",
    "pluto": "where you go through deep change and find hidden power",
    "chiron": "an old wound that can become your gift for helping others",
    "north_node": "the direction of growth this life seems to ask of you",
    "south_node": "familiar comfort zones you are learning to move beyond",
    "lilith": "the raw, untamed side you may have learned to hide",
    "asc": "the first impression you make and your instinctive approach to life",
    "mc": "your public image, career direction and reputation",
    "fortune": "where ease and wellbeing come most naturally",
    "vertex": "fated-feeling encounters",
}

HOUSE_AREA = {
    1: "self-image and how you come across", 2: "money, possessions and self-worth",
    3: "communication, siblings and your local world", 4: "home, family and roots",
    5: "romance, creativity, play and children", 6: "daily work, routines and health habits",
    7: "partnerships and close one-to-one relationships", 8: "intimacy, shared resources and transformation",
    9: "travel, beliefs, higher learning and big-picture meaning", 10: "career, ambition and public life",
    11: "friends, communities and future goals", 12: "solitude, the unconscious and quiet inner work",
}

ASPECT_TEXT = {
    "conjunction": ("blends with", "these two energies act as one - powerful, for better or worse"),
    "opposition": ("pulls against", "a push-pull you learn to balance; often shows up through other people"),
    "square": ("clashes with", "friction that creates pressure - and, worked with, real achievement"),
    "trine": ("flows easily with", "a natural talent that comes without effort"),
    "sextile": ("supports", "an opportunity that pays off when you act on it"),
}

DISCLAIMER = ("Astrology is a symbolic, reflective practice for entertainment and self-reflection. It is not "
              "scientifically validated and should not guide medical, legal, financial or relationship decisions.")
