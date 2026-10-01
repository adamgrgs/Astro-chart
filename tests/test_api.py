from fastapi.testclient import TestClient

from api.index import app

client = TestClient(app)


def test_chart_endpoint():
    r = client.post("/api/chart", json={"date": "1987-07-07", "time": "00:30", "place": "Cairo, Egypt",
                                        "latitude": "30°04′N", "longitude": "31°15′E"})
    assert r.status_code == 200 and r.json()["time"]["utc_offset"] == "+03:00"


def test_error_shape():
    r = client.post("/api/chart", json={"date": "2021-11-07", "time": "01:30", "place": "New York, United States"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "AMBIGUOUS_LOCAL_TIME"
    r = client.post("/api/chart", json={"date": "2021-11-07", "time": "01:30", "bogus": 1})
    assert r.status_code == 422


def test_places_meta_health_index():
    r = client.get("/api/places", params={"q": "Cairo"})
    assert r.json()["results"][0]["timezone"] == "Africa/Cairo"
    assert client.get("/api/meta").json()["options"]["default_orbs"]["conjunction"] == 8.0
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/timezone", params={"lat": "30N04", "lon": "31E15"}).json()["timezone"] == "Africa/Cairo"
