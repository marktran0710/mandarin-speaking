import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.errors import UniqueViolation
import auth
from database import connect_db, row_to_teacher
from main import TeacherCreateRequest, TeacherLoginRequest, TeacherUpdateRequest

router = APIRouter()

@router.get("/api/teachers")
async def list_teachers(identity: auth.Identity = Depends(auth.require_teacher_or_admin)):
    with connect_db() as db:
        rows = db.execute("SELECT * FROM teachers ORDER BY lower(name)").fetchall()
    return [row_to_teacher(row) for row in rows]

@router.post("/api/teachers")
async def create_teacher(
    request: TeacherCreateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    name = request.name.strip()
    auth.validate_password_policy(request.password)
    with connect_db() as db:
        if db.execute("SELECT 1 FROM teachers WHERE lower(name) = lower(%s)", (name,)).fetchone():
            raise HTTPException(status_code=409, detail="Teacher already exists.")
        try:
            row = db.execute("INSERT INTO teachers (id, name, password) VALUES (%s, %s, %s) RETURNING *", (str(uuid.uuid4()), name, auth.hash_password(request.password))).fetchone()
        except UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="Teacher already exists.") from exc
    return row_to_teacher(row)

@router.post("/api/teachers/login")
async def login_teacher(
    request: TeacherLoginRequest,
    response: Response,
    http_request: Request,
):
    client_ip = http_request.client.host if http_request.client else "unknown"
    auth.check_login_rate_limit(f"teacher:{client_ip}:{request.name.strip().lower()}")
    with connect_db() as db:
        row = db.execute("SELECT * FROM teachers WHERE lower(name) = lower(%s)", (request.name.strip(),)).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="Teacher not found")
    if row["status"] != "active": raise HTTPException(status_code=403, detail="Teacher account is inactive")
    if row.get("password_reset_required"):
        raise HTTPException(status_code=403, detail="Teacher password reset required")
    valid, replacement_hash = auth.verify_password(row.get("password"), request.password)
    if not valid: raise HTTPException(status_code=401, detail="Wrong password")
    if replacement_hash is not None:
        with connect_db() as db:
            db.execute("UPDATE teachers SET password = %s WHERE id = %s", (replacement_hash, row["id"]))
    token = auth.issue_token("teacher", row["id"])
    auth.set_session_cookie(response, token, "teacher")
    return row_to_teacher(row)

@router.post("/api/teachers/logout")
async def logout_teacher(response: Response):
    auth.clear_session_cookie(response, "teacher")
    return {"loggedOut": True}

@router.patch("/api/teachers/{teacher_id}")
async def update_teacher(
    teacher_id: str,
    request: TeacherUpdateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    updates, params = [], []
    if request.name is not None:
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Provide a teacher name.")
        with connect_db() as db:
            duplicate = db.execute(
                "SELECT 1 FROM teachers WHERE lower(name) = lower(%s) AND id <> %s",
                (name, teacher_id),
            ).fetchone()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Teacher already exists.")
        updates.append("name = %s")
        params.append(name)
    if request.password is not None:
        auth.validate_password_policy(request.password)
        updates.extend(["password = %s", "password_reset_required = false"])
        params.append(auth.hash_password(request.password))
    if request.status is not None: updates.append("status = %s"); params.append(request.status)
    if not updates: raise HTTPException(status_code=400, detail="No teacher changes supplied.")
    params.append(teacher_id)
    try:
        with connect_db() as db:
            row = db.execute(f"UPDATE teachers SET {', '.join(updates)} WHERE id = %s RETURNING *", tuple(params)).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Teacher already exists.") from exc
    if row is None: raise HTTPException(status_code=404, detail="Teacher not found")
    return row_to_teacher(row)

@router.delete("/api/teachers/{teacher_id}")
async def delete_teacher(
    teacher_id: str,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        row = db.execute("DELETE FROM teachers WHERE id = %s RETURNING id", (teacher_id,)).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="Teacher not found")
    return {"id": teacher_id, "deleted": True}
