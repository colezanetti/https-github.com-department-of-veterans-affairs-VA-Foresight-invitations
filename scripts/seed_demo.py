"""Fill a database with ~4 months of plausible sample data so you can explore the charts.

    STOA_DATA_DIR=./demo-data python -m scripts.seed_demo
"""

import random
from datetime import date, timedelta

from app import stoic
from app.config import load_settings
from app.db import Database


def main(days: int = 120) -> None:
    s = load_settings()
    db = Database(s.db_path)
    db.seed_behaviors(stoic.DEFAULT_BEHAVIORS)
    behaviors = db.list_behaviors()
    rng = random.Random(7)
    today = date.today()
    fitness = 0.0
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        iso = d.isoformat()
        growth = i / days  # practice gets easier over time
        sleep_h = max(4.5, min(9.0, rng.gauss(7.0 + growth * 0.4, 0.8)))
        trained = rng.random() < 0.55
        fitness += 0.02
        hrv = rng.gauss(52 + fitness + (sleep_h - 7) * 3, 4)
        db.upsert_health(iso, {
            "sleep_seconds": int(sleep_h * 3600),
            "sleep_score": int(max(40, min(98, 50 + (sleep_h - 5) * 11 + rng.gauss(0, 5)))),
            "hrv_ms": round(hrv, 1),
            "resting_hr": int(rng.gauss(55 - fitness / 2, 1.5)),
            "body_battery_high": int(max(20, min(100, 40 + (sleep_h - 5) * 14 + rng.gauss(0, 6)))),
            "body_battery_low": int(rng.uniform(10, 30)),
            "stress_avg": int(max(10, rng.gauss(32 - growth * 6, 7))),
            "training_readiness": int(max(5, min(100, 30 + (sleep_h - 5) * 14 + rng.gauss(0, 8)))),
            "steps": int(rng.gauss(9000, 2500)),
            "intensity_minutes": int(rng.uniform(25, 70)) if trained else int(rng.uniform(0, 15)),
            "vo2max": round(48 + fitness / 3, 1),
        }, source="demo")
        if trained:
            db.upsert_activity({"id": f"demo-{iso}", "date": iso, "type": rng.choice(["running", "cycling", "strength_training"]),
                                "name": rng.choice(["Morning Run", "Zone 2 Ride", "Strength"]),
                                "duration_s": rng.uniform(1800, 4200), "distance_m": None, "avg_hr": int(rng.gauss(138, 10)),
                                "calories": int(rng.uniform(300, 800)), "source": "demo"})
        if rng.random() < 0.9:
            p_lapse = max(0.04, 0.35 - growth * 0.2 - (sleep_h - 7) * 0.06)
            db.set_evaluations(iso, {b["id"]: (1 + (rng.random() < 0.25) if rng.random() < p_lapse else 0) for b in behaviors})
            db.save_journal(iso, {
                "morning_intention": "Be patient in meetings and train with intent.",
                "evening_review": "Listened well; let go of the late train.",
                "mood": max(1, min(5, round(rng.gauss(3.2 + (sleep_h - 7) * 0.5 + growth * 0.5, 0.7)))),
                "tranquility": max(1, min(5, round(rng.gauss(3.3 + growth * 0.6, 0.8)))),
                "practice_done": int(rng.random() < 0.6 + growth * 0.3),
            })
    print(f"Seeded {days} days into {s.db_path}")


if __name__ == "__main__":
    main()
