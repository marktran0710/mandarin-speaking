"""JWT session cookie: issuing, verifying, and the FastAPI dependencies that
extract a caller's identity from it.

Replaces the old model where every request just handed the backend a bare
`student_id`/`teacher_id` and was trusted at face value. Login now sets an
httpOnly cookie carrying a signed JWT; `get_current_identity` (and the
role-scoped `require_student`/`require_teacher` wrappers) decode and verify
it, so a router can know who is actually calling instead of who the request
merely claims to be.

The development frontend proxies /api and /uploads through its own origin so
the browser keeps the httpOnly cookies. Student, teacher, and admin cookies
are role-specific, allowing separate app tabs to stay signed in at once. A
browser that calls this backend directly from another origin can lose cookies
because of browser cross-origin rules; use the same-origin proxy in development.
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
# Keep the old cookie as a compatibility fallback for clients that have not
# yet sent an app-role header. New logins also receive a role-specific cookie,
# so teacher and student sessions can coexist in one browser.
COOKIE_NAME = "session_token"
ROLE_COOKIE_NAMES = {
    "student": "student_session_token",
    "teacher": "teacher_session_token",
    "admin": "admin_session_token",
}
CLIENT_ROLE_HEADER = "X-Client-Role"
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


def validate_password_policy(password: str) -> None:
    """Validate account passwords; allow the local-only demo password."""
    production = os.getenv("APP_ENV", "development").lower() == "production"
    minimum = 8 if production else 6
    if len(password) < minimum:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {minimum} characters.",
        )
    if production and hmac.compare_digest(password, "123456"):
        raise HTTPException(status_code=400, detail="Choose a non-default production password.")


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


def set_session_cookie(response: Response, token: str, role: str | None = None) -> None:
    cookie_name = ROLE_COOKIE_NAMES.get(role, COOKIE_NAME)
    response.set_cookie(
        key=cookie_name,
        value=token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        # Plain HTTP is used only for local development. Set COOKIE_SECURE=true
        # when the production service runs behind HTTPS.
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )
    # Keep legacy API clients working while the browser frontends migrate to
    # role-specific cookies. Frontend requests select the correct cookie with
    # X-Client-Role, so this compatibility cookie no longer causes session
    # replacement between teacher and student tabs.
    if role:
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=TOKEN_TTL_SECONDS,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            path="/",
        )


def clear_session_cookie(response: Response, role: str | None = None) -> None:
    if role in ROLE_COOKIE_NAMES:
        response.delete_cookie(key=ROLE_COOKIE_NAMES[role], path="/")
    else:
        for cookie_name in ROLE_COOKIE_NAMES.values():
            response.delete_cookie(key=cookie_name, path="/")
    # Clear the compatibility cookie as well. Role-specific cookies remain
    # intact when a teacher or student signs out of only their own app.
    response.delete_cookie(key=COOKIE_NAME, path="/")


def _validate_identity(identity: Identity) -> Identity:
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


def _decode_cookie(token: str | None) -> Identity | None:
    if not token:
        return None
    return decode_token(token)


def _role_identity(
    role: str,
    role_token: str | None,
    legacy_token: str | None,
) -> Identity:
    identity = _decode_cookie(role_token)
    if identity is None:
        identity = _decode_cookie(legacy_token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return _validate_identity(identity)


def get_current_identity(
    request: Request = None,
    session_token: Optional[str] = Cookie(default=None),
    student_session_token: Optional[str] = Cookie(default=None),
    teacher_session_token: Optional[str] = Cookie(default=None),
    admin_session_token: Optional[str] = Cookie(default=None),
) -> Identity:
    """Decode the session selected by the frontend app, or 401.

    Requests from the separate student/teacher/admin entries identify their
    app with X-Client-Role. Direct media requests do not need that header and
    fall back to any available role cookie.
    """
    requested_role = request.headers.get(CLIENT_ROLE_HEADER) if request else None
    role_tokens = {
        "student": student_session_token,
        "teacher": teacher_session_token,
        "admin": admin_session_token,
    }
    token = role_tokens.get(requested_role or "")
    if token is None and requested_role not in role_tokens:
        for candidate in ("admin", "teacher", "student"):
            token = role_tokens[candidate]
            if token:
                break
    identity = _decode_cookie(token)
    if identity is None and session_token:
        legacy_identity = _decode_cookie(session_token)
        if requested_role in role_tokens and legacy_identity.role != requested_role:
            legacy_identity = None
        identity = legacy_identity
    if identity is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return _validate_identity(identity)


def _require_role(role: str):
    def _role_dependency(
        role_token: Optional[str] = Cookie(default=None, alias=ROLE_COOKIE_NAMES[role]),
        session_token: Optional[str] = Cookie(default=None),
    ) -> Identity:
        return _role_identity(role, role_token, session_token)

    def _dependency(identity: Identity = Depends(_role_dependency)) -> Identity:
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
