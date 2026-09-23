"""Persistence boundary for the ``audio_records`` table's read/delete paths.

The write path (create/upload) already goes through services/media.py's
save_audio_record/save_uploaded_audio, which own file-storage side effects
alongside persistence - this module only covers what routers/audio.py still
did with inline SQL: listing, counting, ownership lookup, and delete.
"""
from typing import Optional

from repositories.database import row_to_audio_record


def list_records(
    db,
    *,
    limit: int,
    skip: int,
    student_id: Optional[str] = None,
    topic_id: Optional[str] = None,
) -> list[dict]:
    query = "SELECT * FROM audio_records"
    params: list[object] = []
    filters: list[str] = []
    if student_id:
        filters.append("student_id = %s")
        params.append(student_id)
    if topic_id:
        filters.append("topic_id = %s")
        params.append(topic_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
    params.extend([limit, skip])
    rows = db.execute(query, params).fetchall()
    return [row_to_audio_record(row) for row in rows]


def count_records(db) -> int:
    return db.execute("SELECT COUNT(*) AS total FROM audio_records").fetchone()["total"]


def find_owner(db, record_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT student_id FROM audio_records WHERE id = %s",
        (record_id,),
    ).fetchone()


def delete_record(db, record_id: str) -> Optional[dict]:
    """Deletes the record and returns its stored audio_url (for file cleanup), if any."""
    return db.execute(
        "DELETE FROM audio_records WHERE id = %s RETURNING audio_url",
        (record_id,),
    ).fetchone()
