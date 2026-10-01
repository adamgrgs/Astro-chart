"""Interpretation + ideal-match tests. No network: the AI writer is stubbed."""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient

from api.index import app
from astrocalc import build_chart, llm
from astrocalc import interpret as I
from astrocalc.match import find_matches

CAIRO = {"date": "1987-07-07", "time": "00:30", "latitude": "30°04′N", "longitude": "31°15′E", "settings": {}}
NY_UNKNOWN = {"date": "1990-01-01", "time_unknown": True, "latitude": 40.7, "longitude": -74.0, "settings": {}}


@pytest.fixture(scope="module")
def cairo():
    return build_chart(dict(CAIRO))


@pytest.fixture(scope="module")
def unknown():
    return build_chart(dict(NY_UNKNOWN))


def test_facts_match_chart(cairo):
    f = I.chart_facts(cairo)
    assert f["big_three"]["sun"]["sign"] == "Cancer" and f["big_three"]["sun"]["house"] == 4
    assert f["big_three"]["moon"]["sign"] == "Scorpio" and f["big_three"]["rising"]["sign"] == "Aries"
    assert f["chart_ruler"]["id"] == "mars" and f["chart_ruler"]["sign"] == "Leo"
    assert {"sign": "Cancer", "planets": ["Sun", "Mercury", "Venus"]} in f["sign_stelliums"]
    assert "Neptune: Capricorn, 9th house, retrograde" in f["placements_checklist"]


def test_template_reading_is_consistent(cairo, unknown):
    for chart in (cairo, unknown):
        r = I.template_reading(I.chart_facts(chart))
        assert r["summary"] and len(r["sections"]) >= 4
        assert I.validate_claims(I._as_text(r), chart) == []
    assert "rising" not in I.template_reading(I.chart_facts(unknown))["summary"]


def test_validator_catches_contradictions(cairo, unknown):
    assert I.validate_claims("Your Sun in Cancer and your Moon in Scorpio, Mars in the 4th house.", cairo) == []
    assert I.validate_claims("Aries rising and a Cancer Sun.", cairo) == []
    bad = I.validate_claims("Your Venus in Leo makes you dramatic.", cairo)
    assert bad and "Venus in Leo" in bad[0]
    assert I.validate_claims("Mars in the 7th house", cairo)
    assert I.validate_claims("Your Sun sits at 14° of Cancer", cairo)
    # one planet's "in <sign>" must not be attributed to an earlier planet name
    assert I.validate_claims("The Moon trines your Sun in Cancer.", cairo) == []
    # unknown time: houses / rising are not allowed
    assert I.validate_claims("Sun in the 10th house", unknown)
    assert I.validate_claims("Your Ascendant in Leo", unknown)


def test_ai_output_rejected_when_wrong(cairo, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    calls = []

    def fake(system, user, max_tokens=2500):
        calls.append(user)
        return {"summary": "You have Venus in Leo.", "sections": [{"title": "x", "body": "Venus in Leo."}]}, "anthropic", "m"
    monkeypatch.setattr(llm, "complete_json", fake)
    out = I.interpret(cairo)
    assert out["reading"]["source"] == "template" and len(calls) == 2
    assert "Correct placements" in calls[1]
    assert out["reading"]["guardrail"]["violations"]


def test_ai_output_accepted_when_consistent(cairo, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(llm, "complete_json", lambda s, u, max_tokens=2500: (
        {"summary": "A Cancer Sun with a Scorpio Moon.", "sections": [{"title": "Core", "body": "Sun in Cancer."}]},
        "anthropic", "m"))
    r = I.interpret(cairo)["reading"]
    assert r["source"] == "ai" and r["guardrail"]["violations"] == []


def test_no_key_uses_template(cairo, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = I.interpret(cairo)["reading"]
    assert r["source"] == "template" and "No AI key" in r["note"]


def test_match_deterministic_and_bounded(cairo):
    a = find_matches(cairo, 10, 10, 6, today=dt.date(2026, 10, 1))
    b = find_matches(cairo, 10, 10, 6, today=dt.date(2026, 10, 1))
    assert a == b
    assert a["search"]["from"] == "1977-01-01" and a["search"]["to"] == "1997-12-31"
    assert len(a["windows"]) == 6 and len(a["sun_sign_ranking"]) == 12
    assert a["windows"][0]["match_strength"] == 100
    for w in a["windows"]:
        assert "1977-01-01" <= w["from"] <= w["to"] <= "1997-12-31" and w["reasons"]
    counts = {}
    for w in a["windows"]:
        counts[w["sun_signs"][0]] = counts.get(w["sun_signs"][0], 0) + 1
    assert max(counts.values()) <= 2
    # never suggests dates after today
    c = find_matches(cairo, 0, 50, 3, today=dt.date(2000, 1, 1))
    assert c["search"]["to"] == "2000-01-01"


def test_match_profile_template(cairo, unknown):
    for chart in (cairo, unknown):
        res = find_matches(chart, 5, 5, 4, today=dt.date(2026, 10, 1))
        p = I.match_profile(chart, res, use_ai=False)
        assert p["source"] == "template" and p["sections"]


def test_api_interpret_and_match(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)
    body = {k: v for k, v in CAIRO.items() if k != "settings"}
    r = client.post("/api/interpret", json=body)
    assert r.status_code == 200 and r.json()["facts"]["big_three"]["sun"]["sign"] == "Cancer"
    r = client.post("/api/match", json={**body, "years_before": 3, "years_after": 3, "top": 3})
    j = r.json()
    assert r.status_code == 200 and len(j["windows"]) == 3 and j["profile"]["sections"] and j["disclaimer"]
    r = client.post("/api/match", json={**body, "years_before": 99})
    assert r.status_code == 422
