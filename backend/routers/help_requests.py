import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

import auth
from database import connect_db, row_to_help_request
from main import HelpRequest

router = APIRouter()


@router.get("/api/help-requests")
def list_help_requests(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM help_requests
            ORDER BY
                CASE status WHEN 'open' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, skip),
        ).fetchall()
    return [row_to_help_request(row) for row in rows]


@router.post("/api/help-requests")
def create_help_request(
    request: HelpRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    student_name = request.studentName.strip() or "Student"
    message = request.message.strip() or "I need teacher help."
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO help_requests (
                id, student_name, message, status, created_at, resolved_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                student_name = EXCLUDED.student_name,
                message = EXCLUDED.message,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                resolved_at = EXCLUDED.resolved_at
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
def resolve_help_request(
    request_id: str,
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    resolved_at = datetime.datetime.utcnow().isoformat() + "Z"
    with connect_db() as db:
        updated = db.execute(
            """
            UPDATE help_requests
            SET status = 'resolved', resolved_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (resolved_at, request_id),
        ).fetchone()
        if updated is None:
            raise HTTPException(status_code=404, detail="Help request not found")
    return row_to_help_request(updated)
