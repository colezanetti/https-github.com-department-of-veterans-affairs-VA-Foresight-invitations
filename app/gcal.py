"""Google Calendar: read your schedule and turn it into chances to practise.

The OAuth flow runs on the server, and the refresh token is stored in the data
directory. Access is read-only unless GOOGLE_CALENDAR_WRITE is enabled, which lets
the app add practice blocks to your calendar.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

READ_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events"

# (pattern, virtue, title, practice). First match wins.
RULES = [
    (r"\b(interview|present|pitch|demo|review|performance|deadline|exam|launch|negotiat)",
     "courage", "High-stakes moment",
     "Premeditatio malorum: picture it going badly, then decide how you'd still act well. "
     "What stands in the way becomes the way."),
    (r"\b(1:1|1-1|one on one|1on1|feedback|coaching|mentor)",
     "justice", "One-on-one",
     "Listen first and fully. Ask what they need from you, and give credit where it's due."),
    (r"\b(gym|run|ride|swim|workout|training|yoga|lift|hike|climb|tennis|golf|pilates|crossfit)",
     "courage", "Training session",
     "Train the body as the mind's servant. Match the effort to today's recovery, not your ego."),
    (r"\b(flight|travel|commute|drive|train to|airport|uber)",
     "wisdom", "Travel time",
     "Travel well: no complaining about delays. Use the time to read or reflect on your intention."),
    (r"\b(dinner|lunch|coffee|drinks|party|happy hour|bbq|celebrat)",
     "temperance", "Meal or social",
     "Eat not to dullness, drink not to elevation. Be the most attentive person at the table."),
    (r"\b(family|kids|school|birthday|anniversary|date night|parents)",
     "justice", "Time with family",
     "Be fully present: phone away. These are the people your duty starts with."),
    (r"\b(doctor|dentist|therapy|physio|massage|appointment)",
     "wisdom", "Health appointment",
     "Care for the body without anxiety about it. Ask the questions you came to ask."),
    (r"\b(meeting|sync|standup|stand-up|call|zoom|meet|huddle|workshop|offsite|all hands|townhall)",
     "justice", "Meeting",
     "Speak only what may benefit others (Franklin's Silence). Leave people better informed, not more burdened."),
]


def classify(summary: str) -> dict | None:
    text = (summary or "").lower()
    for pattern, virtue, title, practice in RULES:
        if re.search(pattern, text):
            return {"virtue": virtue, "kind": title, "practice": practice}
    return None


def _parse(dt: dict, tz: ZoneInfo) -> tuple[datetime, bool]:
    if "dateTime" in dt:
        return datetime.fromisoformat(dt["dateTime"].replace("Z", "+00:00")).astimezone(tz), False
    return datetime.fromisoformat(dt["date"]).replace(tzinfo=tz), True


def opportunities(events: list[dict], tz_name: str, now: datetime | None = None,
                  day_start: int = 7, day_end: int = 21) -> dict:
    """Turn raw Google events into practice opportunities plus open windows for training or rest."""
    tz = ZoneInfo(tz_name)
    now = now or datetime.now(tz)
    timed = []
    out = []
    for ev in events:
        if ev.get("status") == "cancelled":
            continue
        start, all_day = _parse(ev["start"], tz)
        end, _ = _parse(ev["end"], tz)
        info = classify(ev.get("summary", ""))
        item = {
            "id": ev.get("id"),
            "summary": ev.get("summary", "(no title)"),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "all_day": all_day,
            **(info or {"virtue": None, "kind": "Event", "practice": None}),
        }
        out.append(item)
        if not all_day:
            timed.append((start, end))

    # Back-to-back stretches call for temperance (tranquility under load).
    timed.sort()
    streak_start, streak_end, streak_n = None, None, 0
    load = []
    for start, end in timed:
        if streak_end and start - streak_end <= timedelta(minutes=10):
            streak_end = max(streak_end, end)
            streak_n += 1
        else:
            if streak_n >= 3:
                load.append((streak_start, streak_end, streak_n))
            streak_start, streak_end, streak_n = start, end, 1
    if streak_n >= 3:
        load.append((streak_start, streak_end, streak_n))
    for s, e, n in load:
        out.append({
            "id": f"load-{s.isoformat()}", "summary": f"{n} events back to back",
            "start": s.isoformat(), "end": e.isoformat(), "all_day": False,
            "virtue": "temperance", "kind": "Heavy stretch",
            "practice": "Take three slow breaths between each one. Be undisturbed by trifles; pause before you answer.",
        })

    # Open windows of 45+ minutes inside waking hours: chances to train, walk, or rest.
    windows = []
    days = sorted({datetime.fromisoformat(o["start"]).date() for o in out} | {now.date()})
    for d in days:
        cursor = datetime(d.year, d.month, d.day, day_start, tzinfo=tz)
        limit = datetime(d.year, d.month, d.day, day_end, tzinfo=tz)
        if d == now.date():
            cursor = max(cursor, now)
        for start, end in [t for t in timed if t[0].date() == d] + [(limit, limit)]:
            if start - cursor >= timedelta(minutes=45) and cursor < limit:
                windows.append({"start": cursor.isoformat(), "end": min(start, limit).isoformat(),
                                "minutes": int((min(start, limit) - cursor).total_seconds() // 60)})
            cursor = max(cursor, end)

    out.sort(key=lambda o: o["start"])
    return {"events": out, "open_windows": windows}


class CalendarService:
    def __init__(self, settings):
        self.s = settings
        self.token_path = Path(settings.google_token_path)
        self._flow_state: dict[str, str] = {}  # oauth state -> PKCE code_verifier

    @property
    def scopes(self) -> list[str]:
        return [WRITE_SCOPE] if self.s.google_calendar_write else [READ_SCOPE]

    @property
    def configured(self) -> bool:
        return bool(self.s.google_client_id and self.s.google_client_secret)

    @property
    def connected(self) -> bool:
        return self.token_path.exists()

    def _client_config(self) -> dict:
        return {"web": {
            "client_id": self.s.google_client_id,
            "client_secret": self.s.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [self.s.google_redirect_uri],
        }}

    def auth_url(self) -> str:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(self._client_config(), scopes=self.scopes,
                                       redirect_uri=self.s.google_redirect_uri)
        url, state = flow.authorization_url(access_type="offline", prompt="consent",
                                            include_granted_scopes="true")
        self._flow_state[state] = flow.code_verifier or ""
        return url

    def finish(self, state: str, code: str) -> None:
        from google_auth_oauthlib.flow import Flow
        if state not in self._flow_state:
            raise ValueError("Unknown or expired sign-in attempt. Try connecting again.")
        flow = Flow.from_client_config(self._client_config(), scopes=self.scopes,
                                       redirect_uri=self.s.google_redirect_uri, state=state)
        flow.code_verifier = self._flow_state.pop(state) or None
        flow.fetch_token(code=code)
        self.token_path.write_text(flow.credentials.to_json())
        self.token_path.chmod(0o600)

    def disconnect(self) -> None:
        self.token_path.unlink(missing_ok=True)

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_info(json.loads(self.token_path.read_text()))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json())
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def list_events(self, days: int = 7) -> list[dict]:
        tz = ZoneInfo(self.s.timezone)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        res = self._service().events().list(
            calendarId="primary", timeMin=start.isoformat(),
            timeMax=(start + timedelta(days=days)).isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=250,
        ).execute()
        return res.get("items", [])

    def add_block(self, summary: str, description: str, start: str, end: str) -> dict:
        if not self.s.google_calendar_write:
            raise PermissionError("Set GOOGLE_CALENDAR_WRITE=true and reconnect to add events.")
        body = {"summary": summary, "description": description,
                "start": {"dateTime": start}, "end": {"dateTime": end},
                "reminders": {"useDefault": True}}
        return self._service().events().insert(calendarId="primary", body=body).execute()
