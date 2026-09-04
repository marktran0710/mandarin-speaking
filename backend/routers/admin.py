"""Admin console login.

Replaces the old client-side-only "admin123" check in AdminApp.tsx with a
real backend password check plus a signed JWT session cookie, matching the
student/teacher login pattern in auth.py. There is a single shared admin
account (no admin roster/table), so the JWT subject is a fixed constant.
"""
import os
import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import auth

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
