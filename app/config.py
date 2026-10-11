"""Runtime configuration, read from environment variables (or a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the app runs without extra dependencies."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    app_password: str
    secret_key: str
    timezone: str
    garmin_email: str
    garmin_password: str
    garmin_sync_hour: int
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_calendar_write: bool
    public_url: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "stoa.db"

    @property
    def garmin_token_dir(self) -> Path:
        return self.data_dir / "garmin_tokens"

    @property
    def google_token_path(self) -> Path:
        return self.data_dir / "google_token.json"


def load_settings() -> Settings:
    data_dir = Path(os.getenv("STOA_DATA_DIR", ROOT / "data")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)

    secret = os.getenv("STOA_SECRET_KEY", "")
    if not secret:
        # Persist a generated secret so sessions survive restarts.
        secret_file = data_dir / ".secret_key"
        if secret_file.exists():
            secret = secret_file.read_text().strip()
        else:
            secret = os.urandom(32).hex()
            secret_file.write_text(secret)
            secret_file.chmod(0o600)

    public_url = os.getenv("STOA_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return Settings(
        data_dir=data_dir,
        app_password=os.getenv("STOA_PASSWORD", ""),
        secret_key=secret,
        timezone=os.getenv("STOA_TIMEZONE", "America/New_York"),
        garmin_email=os.getenv("GARMIN_EMAIL", ""),
        garmin_password=os.getenv("GARMIN_PASSWORD", ""),
        garmin_sync_hour=int(os.getenv("GARMIN_SYNC_HOUR", "6")),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        google_redirect_uri=os.getenv(
            "GOOGLE_REDIRECT_URI", f"{public_url}/api/google/callback"
        ),
        google_calendar_write=os.getenv("GOOGLE_CALENDAR_WRITE", "false").lower()
        in ("1", "true", "yes"),
        public_url=public_url,
    )
