"""SQLite storage. One file, one user, no ORM."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS behaviors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    virtue      TEXT NOT NULL,           -- wisdom | courage | justice | temperance
    franklin    TEXT NOT NULL,           -- Franklin virtue it descends from
    title       TEXT NOT NULL,
    question    TEXT NOT NULL,           -- the evening self-examination question
    active      INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

-- Franklin marked a dot for each fault. We store a lapse count per behavior per day
-- (0 = clean). A missing row means "not evaluated".
CREATE TABLE IF NOT EXISTS evaluations (
    date        TEXT NOT NULL,
    behavior_id INTEGER NOT NULL REFERENCES behaviors(id) ON DELETE CASCADE,
    lapses      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, behavior_id)
);

CREATE TABLE IF NOT EXISTS journal (
    date              TEXT PRIMARY KEY,
    morning_intention TEXT NOT NULL DEFAULT '',  -- "What good shall I do this day?"
    evening_review    TEXT NOT NULL DEFAULT '',  -- "What good have I done today?"
    gratitude         TEXT NOT NULL DEFAULT '',
    premeditatio      TEXT NOT NULL DEFAULT '',  -- obstacles anticipated
    mood              INTEGER,                   -- 1-5
    tranquility       INTEGER,                   -- 1-5
    practice_done     INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS health_daily (
    date                TEXT PRIMARY KEY,
    steps               INTEGER,
    resting_hr          INTEGER,
    hrv_ms              REAL,
    sleep_seconds       INTEGER,
    sleep_score         INTEGER,
    body_battery_high   INTEGER,
    body_battery_low    INTEGER,
    stress_avg          INTEGER,
    training_readiness  INTEGER,
    vo2max              REAL,
    intensity_minutes   INTEGER,
    active_kcal         INTEGER,
    weight_kg           REAL,
    source              TEXT NOT NULL DEFAULT 'manual',
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activities (
    id            TEXT PRIMARY KEY,
    date          TEXT NOT NULL,
    type          TEXT,
    name          TEXT,
    duration_s    REAL,
    distance_m    REAL,
    avg_hr        INTEGER,
    calories      INTEGER,
    source        TEXT NOT NULL DEFAULT 'garmin'
);
CREATE INDEX IF NOT EXISTS activities_date ON activities(date);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

HEALTH_FIELDS = [
    "steps", "resting_hr", "hrv_ms", "sleep_seconds", "sleep_score",
    "body_battery_high", "body_battery_low", "stress_avg", "training_readiness",
    "vo2max", "intensity_minutes", "active_kcal", "weight_kg",
]

JOURNAL_FIELDS = [
    "morning_intention", "evening_review", "gratitude", "premeditatio",
    "mood", "tranquility", "practice_done",
]


class Database:
    def __init__(self, path: Path | str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- key/value -------------------------------------------------------
    def get_kv(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_kv(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO kv(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    # --- behaviors -------------------------------------------------------
    def seed_behaviors(self, defaults: list[dict]) -> None:
        with self.connect() as conn:
            if conn.execute("SELECT COUNT(*) FROM behaviors").fetchone()[0]:
                return
            for i, b in enumerate(defaults):
                conn.execute(
                    "INSERT INTO behaviors(virtue, franklin, title, question, sort_order) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (b["virtue"], b["franklin"], b["title"], b["question"], i),
                )

    def list_behaviors(self, include_inactive: bool = False) -> list[dict]:
        sql = "SELECT * FROM behaviors"
        if not include_inactive:
            sql += " WHERE active = 1"
        sql += " ORDER BY sort_order, id"
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql)]

    def upsert_behavior(self, data: dict) -> dict:
        with self.connect() as conn:
            if data.get("id"):
                conn.execute(
                    "UPDATE behaviors SET virtue=?, franklin=?, title=?, question=?, "
                    "active=?, sort_order=? WHERE id=?",
                    (data["virtue"], data["franklin"], data["title"], data["question"],
                     int(data.get("active", 1)), int(data.get("sort_order", 0)), data["id"]),
                )
                bid = data["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO behaviors(virtue, franklin, title, question, sort_order) "
                    "VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM behaviors))",
                    (data["virtue"], data["franklin"], data["title"], data["question"]),
                )
                bid = cur.lastrowid
            return dict(conn.execute("SELECT * FROM behaviors WHERE id=?", (bid,)).fetchone())

    def delete_behavior(self, behavior_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM behaviors WHERE id = ?", (behavior_id,))

    # --- evaluations -----------------------------------------------------
    def set_evaluations(self, date: str, lapses: dict[int, int]) -> None:
        with self.connect() as conn:
            for bid, count in lapses.items():
                conn.execute(
                    "INSERT INTO evaluations(date, behavior_id, lapses) VALUES (?, ?, ?) "
                    "ON CONFLICT(date, behavior_id) DO UPDATE SET lapses = excluded.lapses",
                    (date, int(bid), max(0, int(count))),
                )

    def evaluations_between(self, start: str, end: str) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT e.date, e.behavior_id, e.lapses, b.virtue, b.franklin "
                "FROM evaluations e JOIN behaviors b ON b.id = e.behavior_id "
                "WHERE e.date BETWEEN ? AND ? ORDER BY e.date",
                (start, end),
            )]

    # --- journal ---------------------------------------------------------
    def get_journal(self, date: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM journal WHERE date = ?", (date,)).fetchone()
        if row:
            return dict(row)
        return {"date": date, **{f: ("" if f not in ("mood", "tranquility", "practice_done") else None)
                                 for f in JOURNAL_FIELDS}, "practice_done": 0}

    def save_journal(self, date: str, data: dict) -> dict:
        current = self.get_journal(date)
        current.update({k: v for k, v in data.items() if k in JOURNAL_FIELDS})
        current["practice_done"] = int(bool(current.get("practice_done")))
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO journal(date, {', '.join(JOURNAL_FIELDS)}, updated_at) "
                f"VALUES (?, {', '.join('?' for _ in JOURNAL_FIELDS)}, datetime('now')) "
                f"ON CONFLICT(date) DO UPDATE SET "
                + ", ".join(f"{f} = excluded.{f}" for f in JOURNAL_FIELDS)
                + ", updated_at = excluded.updated_at",
                (date, *[current.get(f) for f in JOURNAL_FIELDS]),
            )
        return self.get_journal(date)

    def journals_between(self, start: str, end: str) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM journal WHERE date BETWEEN ? AND ? ORDER BY date", (start, end)
            )]

    # --- health ----------------------------------------------------------
    def upsert_health(self, date: str, metrics: dict, source: str) -> None:
        """Merge non-null metrics into the day's row (never blank out existing data)."""
        clean = {k: v for k, v in metrics.items() if k in HEALTH_FIELDS and v is not None}
        if not clean:
            return
        cols = list(clean)
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO health_daily(date, {', '.join(cols)}, source, updated_at) "
                f"VALUES (?, {', '.join('?' for _ in cols)}, ?, datetime('now')) "
                f"ON CONFLICT(date) DO UPDATE SET "
                + ", ".join(f"{c} = excluded.{c}" for c in cols)
                + ", source = excluded.source, updated_at = excluded.updated_at",
                (date, *[clean[c] for c in cols], source),
            )

    def get_health(self, date: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM health_daily WHERE date = ?", (date,)).fetchone()
        return dict(row) if row else None

    def health_between(self, start: str, end: str) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM health_daily WHERE date BETWEEN ? AND ? ORDER BY date", (start, end)
            )]

    def upsert_activity(self, act: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO activities(id, date, type, name, duration_s, distance_m, avg_hr, calories, source) "
                "VALUES (:id, :date, :type, :name, :duration_s, :distance_m, :avg_hr, :calories, :source) "
                "ON CONFLICT(id) DO UPDATE SET date=excluded.date, type=excluded.type, name=excluded.name, "
                "duration_s=excluded.duration_s, distance_m=excluded.distance_m, avg_hr=excluded.avg_hr, "
                "calories=excluded.calories",
                {"source": "garmin", **act},
            )

    def activities_between(self, start: str, end: str) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM activities WHERE date BETWEEN ? AND ? ORDER BY date", (start, end)
            )]

    # --- export / import -------------------------------------------------
    def export_all(self) -> dict:
        out = {}
        with self.connect() as conn:
            for table in ("behaviors", "evaluations", "journal", "health_daily", "activities"):
                out[table] = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
        return out

    def import_all(self, payload: dict) -> dict[str, int]:
        counts = {}
        with self.connect() as conn:
            for table in ("behaviors", "evaluations", "journal", "health_daily", "activities"):
                rows = payload.get(table) or []
                valid = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
                for row in rows:
                    row = {k: v for k, v in row.items() if k in valid}
                    if not row:
                        continue
                    cols = list(row)
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table}({', '.join(cols)}) "
                        f"VALUES ({', '.join('?' for _ in cols)})",
                        [row[c] for c in cols],
                    )
                counts[table] = len(rows)
        return counts
