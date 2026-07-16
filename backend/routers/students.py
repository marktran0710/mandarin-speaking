import uuid

from fastapi import APIRouter, HTTPException

from database import connect_db, row_to_student
from main import StudentCreateRequest

router = APIRouter()


@router.get("/api/students")
async def list_students():
    with connect_db() as db:
        rows = db.execute("SELECT * FROM students ORDER BY name COLLATE NOCASE").fetchall()
    return [row_to_student(row) for row in rows]


@router.post("/api/students")
async def create_student(request: StudentCreateRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provide a student name.")

    with connect_db() as db:
        existing = db.execute(
            "SELECT * FROM students WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        if existing is not None:
            # Idempotent: re-adding a name already on the roster just hands
            # back its existing id instead of erroring, so a teacher can
            # re-submit the roster form without worrying about duplicates.
            return row_to_student(existing)

        student_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO students (id, name) VALUES (?, ?)",
            (student_id, name),
        )
        created = db.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()
    return row_to_student(created)


@router.delete("/api/students/{student_id}")
async def delete_student(student_id: str):
    with connect_db() as db:
        row = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Student not found")
        db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    return {"id": student_id, "deleted": True}
