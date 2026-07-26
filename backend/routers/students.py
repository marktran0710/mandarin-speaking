import uuid

from fastapi import APIRouter, HTTPException

from database import connect_db, row_to_student
from main import StudentCreateRequest, StudentLoginRequest

router = APIRouter()


@router.get("/api/students")
async def list_students():
    with connect_db() as db:
        # Postgres has no COLLATE NOCASE; lower() reproduces SQLite's
        # case-insensitive roster ordering (backed by ix_students_lower_name).
        rows = db.execute("SELECT * FROM students ORDER BY lower(name)").fetchall()
    return [row_to_student(row) for row in rows]


@router.post("/api/students")
async def create_student(request: StudentCreateRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provide a student name.")

    with connect_db() as db:
        existing = db.execute(
            "SELECT * FROM students WHERE lower(name) = lower(%s)",
            (name,),
        ).fetchone()
        if existing is not None:
            # Idempotent: re-adding a name already on the roster just hands
            # back its existing id instead of erroring, so a teacher can
            # re-submit the roster form without worrying about duplicates.
            return row_to_student(existing)

        student_id = str(uuid.uuid4())
        created = db.execute(
            "INSERT INTO students (id, name) VALUES (%s, %s) RETURNING *",
            (student_id, name),
        ).fetchone()
    return row_to_student(created)


@router.post("/api/students/login")
async def login_student(request: StudentLoginRequest):
    """Password check for the student login page (default 123456).

    A classroom friction gate, not real auth: plaintext comparison, no
    tokens — success just hands back the roster record the frontend
    stores in its localStorage session, same as before passwords existed.
    """
    if not (request.studentId or (request.name and request.name.strip())):
        raise HTTPException(status_code=400, detail="Provide a student id or name.")

    with connect_db() as db:
        if request.studentId:
            row = db.execute(
                "SELECT * FROM students WHERE id = %s", (request.studentId,)
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM students WHERE lower(name) = lower(%s)",
                (request.name.strip(),),
            ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if request.password != (row.get("password") or "123456"):
        raise HTTPException(status_code=401, detail="Wrong password")
    return row_to_student(row)


@router.delete("/api/students/{student_id}")
async def delete_student(student_id: str):
    with connect_db() as db:
        row = db.execute(
            "DELETE FROM students WHERE id = %s RETURNING id", (student_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Student not found")
    return {"id": student_id, "deleted": True}
