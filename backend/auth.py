"""JWT session cookie: issuing, verifying, and the FastAPI dependencies that
extract a caller's identity from it.

Replaces the old model where every request just handed the backend a bare
`student_id`/`teacher_id` and was trusted at face value. Login now sets an
httpOnly cookie carrying a signed JWT; `get_current_identity` (and the
role-scoped `require_student`/`require_teacher` wrappers) decode and verify
it, so a router can know who is actually calling instead of who the request
merely claims to be.

The cross-device "Laptop mode" case (frontend and backend on different
Tailscale hosts) works too, but only because the browser is never allowed to
call this backend cross-origin in the first place - vite.config.ts proxies
/api and /uploads through the frontend's own dev server, which forwards to
the real backend host server-side. A browser that DOES call this backend
directly cross-origin will silently lose the cookie (Chrome drops it even
with correct CORS/SameSite=Lax headers) - always go through the proxy.
"""
from __future__ import annotations

import os
import time
import hashlib
import hmac
import collections
import threading
from dataclasses import dataclass
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Cookie, Depends, HTTPException, Request, Response

# Mirrors the same self-contained load_dotenv() pattern database.py and
# ai_feedback.py use - this module can be imported before main.py's own
# load_dotenv() call runs, so without loading here too, JWT_SECRET_KEY would
# silently read as unset.
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if len(JWT_SECRET_KEY) < 16:
    # Fail loudly at import time rather than silently issue tokens anyone
    # could forge by signing with the same empty/weak key.
    raise RuntimeError(
        "JWT_SECRET_KEY is missing or too short. Set a real secret in .env "
        '(python -c "import secrets; print(secrets.token_urlsafe(48))").'
    )

JWT_ALGORITHM = "HS256"
# 30 days by default - the classroom login is a once-per-session action, not
# something students should be re-prompted for mid-lesson.
TOKEN_TTL_SECONDS = int(os.getenv("JWT_TOKEN_TTL_SECONDS", str(30 * 24 * 3600)))
COOKIE_NAME = "session_token"
VALID_ROLES = ("student", "teacher", "admin")
_login_attempts: dict[str, collections.deque[float]] = {}
_login_attempts_lock = threading.Lock()

# bcrypt only accepts 72-byte inputs.  Normalising every password with a
# domain-separated SHA-256 digest before bcrypt keeps the API's existing
# 100-character allowance without silently truncating a user's password.
_PASSWORD_PEPPER = b"mandarin-speaking-password-v1\x00"
_BCRYPT_ROUNDS = 12
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


def _bcrypt_password(password: str) -> bytes:
    return _PASSWORD_PEPPER + hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    """Return a bcrypt hash suitable for storing in the password column."""
    return bcrypt.hashpw(
        _bcrypt_password(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("ascii")


def _is_bcrypt_hash(stored_password: str) -> bool:
    return stored_password.startswith(_BCRYPT_PREFIXES)


def _bcrypt_needs_rehash(stored_password: str) -> bool:
    try:
        return int(stored_password.split("$", 3)[2]) < _BCRYPT_ROUNDS
    except (IndexError, ValueError):
        # checkpw() below is still the authority on whether a hash is valid.
        return False


def verify_password(stored_password: object, submitted_password: str) -> tuple[bool, str | None]:
    """Verify a stored password and return a replacement hash when needed.

    Existing rows stored plaintext passwords.  A successful legacy login is
    deliberately accepted once, compared in constant time, then replaced by
    bcrypt in the caller's transaction.  Invalid bcrypt data is treated as a
    failed login instead of surfacing as a server error.
    """
    if not isinstance(stored_password, str):
        return False, None

    if _is_bcrypt_hash(stored_password):
        try:
            valid = bcrypt.checkpw(
                _bcrypt_password(submitted_password), stored_password.encode("ascii")
            )
        except (UnicodeEncodeError, ValueError):
            return False, None
        if not valid:
            return False, None
        return True, hash_password(submitted_password) if _bcrypt_needs_rehash(stored_password) else None

    valid = hmac.compare_digest(stored_password, submitted_password)
    return valid, hash_password(submitted_password) if valid else None


def check_login_rate_limit(key: str, max_attempts: int = 10, window_seconds: int = 60) -> None:
    """Bound password guessing per client and account without external state.

    This in-process limiter is an MVP guard for one backend instance. A future
    multi-replica deployment must move it to Redis or another shared store.
    """
    now = time.monotonic()
    with _login_attempts_lock:
        attempts = _login_attempts.setdefault(key, collections.deque())
        while attempts and now - attempts[0] > window_seconds:
            attempts.popleft()
        if len(attempts) >= max_attempts:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        attempts.append(now)


@dataclass(frozen=True)
class Identity:
    role: str
    id: str


def issue_token(role: str, subject_id: str) -> str:
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {role!r}")
    if not subject_id:
        raise ValueError("subject_id must not be empty")
    now = int(time.time())
    payload = {
        "role": role,
        "sub": subject_id,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Identity:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session.")

    role = payload.get("role")
    subject_id = payload.get("sub")
    if role not in VALID_ROLES or not subject_id:
        raise HTTPException(status_code=401, detail="Invalid session.")
    return Identity(role=role, id=subject_id)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        # Plain HTTP over LAN/Tailscale today - Secure would silently drop
        # the cookie. Set COOKIE_SECURE=true once this runs behind HTTPS.
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def get_current_identity(
    session_token: Optional[str] = Cookie(default=None),
) -> Identity:
    """Base dependency: decode the session cookie into an Identity, or 401."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not logged in.")
    identity = decode_token(session_token)
    if identity.role in ("student", "teacher"):
        # Sessions must stop working when the roster account is deleted or
        # disabled; a long-lived JWT alone is not sufficient revocation.
        from database import connect_db

        table = "students" if identity.role == "student" else "teachers"
        select = "1" if identity.role == "student" else "status"
        with connect_db() as db:
            row = db.execute(
                f"SELECT {select} FROM {table} WHERE id = %s", (identity.id,)
            ).fetchone()
        if row is None or (identity.role == "teacher" and row.get("status") != "active"):
            raise HTTPException(status_code=401, detail="Account is no longer active.")
    return identity


def _require_role(role: str):
    def _dependency(identity: Identity = Depends(get_current_identity)) -> Identity:
        if identity.role != role:
            raise HTTPException(status_code=403, detail=f"{role.capitalize()} account required.")
        return identity

    return _dependency


def _require_any_role(*roles: str):
    def _dependency(identity: Identity = Depends(get_current_identity)) -> Identity:
        if identity.role not in roles:
            raise HTTPException(status_code=403, detail="Not authorized for this action.")
        return identity

    return _dependency


require_student = _require_role("student")
require_teacher = _require_role("teacher")
require_admin = _require_role("admin")
# Teacher dashboards and the admin console both browse across every
# student's data - the same "list everything" endpoints serve both.
require_teacher_or_admin = _require_any_role("teacher", "admin")


def require_story_access(
    request: Request,
    identity: Identity = Depends(get_current_identity),
) -> Identity:
    """Allow logged-in students to read lessons, but reserve story writes
    and teacher-generated content for staff accounts."""
    if request.method != "GET" and identity.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin account required.")
    return identity
