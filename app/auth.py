"""Password hashing (PBKDF2-SHA256), signed session cookies, login throttling. Stdlib only."""
import base64
import hashlib
import hmac
import json
import secrets
import time

COOKIE = "sap_admin"
SESSION_SECONDS = 60 * 60 * 24 * 14


ITER = 390_000


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITER)
    return "pbkdf2$%d$%s$%s" % (ITER, base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, s, h = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(s), int(it))
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False


def _sig(key: str, payload: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(key.encode(), payload, hashlib.sha256).digest()).decode().rstrip("=")


def make_session(key: str, uid: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"u": uid, "e": int(time.time()) + SESSION_SECONDS}).encode())
    return payload.decode() + "." + _sig(key, payload)


def read_session(key: str, token: str):
    """Return the user id, or None when the cookie is missing, forged or expired."""
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sig(key, payload.encode())):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return data["u"] if data["e"] > time.time() else None
    except Exception:
        return None


class Throttle:
    """In-memory sliding window; enough to blunt password guessing and form spam."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window, self.hits = limit, window, {}

    def hit(self, key: str) -> bool:
        """Record an attempt; False when the caller is over the limit."""
        now = time.time()
        h = [t for t in self.hits.get(key, []) if now - t < self.window]
        h.append(now)
        self.hits[key] = h
        if len(self.hits) > 5000:  # keep memory bounded
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.window}
        return len(h) <= self.limit
