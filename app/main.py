"""Stoa: a daily Stoic practice, Franklin's self-examination, and Garmin health data in one place."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import analytics, auth, stoic
from .config import Settings, load_settings
from .db import HEALTH_FIELDS, Database
from .garmin_sync import GarminService, _default_factory
from .gcal import CalendarService, opportunities
from .importers import import_csv

log = logging.getLogger("stoa")
STATIC = Path(__file__).parent / "static"
PUBLIC_PATHS = {"/api/login", "/api/session", "/manifest.webmanifest", "/sw.js", "/"}


def create_app(settings: Settings | None = None, garmin_factory=None,
               start_scheduler: bool = True) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.db_path)
    db.seed_behaviors(stoic.DEFAULT_BEHAVIORS)
    garmin = GarminService(db, settings.garmin_token_dir, settings.garmin_email,
                           settings.garmin_password, garmin_factory or _default_factory)
    calendar = CalendarService(settings)
    tz = ZoneInfo(settings.timezone)

    def today() -> Date:
        return datetime.now(tz).date()

    @asynccontextmanager
    async def lifespan(_app):
        scheduler = _start_scheduler(settings, garmin, today) if start_scheduler else None
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="Stoa", docs_url="/api/docs", openapi_url="/api/openapi.json",
                  lifespan=lifespan)
    app.state.db, app.state.garmin, app.state.calendar = db, garmin, calendar

    def parse_date(value: str | None) -> Date:
        if not value:
            return today()
        try:
            return Date.fromisoformat(value)
        except ValueError:
            raise HTTPException(400, f"Bad date: {value}")

    # --- auth ------------------------------------------------------------
    @app.middleware("http")
    async def require_login(request: Request, call_next):
        path = request.url.path
        open_path = (path in PUBLIC_PATHS or path.startswith("/static/")
                     or path == "/api/google/callback")
        if settings.app_password and not open_path and (path.startswith("/api/")):
            if not auth.verify(settings.secret_key, request.cookies.get(auth.COOKIE)):
                return JSONResponse({"detail": "Not signed in"}, status_code=401)
        return await call_next(request)

    @app.get("/api/session")
    def session(request: Request):
        needs = bool(settings.app_password)
        ok = not needs or auth.verify(settings.secret_key, request.cookies.get(auth.COOKIE))
        return {"authenticated": ok, "password_required": needs}

    @app.post("/api/login")
    def login(response: Response, payload: dict = Body(...)):
        if not auth.check_password(settings.app_password, payload.get("password", "")):
            raise HTTPException(401, "Wrong password")
        response.set_cookie(auth.COOKIE, auth.sign(settings.secret_key), max_age=auth.MAX_AGE,
                            httponly=True, samesite="lax",
                            secure=settings.public_url.startswith("https"))
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(auth.COOKIE)
        return {"ok": True}

    # --- philosophy ------------------------------------------------------
    @app.get("/api/meta")
    def meta():
        return {
            "virtues": stoic.VIRTUES,
            "franklin": [{"name": n, "virtue": v, "precept": p} for n, v, p in stoic.FRANKLIN],
            "health_fields": HEALTH_FIELDS,
            "today": today().isoformat(),
            "timezone": settings.timezone,
        }

    @app.get("/api/today")
    def today_view(date: str | None = None):
        day = parse_date(date)
        iso = day.isoformat()
        health = db.get_health(iso)
        baseline = analytics.hrv_baseline(db, day)
        behaviors = db.list_behaviors()
        evals = {e["behavior_id"]: e["lapses"] for e in db.evaluations_between(iso, iso)}
        journal = db.get_journal(iso)
        acts = db.activities_between(iso, iso)
        insight = stoic.daily_insight(day, health, baseline, analytics.weakest_virtue(db, day))
        return {
            "date": iso,
            "insight": insight,
            "journal": journal,
            "behaviors": behaviors,
            "evaluations": evals,
            "health": health,
            "hrv_baseline": round(baseline, 1) if baseline else None,
            "activities": acts,
            "pillars": analytics.pillars(health, journal, acts, len(evals), len(behaviors), baseline),
        }

    @app.put("/api/journal/{date}")
    def save_journal(date: str, payload: dict = Body(...)):
        return db.save_journal(parse_date(date).isoformat(), payload)

    @app.put("/api/evaluations/{date}")
    def save_evaluations(date: str, payload: dict = Body(...)):
        iso = parse_date(date).isoformat()
        db.set_evaluations(iso, {int(k): v for k, v in (payload.get("lapses") or {}).items()})
        return {e["behavior_id"]: e["lapses"] for e in db.evaluations_between(iso, iso)}

    @app.get("/api/week")
    def week(start: str | None = None):
        """Franklin's little book: behaviors down the side, days across, a dot per lapse."""
        day = parse_date(start)
        monday = day - timedelta(days=day.weekday())
        sunday = monday + timedelta(days=6)
        grid = {}
        for e in db.evaluations_between(monday.isoformat(), sunday.isoformat()):
            grid.setdefault(e["behavior_id"], {})[e["date"]] = e["lapses"]
        return {
            "start": monday.isoformat(),
            "days": [(monday + timedelta(days=i)).isoformat() for i in range(7)],
            "focus": stoic.focus_for(monday),
            "behaviors": db.list_behaviors(),
            "grid": grid,
        }

    @app.get("/api/trends")
    def trends(days: int = 90, end: str | None = None):
        return analytics.trends(db, parse_date(end), max(7, min(days, 730)))

    @app.get("/api/behaviors")
    def behaviors(all: bool = False):
        return db.list_behaviors(include_inactive=all)

    @app.post("/api/behaviors")
    def save_behavior(payload: dict = Body(...)):
        if payload.get("virtue") not in stoic.VIRTUES:
            raise HTTPException(400, "virtue must be one of " + ", ".join(stoic.VIRTUES))
        if not payload.get("title"):
            raise HTTPException(400, "title is required")
        payload.setdefault("franklin", "")
        payload.setdefault("question", payload["title"])
        return db.upsert_behavior(payload)

    @app.delete("/api/behaviors/{behavior_id}")
    def delete_behavior(behavior_id: int):
        db.delete_behavior(behavior_id)
        return {"ok": True}

    # --- health ----------------------------------------------------------
    @app.put("/api/health/{date}")
    def save_health(date: str, payload: dict = Body(...)):
        iso = parse_date(date).isoformat()
        db.upsert_health(iso, payload, source="manual")
        return db.get_health(iso)

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        try:
            return import_csv(db, await file.read())
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/garmin/status")
    def garmin_status():
        return garmin.status()

    @app.post("/api/garmin/connect")
    def garmin_connect(payload: dict = Body(...)):
        try:
            return garmin.connect(payload.get("email", ""), payload.get("password", ""))
        except Exception as exc:
            raise HTTPException(400, f"Garmin sign-in failed: {exc}")

    @app.post("/api/garmin/mfa")
    def garmin_mfa(payload: dict = Body(...)):
        try:
            return garmin.submit_mfa(str(payload.get("code", "")).strip())
        except Exception as exc:
            raise HTTPException(400, f"Garmin code rejected: {exc}")

    @app.post("/api/garmin/sync")
    def garmin_sync(days: int = 3):
        try:
            return garmin.sync(days=max(1, min(days, 365)), end=today())
        except Exception as exc:
            raise HTTPException(502, f"Garmin sync failed: {exc}")

    @app.post("/api/garmin/disconnect")
    def garmin_disconnect():
        garmin.disconnect()
        return {"ok": True}

    # --- calendar --------------------------------------------------------
    @app.get("/api/google/status")
    def google_status():
        return {"configured": calendar.configured, "connected": calendar.connected,
                "write": settings.google_calendar_write}

    @app.get("/api/google/auth")
    def google_auth():
        if not calendar.configured:
            raise HTTPException(400, "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first (see README).")
        return RedirectResponse(calendar.auth_url())

    @app.get("/api/google/callback")
    def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
        # Reached by Google's redirect; the state check ties it to an auth_url() we issued.
        if error:
            return RedirectResponse(f"/#/settings?google=error&reason={error}")
        try:
            calendar.finish(state, code)
        except Exception as exc:
            log.warning("Google OAuth failed: %s", exc)
            return RedirectResponse("/#/settings?google=error")
        return RedirectResponse("/#/settings?google=connected")

    @app.post("/api/google/disconnect")
    def google_disconnect():
        calendar.disconnect()
        return {"ok": True}

    @app.get("/api/calendar/opportunities")
    def calendar_opportunities(days: int = 7):
        if not calendar.connected:
            return {"connected": False, "events": [], "open_windows": []}
        try:
            events = calendar.list_events(days=max(1, min(days, 30)))
        except Exception as exc:
            raise HTTPException(502, f"Google Calendar error: {exc}")
        return {"connected": True, **opportunities(events, settings.timezone)}

    @app.post("/api/calendar/block")
    def calendar_block(payload: dict = Body(...)):
        try:
            ev = calendar.add_block(payload["summary"], payload.get("description", ""),
                                    payload["start"], payload["end"])
        except PermissionError as exc:
            raise HTTPException(403, str(exc))
        except KeyError as exc:
            raise HTTPException(400, f"Missing {exc}")
        return {"id": ev.get("id"), "link": ev.get("htmlLink")}

    # --- data ownership --------------------------------------------------
    @app.get("/api/export")
    def export():
        stamp = today().isoformat()
        return JSONResponse(db.export_all(), headers={
            "Content-Disposition": f'attachment; filename="stoa-export-{stamp}.json"'})

    @app.post("/api/import")
    def import_data(payload: dict = Body(...)):
        return db.import_all(payload)

    # --- front end -------------------------------------------------------
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/sw.js")
    def service_worker():
        # Served from the root so it can control the whole app.
        return FileResponse(STATIC / "sw.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")

    return app



def _start_scheduler(settings: Settings, garmin: GarminService, today):
    """Automatic daily Garmin pull while the server runs."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone=settings.timezone)
    h = settings.garmin_sync_hour
    # Morning pull catches last night's sleep/HRV; afternoon and evening pick up workouts.
    hours = ",".join(str(x) for x in sorted({h % 24, (h + 7) % 24, (h + 15) % 24}))

    def scheduled_sync():
        if not garmin.status()["connected"]:
            return
        try:
            garmin.sync(days=3, end=today())
        except Exception as exc:
            log.warning("Scheduled Garmin sync failed: %s", exc)

    scheduler.add_job(scheduled_sync, "cron", hour=hours, minute=5, id="garmin")
    scheduler.start()
    return scheduler
