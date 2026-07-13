import datetime

from fastapi import APIRouter, HTTPException, Query

from database import connect_db, row_to_help_request
from main import HelpRequest

router = APIRouter()


@router.get("/api/help-requests")
async def list_help_requests(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM help_requests
            ORDER BY
                CASE status WHEN 'open' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip),
        ).fetchall()
    return [row_to_help_request(row) for row in rows]


@router.post("/api/help-requests")
async def create_help_request(request: HelpRequest):
    student_name = request.studentName.strip() or "Student"
    message = request.message.strip() or "I need teacher help."
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO help_requests (
                id, student_name, message, status, created_at, resolved_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.id,
                student_name,
                message,
                "open",
                request.createdAt,
                None,
            ),
        )
    return {
        **request.model_dump(),
        "studentName": student_name,
        "message": message,
        "status": "open",
        "resolvedAt": None,
    }


@router.post("/api/help-requests/{request_id}/resolve")
async def resolve_help_request(request_id: str):
    resolved_at = datetime.datetime.utcnow().isoformat() + "Z"
    with connect_db() as db:
        row = db.execute(
            "SELECT * FROM help_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Help request not found")
        db.execute(
            """
            UPDATE help_requests
            SET status = 'resolved', resolved_at = ?
            WHERE id = ?
            """,
            (resolved_at, request_id),
        )
        updated = db.execute(
            "SELECT * FROM help_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
    return row_to_help_request(updated)
