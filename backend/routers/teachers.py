import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
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
    with connect_db() as db:
        if db.execute("SELECT 1 FROM teachers WHERE lower(name) = lower(%s)", (name,)).fetchone():
            raise HTTPException(status_code=409, detail="Teacher already exists.")
        row = db.execute("INSERT INTO teachers (id, name, password) VALUES (%s, %s, %s) RETURNING *", (str(uuid.uuid4()), name, request.password)).fetchone()
    return row_to_teacher(row)

@router.post("/api/teachers/login")
async def login_teacher(request: TeacherLoginRequest, response: Response):
    with connect_db() as db:
        row = db.execute("SELECT * FROM teachers WHERE lower(name) = lower(%s)", (request.name.strip(),)).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="Teacher not found")
    if row["status"] != "active": raise HTTPException(status_code=403, detail="Teacher account is inactive")
    if request.password != row["password"]: raise HTTPException(status_code=401, detail="Wrong password")
    token = auth.issue_token("teacher", row["id"])
    auth.set_session_cookie(response, token)
    return row_to_teacher(row)

@router.post("/api/teachers/logout")
async def logout_teacher(response: Response):
    auth.clear_session_cookie(response)
    return {"loggedOut": True}

@router.patch("/api/teachers/{teacher_id}")
async def update_teacher(
    teacher_id: str,
    request: TeacherUpdateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    updates, params = [], []
    if request.password is not None: updates.append("password = %s"); params.append(request.password)
    if request.status is not None: updates.append("status = %s"); params.append(request.status)
    if not updates: raise HTTPException(status_code=400, detail="No teacher changes supplied.")
    params.append(teacher_id)
    with connect_db() as db:
        row = db.execute(f"UPDATE teachers SET {', '.join(updates)} WHERE id = %s RETURNING *", tuple(params)).fetchone()
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
