"""Turn stored rows into daily scores, trends, and correlations."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date as Date, timedelta

from . import stoic
from .db import Database


def _days(start: Date, end: Date) -> list[str]:
    n = (end - start).days
    return [(start + timedelta(days=i)).isoformat() for i in range(n + 1)]


def hrv_baseline(db: Database, day: Date, window: int = 30) -> float | None:
    rows = db.health_between((day - timedelta(days=window)).isoformat(),
                             (day - timedelta(days=1)).isoformat())
    vals = [r["hrv_ms"] for r in rows if r.get("hrv_ms")]
    return sum(vals) / len(vals) if len(vals) >= 5 else None


def virtue_adherence(evals: list[dict]) -> dict[str, float | None]:
    """Share of evaluated behaviors that were kept clean (0 lapses), per virtue."""
    totals, clean = defaultdict(int), defaultdict(int)
    for e in evals:
        totals[e["virtue"]] += 1
        clean[e["virtue"]] += 1 if e["lapses"] == 0 else 0
    out = {v: (round(clean[v] / totals[v] * 100, 1) if totals[v] else None) for v in stoic.VIRTUES}
    all_t = sum(totals.values())
    out["overall"] = round(sum(clean.values()) / all_t * 100, 1) if all_t else None
    return out


def weakest_virtue(db: Database, day: Date, window: int = 14) -> str | None:
    evals = db.evaluations_between((day - timedelta(days=window)).isoformat(),
                                   (day - timedelta(days=1)).isoformat())
    if len(evals) < 10:
        return None
    rate = {}
    totals = defaultdict(int)
    lapses = defaultdict(int)
    for e in evals:
        totals[e["virtue"]] += 1
        lapses[e["virtue"]] += e["lapses"]
    for v, t in totals.items():
        rate[v] = lapses[v] / t
    worst = max(rate, key=rate.get)
    return worst if rate[worst] > 0 else None


def pillars(health: dict | None, journal: dict | None,
            activities: list[dict], evaluated: int, total_behaviors: int,
            baseline: float | None) -> dict:
    return {
        "philosophy": stoic.philosophy_score(journal, evaluated, total_behaviors),
        "exercise": stoic.exercise_score(health, activities),
        "rest": stoic.rest_score(health),
        "recovery": stoic.recovery_score(health, baseline),
    }


def pearson(xs: list, ys: list) -> tuple[float | None, int]:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 7:
        return None, n
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sx = math.sqrt(sum((p[0] - mx) ** 2 for p in pairs))
    sy = math.sqrt(sum((p[1] - my) ** 2 for p in pairs))
    if not sx or not sy:
        return None, n
    r = sum((p[0] - mx) * (p[1] - my) for p in pairs) / (sx * sy)
    return round(r, 2), n


def trends(db: Database, end: Date, days: int) -> dict:
    start = end - timedelta(days=days - 1)
    s, e = start.isoformat(), end.isoformat()
    dates = _days(start, end)
    behaviors = db.list_behaviors()
    n_beh = len(behaviors)

    evals_by_day = defaultdict(list)
    for ev in db.evaluations_between(s, e):
        evals_by_day[ev["date"]].append(ev)
    health = {h["date"]: h for h in db.health_between(s, e)}
    journal = {j["date"]: j for j in db.journals_between(s, e)}
    acts_by_day = defaultdict(list)
    for a in db.activities_between(s, e):
        acts_by_day[a["date"]].append(a)

    # HRV baseline: trailing 30-day mean, computed once across the window plus lead-in.
    lead = db.health_between((start - timedelta(days=30)).isoformat(), e)
    hrv_series = {r["date"]: r["hrv_ms"] for r in lead if r.get("hrv_ms")}

    def baseline_for(d: str):
        dd = Date.fromisoformat(d)
        vals = [v for k, v in hrv_series.items()
                if (dd - timedelta(days=30)).isoformat() <= k < d]
        return sum(vals) / len(vals) if len(vals) >= 5 else None

    rows = []
    for d in dates:
        h = health.get(d)
        ev = evals_by_day.get(d, [])
        adherence = virtue_adherence(ev)
        p = pillars(h, journal.get(d), acts_by_day.get(d, []), len(ev), n_beh, baseline_for(d))
        rows.append({
            "date": d,
            "focus": stoic.focus_for(Date.fromisoformat(d))["franklin"],
            "lapses": sum(x["lapses"] for x in ev) if ev else None,
            "evaluated": len(ev),
            "adherence": adherence,
            "pillars": p,
            "mood": (journal.get(d) or {}).get("mood"),
            "tranquility": (journal.get(d) or {}).get("tranquility"),
            "health": {k: (h or {}).get(k) for k in (
                "steps", "resting_hr", "hrv_ms", "sleep_seconds", "sleep_score",
                "body_battery_high", "stress_avg", "training_readiness", "vo2max",
                "intensity_minutes", "weight_kg")},
            "activity_minutes": round(sum((a.get("duration_s") or 0) for a in acts_by_day.get(d, [])) / 60, 1),
        })

    # Does the body move the character? Same-day and next-day relationships.
    overall = [r["adherence"]["overall"] for r in rows]
    mood = [r["mood"] for r in rows]
    sleep_h = [r["health"]["sleep_seconds"] / 3600 if r["health"]["sleep_seconds"] else None for r in rows]
    recovery = [r["pillars"]["recovery"] for r in rows]
    exercise = [r["pillars"]["exercise"] for r in rows]
    prev = lambda xs: [None] + xs[:-1]  # noqa: E731  yesterday's value aligned to today
    correlations = []
    for label, xs, ys in [
        ("Sleep (h) → virtue adherence", sleep_h, overall),
        ("Recovery → virtue adherence", recovery, overall),
        ("Exercise → mood", exercise, mood),
        ("Sleep (h) → mood", sleep_h, mood),
        ("Yesterday's exercise → today's adherence", prev(exercise), overall),
        ("Virtue adherence → mood", overall, mood),
    ]:
        r, n = pearson(xs, ys)
        correlations.append({"label": label, "r": r, "n": n})

    # Franklin's table: lapses per Franklin virtue across the window.
    by_franklin = defaultdict(lambda: {"lapses": 0, "evaluated": 0})
    for ev_list in evals_by_day.values():
        for ev in ev_list:
            by_franklin[ev["franklin"]]["lapses"] += ev["lapses"]
            by_franklin[ev["franklin"]]["evaluated"] += 1

    return {
        "start": s, "end": e, "days": rows,
        "correlations": correlations,
        "franklin_totals": [{"franklin": k, "virtue": stoic.FRANKLIN_BY_NAME.get(k, ("", ""))[0], **v}
                            for k, v in sorted(by_franklin.items())],
        "summary": _summary(rows),
    }


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _summary(rows: list[dict]) -> dict:
    half = len(rows) // 2
    first, second = rows[:half], rows[half:]
    out = {}
    for key in ("overall",) + tuple(stoic.VIRTUES):
        a = _avg([r["adherence"][key] for r in first])
        b = _avg([r["adherence"][key] for r in second])
        out[key] = {"current": b, "previous": a,
                    "delta": round(b - a, 1) if a is not None and b is not None else None}
    for key in ("philosophy", "exercise", "rest", "recovery"):
        a = _avg([r["pillars"][key] for r in first])
        b = _avg([r["pillars"][key] for r in second])
        out[key] = {"current": b, "previous": a,
                    "delta": round(b - a, 1) if a is not None and b is not None else None}
    streak = 0
    for r in reversed(rows):
        if r["evaluated"]:
            streak += 1
        elif r is rows[-1]:
            continue  # today not yet reviewed doesn't break the streak
        else:
            break
    out["review_streak"] = streak
    return out
