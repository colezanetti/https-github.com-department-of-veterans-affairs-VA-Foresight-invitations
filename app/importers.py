"""Manual upload fallbacks: Garmin Connect CSV exports and a simple daily CSV."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime

from .db import HEALTH_FIELDS, Database


def _num(value: str | None):
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value in ("", "--"):
        return None
    try:
        f = float(value)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def _duration(value: str | None) -> float | None:
    """Garmin exports durations like '01:02:03' or '45:10.5'."""
    if not value or value.strip() in ("", "--"):
        return None
    try:
        parts = [float(p) for p in value.strip().split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def _date(value: str) -> str | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def import_csv(db: Database, content: bytes) -> dict:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    lower = {h.lower() for h in headers}

    if "activity type" in lower and "date" in lower:
        return _import_garmin_activities(db, reader)
    if "date" in lower and lower & set(HEALTH_FIELDS):
        return _import_daily(db, reader)
    raise ValueError(
        "Unrecognised CSV. Upload a Garmin Connect activities export, or a daily CSV with a "
        f"'date' column plus any of: {', '.join(HEALTH_FIELDS)}."
    )


def _import_garmin_activities(db: Database, reader: csv.DictReader) -> dict:
    count = 0
    for raw in reader:
        row = {k.strip(): v for k, v in raw.items() if k}
        day = _date(row.get("Date", ""))
        if not day:
            continue
        distance = _num(row.get("Distance"))
        # Garmin exports distance in km/mi per user setting; store as metres assuming km.
        ident = hashlib.sha1(f"{row.get('Date')}|{row.get('Title')}".encode()).hexdigest()[:16]
        db.upsert_activity({
            "id": f"csv-{ident}",
            "date": day,
            "type": (row.get("Activity Type") or "").strip().lower().replace(" ", "_") or None,
            "name": row.get("Title"),
            "duration_s": _duration(row.get("Time") or row.get("Elapsed Time")),
            "distance_m": distance * 1000 if isinstance(distance, (int, float)) else None,
            "avg_hr": _num(row.get("Avg HR")),
            "calories": _num(row.get("Calories")),
            "source": "csv",
        })
        count += 1
    return {"kind": "activities", "rows": count}


def _import_daily(db: Database, reader: csv.DictReader) -> dict:
    count = 0
    for raw in reader:
        row = {k.strip().lower(): v for k, v in raw.items() if k}
        day = _date(row.get("date", ""))
        if not day:
            continue
        metrics = {f: _num(row.get(f)) for f in HEALTH_FIELDS}
        db.upsert_health(day, metrics, source="csv")
        count += 1
    return {"kind": "daily", "rows": count}
