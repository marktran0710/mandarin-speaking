"""JWT session cookie: issuing, verifying, and the FastAPI dependencies that
extract a caller's identity from it.

Replaces the old model where every request just handed the backend a bare
`student_id`/`teacher_id` and was trusted at face value. Login now sets an
httpOnly cookie carrying a signed JWT; `get_current_identity` (and the
role-scoped `require_student`/`require_teacher` wrappers) decode and verify
it, so a router can know who is actually calling instead of who the request
merely claims to be.

Not designed for the cross-device "Laptop mode" case (frontend and backend
on different Tailscale hosts) - that needs either HTTPS (for
`SameSite=None; Secure`) or a header-based token instead of a cookie. Scoped
out for now; see the classroom capacity/JWT design discussion.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import Cookie, Depends, HTTPException, Response

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
    return decode_token(session_token)


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
