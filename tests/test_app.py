from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import stoic
from app.config import Settings
from app.garmin_sync import parse_activity, parse_day
from app.gcal import classify, opportunities
from app.main import create_app


def make_settings(tmp_path, password=""):
    return Settings(
        data_dir=tmp_path, app_password=password, secret_key="test-secret",
        timezone="America/New_York", garmin_email="", garmin_password="", garmin_sync_hour=6,
        google_client_id="", google_client_secret="", google_redirect_uri="http://x/cb",
        google_calendar_write=False, public_url="http://localhost:8000",
    )


class FakeGarmin:
    """Stands in for garminconnect.Garmin with realistic payload shapes."""

    instances = []

    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.mfa = return_on_mfa and email == "mfa@example.com"
        self.client = self
        FakeGarmin.instances.append(self)

    def login(self, tokenstore=None):
        return ("needs_mfa", {"state": 1}) if self.mfa else (None, None)

    def resume_login(self, state, code):
        assert code == "123456"
        return None, None

    def dump(self, path):
        import pathlib
        pathlib.Path(path, "tokens.json").write_text("{}")

    def get_user_summary(self, d):
        return {"totalSteps": 9100, "restingHeartRate": 52, "averageStressLevel": 28,
                "bodyBatteryHighestValue": 82, "bodyBatteryLowestValue": 20,
                "moderateIntensityMinutes": 20, "vigorousIntensityMinutes": 10, "activeKilocalories": 610.4}

    def get_sleep_data(self, d):
        return {"dailySleepDTO": {"sleepTimeSeconds": 7 * 3600, "sleepScores": {"overall": {"value": 81}}}}

    def get_hrv_data(self, d):
        return {"hrvSummary": {"lastNightAvg": 58}}

    def get_training_readiness(self, d):
        return [{"score": 74}]

    def get_max_metrics(self, d):
        return [{"generic": {"vo2MaxPreciseValue": 51.3}}]

    def get_body_composition(self, d):
        return {"totalAverage": {"weight": 78500}}

    def get_activities_by_date(self, s, e):
        return [{"activityId": 1, "activityName": "Morning Run", "activityType": {"typeKey": "running"},
                 "startTimeLocal": f"{e} 06:30:00", "duration": 2700.0, "distance": 8000.0,
                 "averageHR": 148.2, "calories": 600}]


@pytest.fixture
def client(tmp_path):
    app = create_app(make_settings(tmp_path), garmin_factory=FakeGarmin, start_scheduler=False)
    with TestClient(app) as c:
        yield c


def test_focus_cycles_through_franklins_13_virtues():
    weeks = [stoic.focus_for(stoic.CYCLE_EPOCH + timedelta(weeks=i))["franklin"] for i in range(14)]
    assert weeks[0] == "Temperance" and weeks[1] == "Silence" and weeks[13] == "Temperance"
    assert len(set(weeks[:13])) == 13


def test_every_franklin_virtue_maps_to_a_stoic_virtue():
    assert {v for _, v, _ in stoic.FRANKLIN} == set(stoic.VIRTUES)
    assert all(q["virtue"] in stoic.VIRTUES and q["practice"] for q in stoic.QUOTES)


def test_low_recovery_steers_toward_rest():
    tired = {"training_readiness": 20, "body_battery_high": 30, "stress_avg": 60, "sleep_seconds": 5 * 3600}
    ins = stoic.daily_insight(date(2026, 3, 2), tired, None, None)
    assert ins["state"] == "recover"
    assert ins["quote"]["virtue"] == "temperance"
    kinds = [r["kind"] for r in ins["recommendations"]]
    assert "rest" in kinds


def test_parse_garmin_day():
    g = FakeGarmin()
    row = parse_day(g.get_user_summary(""), g.get_sleep_data(""), g.get_hrv_data(""),
                    g.get_training_readiness(""), g.get_max_metrics(""), g.get_body_composition(""))
    assert row["intensity_minutes"] == 40
    assert row["sleep_score"] == 81 and row["hrv_ms"] == 58 and row["vo2max"] == 51.3
    assert row["weight_kg"] == 78.5 and row["active_kcal"] == 610
    assert parse_day({"averageStressLevel": -1}, None, None, None, None, None)["stress_avg"] is None
    act = parse_activity(g.get_activities_by_date("", "2026-01-02")[0])
    assert act["date"] == "2026-01-02" and act["type"] == "running" and act["avg_hr"] == 148


def test_today_journal_and_evaluations(client):
    d = "2026-05-04"
    today = client.get(f"/api/today?date={d}").json()
    assert len(today["behaviors"]) == len(stoic.DEFAULT_BEHAVIORS)
    assert today["insight"]["focus"]["virtue"] in stoic.VIRTUES

    client.put(f"/api/journal/{d}", json={"morning_intention": "Be patient", "mood": 4})
    client.put(f"/api/journal/{d}", json={"evening_review": "Helped a colleague"})
    j = client.get(f"/api/today?date={d}").json()["journal"]
    assert j["morning_intention"] == "Be patient" and j["evening_review"] == "Helped a colleague" and j["mood"] == 4

    ids = [b["id"] for b in today["behaviors"]]
    r = client.put(f"/api/evaluations/{d}", json={"lapses": {str(ids[0]): 0, str(ids[1]): 2}}).json()
    assert r == {str(ids[0]): 0, str(ids[1]): 2}
    week = client.get(f"/api/week?start={d}").json()
    assert week["start"] == "2026-05-04" and week["grid"][str(ids[1])][d] == 2


def test_garmin_connect_with_mfa_then_sync(client):
    assert client.post("/api/garmin/connect", json={"email": "mfa@example.com", "password": "x"}).json() == {"status": "mfa_required"}
    assert client.get("/api/garmin/status").json()["awaiting_mfa"] is True
    assert client.post("/api/garmin/mfa", json={"code": "123456"}).json() == {"status": "ok"}
    res = client.post("/api/garmin/sync?days=3").json()
    assert len(res["days"]) == 3 and res["activities"] == 1
    status = client.get("/api/garmin/status").json()
    assert status["connected"] and status["last_sync"]
    today = client.get("/api/today").json()
    assert today["health"]["sleep_score"] == 81 and today["pillars"]["exercise"] == 100.0


def test_trends_and_correlations(client):
    end = date(2026, 6, 30)
    ids = [b["id"] for b in client.get("/api/behaviors").json()]
    for i in range(30):
        d = (end - timedelta(days=29 - i)).isoformat()
        sleep_h = 5 + (i % 4)
        client.put(f"/api/health/{d}", json={"sleep_seconds": sleep_h * 3600, "hrv_ms": 50 + i % 5})
        # Better sleep -> fewer lapses
        client.put(f"/api/evaluations/{d}", json={"lapses": {str(b): (1 if k >= sleep_h + 3 else 0) for k, b in enumerate(ids)}})
        client.put(f"/api/journal/{d}", json={"mood": sleep_h - 4})
    t = client.get(f"/api/trends?days=30&end={end}").json()
    assert len(t["days"]) == 30
    corr = {c["label"]: c["r"] for c in t["correlations"]}
    assert corr["Sleep (h) → virtue adherence"] > 0.9
    assert corr["Sleep (h) → mood"] == 1.0
    assert t["summary"]["review_streak"] == 30
    assert {x["franklin"] for x in t["franklin_totals"]} >= {"Order", "Temperance"}


def test_csv_upload(client):
    daily = b"date,steps,sleep_seconds,resting_hr\n2026-02-01,8000,27000,55\n"
    assert client.post("/api/upload", files={"file": ("d.csv", daily)}).json() == {"kind": "daily", "rows": 1}
    acts = b'Activity Type,Date,Title,Distance,Calories,Time,Avg HR\nRunning,2026-02-01 07:00:00,"Easy Run",5.01,350,00:28:30,141\n'
    assert client.post("/api/upload", files={"file": ("a.csv", acts)}).json() == {"kind": "activities", "rows": 1}
    day = client.get("/api/today?date=2026-02-01").json()
    assert day["health"]["steps"] == 8000 and day["activities"][0]["duration_s"] == 1710
    assert client.post("/api/upload", files={"file": ("x.csv", b"a,b\n1,2\n")}).status_code == 400


def test_export_import_roundtrip(client, tmp_path):
    client.put("/api/journal/2026-01-01", json={"gratitude": "Morning light"})
    dump = client.get("/api/export").json()
    other = create_app(make_settings(tmp_path / "other"), garmin_factory=FakeGarmin, start_scheduler=False)
    with TestClient(other) as c2:
        c2.post("/api/import", json=dump)
        assert c2.get("/api/today?date=2026-01-01").json()["journal"]["gratitude"] == "Morning light"


def test_password_gate(tmp_path):
    app = create_app(make_settings(tmp_path, password="hunter2"), garmin_factory=FakeGarmin, start_scheduler=False)
    with TestClient(app) as c:
        assert c.get("/api/today").status_code == 401
        assert c.get("/api/session").json() == {"authenticated": False, "password_required": True}
        assert c.post("/api/login", json={"password": "nope"}).status_code == 401
        assert c.post("/api/login", json={"password": "hunter2"}).status_code == 200
        assert c.get("/api/today").status_code == 200
        assert c.get("/").status_code == 200


def test_calendar_classification_and_open_windows():
    assert classify("Quarterly performance review")["virtue"] == "courage"
    assert classify("1:1 with Sam")["virtue"] == "justice"
    assert classify("Dinner with friends")["virtue"] == "temperance"
    assert classify("Dentist") ["virtue"] == "wisdom"
    assert classify("Pick up dry cleaning") is None

    tz = ZoneInfo("America/New_York")
    def ev(h1, m1, h2, m2, s):
        return {"summary": s, "start": {"dateTime": datetime(2026, 3, 3, h1, m1, tzinfo=tz).isoformat()},
                "end": {"dateTime": datetime(2026, 3, 3, h2, m2, tzinfo=tz).isoformat()}}
    events = [ev(9, 0, 10, 0, "Standup"), ev(10, 0, 11, 0, "Design review"), ev(11, 5, 12, 0, "Team sync"),
              ev(15, 0, 16, 0, "Gym")]
    out = opportunities(events, "America/New_York", now=datetime(2026, 3, 3, 6, 0, tzinfo=tz))
    kinds = [e["kind"] for e in out["events"]]
    assert "Heavy stretch" in kinds
    windows = [(w["start"][11:16], w["minutes"]) for w in out["open_windows"]]
    assert ("07:00", 120) in windows and ("12:00", 180) in windows and ("16:00", 300) in windows
