"""Use-case orchestration for the help-request queue.

Coordinates the help-request repository with the plain field
defaulting/shaping that used to live inline in routers/help_requests.py.
Raises HelpRequestServiceError (not HTTPException) - the router maps it to
an HTTP status code.
"""
from repositories import help_request_repository as repo
from repositories.database import row_to_help_request


class HelpRequestServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_help_requests(db, limit: int, skip: int) -> list[dict]:
    rows = repo.find_all(db, limit, skip)
    return [row_to_help_request(row) for row in rows]


def create_help_request(db, request) -> dict:
    student_name = request.studentName.strip() or "Student"
    message = request.message.strip() or "I need teacher help."
    repo.upsert(
        db,
        id=request.id,
        student_name=student_name,
        message=message,
        status="open",
        created_at=request.createdAt,
        resolved_at=None,
    )
    return {
        **request.model_dump(),
        "studentName": student_name,
        "message": message,
        "status": "open",
        "resolvedAt": None,
    }


def resolve_help_request(db, request_id: str, resolved_at: str) -> dict:
    updated = repo.resolve(db, request_id, resolved_at)
    if updated is None:
        raise HelpRequestServiceError(404, "Help request not found")
    return row_to_help_request(updated)
