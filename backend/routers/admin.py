"""Admin console login.

Replaces the old client-side-only "admin123" check in AdminApp.tsx with a
real backend password check plus a signed JWT session cookie, matching the
student/teacher login pattern in auth.py. There is a single shared admin
account (no admin roster/table), so the JWT subject is a fixed constant.
"""
import os
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import auth
from database import (
    connect_db,
    row_to_student,
    row_to_teacher,
    row_to_vocab_quiz_attempt,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Read after `import auth` above, which runs auth.py's own load_dotenv()
# calls as an import side effect - see the load-order note in auth.py.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SUBJECT_ID = "admin"


class AdminLoginRequest(BaseModel):
    password: str


@router.post("/login")
def login_admin(
    request: AdminLoginRequest,
    response: Response,
    http_request: Request,
):
    client_ip = http_request.client.host if http_request.client else "unknown"
    auth.check_login_rate_limit(f"admin:{client_ip}")
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin login is not configured.")
    if not hmac.compare_digest(request.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Wrong password")
    token = auth.issue_token("admin", ADMIN_SUBJECT_ID)
    auth.set_session_cookie(response, token, "admin")
    return {"role": "admin"}


@router.post("/logout")
def logout_admin(response: Response):
    auth.clear_session_cookie(response, "admin")
    return {"loggedOut": True}


@router.get("/roster-overview")
def get_roster_overview(_identity: auth.Identity = Depends(auth.require_admin)):
    """One request for the admin console's landing data.

    The console previously fired three parallel calls (students, teachers,
    vocab-quiz-attempts) on every load/refresh — each its own auth check and
    pooled connection. Serving them from a single handler collapses that to
    one round-trip over one connection. Shapes are identical to the standalone
    ``/api/students``, ``/api/teachers`` and ``/api/vocab-quiz-attempts``
    (admin scope) endpoints, so the client stays field-for-field compatible.
    Quiz attempts keep their full ``questionResults`` payload — the IRT panel
    and the response-count metric both read per-question data.
    """
    with connect_db() as db:
        students = db.execute("SELECT * FROM students ORDER BY lower(name)").fetchall()
        teachers = db.execute("SELECT * FROM teachers ORDER BY lower(name)").fetchall()
        attempts = db.execute(
            "SELECT * FROM vocab_quiz_attempts ORDER BY completed_at DESC"
        ).fetchall()
    return {
        "students": [row_to_student(row) for row in students],
        "teachers": [row_to_teacher(row) for row in teachers],
        "quizAttempts": [row_to_vocab_quiz_attempt(row) for row in attempts],
    }
