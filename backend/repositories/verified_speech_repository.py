"""Persistence boundary for the two reads routers/verified_speaking.py needs.

Deliberately minimal: the write path for a verified audio record goes
through main.py's save_verified_audio_record/save_uploaded_audio (which
also own file-storage side effects and concurrent-insert reconciliation),
not through this module. See docs/backend-architecture.md for why
verified_speaking.py keeps its orchestration in the router rather than a
service layer - it's tightly coupled to the async analysis pipeline
(timeouts, exception passthrough from the analyzer) in a way that would
need main.py's own analysis functions extracted first to do safely.
"""
from typing import Optional


def find_published_scene(db, story_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT id, frames FROM custom_stories WHERE id = %s AND published = TRUE",
        (story_id,),
    ).fetchone()


def find_published_conversation_turns(db, story_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT conversation_turns FROM custom_stories WHERE id = %s AND published = TRUE",
        (story_id,),
    ).fetchone()


def find_attempts_by_id(db, attempt_id: str) -> list[dict]:
    return list(db.execute(
        """
        SELECT id, student_id, audio_sha256, server_verified_at,
               audio_url, praat_metrics, topic_id, image_index
        FROM audio_records
        WHERE attempt_id = %s
        ORDER BY server_verified_at DESC NULLS LAST, created_at DESC, id DESC
        """,
        (attempt_id,),
    ).fetchall())
