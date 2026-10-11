"""Single-user password gate with a signed, long-lived cookie."""

from __future__ import annotations

import hashlib
import hmac
import time

COOKIE = "stoa_session"
MAX_AGE = 60 * 60 * 24 * 90  # 90 days, so the iPhone home-screen app stays signed in


def sign(secret: str, issued: int | None = None) -> str:
    issued = issued or int(time.time())
    mac = hmac.new(secret.encode(), str(issued).encode(), hashlib.sha256).hexdigest()
    return f"{issued}.{mac}"


def verify(secret: str, token: str | None) -> bool:
    if not token or "." not in token:
        return False
    issued, mac = token.split(".", 1)
    if not issued.isdigit():
        return False
    expected = hmac.new(secret.encode(), issued.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected) and time.time() - int(issued) < MAX_AGE


def check_password(expected: str, given: str) -> bool:
    return bool(expected) and hmac.compare_digest(expected.encode(), (given or "").encode())
