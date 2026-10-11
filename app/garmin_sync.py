"""Automatic Garmin Connect pull.

Garmin does not offer a public API to individuals (its Health API is for approved
businesses), so this uses the community `garminconnect` library, which signs in the
way the Garmin Connect app does. After the first sign-in, tokens are cached in the
data directory and refreshed automatically; your password is only needed again if
Garmin invalidates the tokens.
"""

from __future__ import annotations

import logging
import threading
from datetime import date as Date, timedelta
from typing import Any, Callable

from .db import Database

log = logging.getLogger(__name__)


def _get(d: Any, *path, default=None):
    for key in path:
        if isinstance(d, dict):
            d = d.get(key)
        elif isinstance(d, list) and isinstance(key, int) and len(d) > key:
            d = d[key]
        else:
            return default
        if d is None:
            return default
    return d


def parse_day(summary: dict | None, sleep: dict | None, hrv: dict | None,
              readiness: Any, max_metrics: Any, body: dict | None) -> dict:
    """Map Garmin's JSON payloads onto our daily health row."""
    moderate = _get(summary, "moderateIntensityMinutes")
    vigorous = _get(summary, "vigorousIntensityMinutes")
    intensity = None
    if moderate is not None or vigorous is not None:
        # Garmin counts vigorous minutes double toward the weekly goal.
        intensity = (moderate or 0) + 2 * (vigorous or 0)

    readiness_score = None
    if isinstance(readiness, list) and readiness:
        readiness_score = _get(readiness, 0, "score")
    elif isinstance(readiness, dict):
        readiness_score = readiness.get("score")

    vo2 = None
    mm = max_metrics[0] if isinstance(max_metrics, list) and max_metrics else max_metrics
    if isinstance(mm, dict):
        vo2 = _get(mm, "generic", "vo2MaxPreciseValue") or _get(mm, "generic", "vo2MaxValue")

    weight_g = _get(body, "totalAverage", "weight")

    return {
        "steps": _get(summary, "totalSteps"),
        "resting_hr": _get(summary, "restingHeartRate"),
        "stress_avg": _nonneg(_get(summary, "averageStressLevel")),
        "body_battery_high": _get(summary, "bodyBatteryHighestValue"),
        "body_battery_low": _get(summary, "bodyBatteryLowestValue"),
        "active_kcal": _int(_get(summary, "activeKilocalories")),
        "intensity_minutes": intensity,
        "sleep_seconds": _get(sleep, "dailySleepDTO", "sleepTimeSeconds"),
        "sleep_score": _get(sleep, "dailySleepDTO", "sleepScores", "overall", "value"),
        "hrv_ms": _get(hrv, "hrvSummary", "lastNightAvg"),
        "training_readiness": readiness_score,
        "vo2max": vo2,
        "weight_kg": round(weight_g / 1000, 2) if weight_g else None,
    }


def parse_activity(a: dict) -> dict:
    start = a.get("startTimeLocal") or a.get("startTimeGMT") or ""
    return {
        "id": str(a.get("activityId")),
        "date": start[:10],
        "type": _get(a, "activityType", "typeKey"),
        "name": a.get("activityName"),
        "duration_s": a.get("duration"),
        "distance_m": a.get("distance"),
        "avg_hr": _int(a.get("averageHR")),
        "calories": _int(a.get("calories")),
    }


def _int(v):
    return int(round(v)) if isinstance(v, (int, float)) else None


def _nonneg(v):
    # Garmin reports -1 / -2 when there isn't enough data.
    return v if isinstance(v, (int, float)) and v >= 0 else None


def _default_factory(**kwargs):
    from garminconnect import Garmin
    return Garmin(**kwargs)


class GarminService:
    def __init__(self, db: Database, token_dir, email: str = "", password: str = "",
                 client_factory: Callable[..., Any] = _default_factory):
        self.db = db
        self.token_dir = str(token_dir)
        self.email = email
        self.password = password
        self.factory = client_factory
        self._client = None
        self._pending_mfa: tuple[Any, Any] | None = None
        self._lock = threading.Lock()

    # --- auth ------------------------------------------------------------
    def _tokens_exist(self) -> bool:
        from pathlib import Path
        p = Path(self.token_dir)
        return p.exists() and any(p.iterdir())

    def status(self) -> dict:
        return {
            "connected": self._client is not None or self._tokens_exist(),
            "awaiting_mfa": self._pending_mfa is not None,
            "last_sync": self.db.get_kv("garmin_last_sync"),
            "last_error": self.db.get_kv("garmin_last_error"),
        }

    def connect(self, email: str, password: str) -> dict:
        """Sign in with credentials. Returns {'status': 'ok' | 'mfa_required'}."""
        client = self.factory(email=email, password=password, return_on_mfa=True)
        result = client.login()
        if result and result[0] == "needs_mfa":
            self._pending_mfa = (client, result[1])
            return {"status": "mfa_required"}
        self._save(client)
        return {"status": "ok"}

    def submit_mfa(self, code: str) -> dict:
        if not self._pending_mfa:
            raise RuntimeError("No sign-in is waiting for a code. Start again.")
        client, state = self._pending_mfa
        client.resume_login(state, code)
        self._pending_mfa = None
        self._save(client)
        return {"status": "ok"}

    def disconnect(self) -> None:
        import shutil
        self._client = None
        shutil.rmtree(self.token_dir, ignore_errors=True)

    def _save(self, client) -> None:
        from pathlib import Path
        Path(self.token_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        client.client.dump(self.token_dir)
        self._client = client
        self.db.set_kv("garmin_last_error", None)

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self._tokens_exist():
            client = self.factory(email=self.email or None, password=self.password or None)
            client.login(self.token_dir)
        elif self.email and self.password:
            client = self.factory(email=self.email, password=self.password)
            client.login(self.token_dir)
        else:
            raise RuntimeError("Garmin is not connected. Sign in from Settings.")
        self._client = client
        return client

    # --- sync ------------------------------------------------------------
    def sync(self, days: int = 3, end: Date | None = None) -> dict:
        """Pull the last `days` days (re-pulling recent days picks up late sleep/HRV data)."""
        with self._lock:
            end = end or Date.today()
            start = end - timedelta(days=days - 1)
            try:
                client = self._get_client()
                synced = []
                d = start
                while d <= end:
                    iso = d.isoformat()
                    row = parse_day(
                        _safe(client.get_user_summary, iso),
                        _safe(client.get_sleep_data, iso),
                        _safe(client.get_hrv_data, iso),
                        _safe(client.get_training_readiness, iso),
                        _safe(client.get_max_metrics, iso),
                        _safe(client.get_body_composition, iso),
                    )
                    self.db.upsert_health(iso, row, source="garmin")
                    synced.append(iso)
                    d += timedelta(days=1)
                acts = _safe(client.get_activities_by_date, start.isoformat(), end.isoformat()) or []
                for a in acts:
                    parsed = parse_activity(a)
                    if parsed["id"] and parsed["date"]:
                        self.db.upsert_activity(parsed)
                from datetime import datetime
                self.db.set_kv("garmin_last_sync", datetime.now().isoformat(timespec="seconds"))
                self.db.set_kv("garmin_last_error", None)
                return {"days": synced, "activities": len(acts)}
            except Exception as exc:  # surfaced in the UI
                self._client = None
                self.db.set_kv("garmin_last_error", str(exc))
                raise


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        log.warning("Garmin call %s failed: %s", getattr(fn, "__name__", fn), exc)
        if "auth" in type(exc).__name__.lower():
            raise
        return None
