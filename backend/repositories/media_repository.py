"""Persistence boundary for the student media-ownership checks behind
``/uploads/{relative_path}``.

Pure CRUD only - the cheapest-first ordering/short-circuit decision lives in
services/media_access_service.py. Every function takes an already-open
connection so the caller controls the transaction boundary.
"""


def owns_audio_record(db, student_id: str, stored_url: str) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM audio_records WHERE student_id = %s AND audio_url = %s LIMIT 1",
            (student_id, stored_url),
        ).fetchone()
    )


def owns_story_submission_audio(db, student_id: str, stored_url: str) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM story_submissions WHERE student_id = %s AND concatenated_audio_url = %s LIMIT 1",
            (student_id, stored_url),
        ).fetchone()
    )


def is_published_story_media(db, stored_url: str) -> bool:
    like_pattern = f"%{stored_url}%"
    return bool(
        db.execute(
            """
            SELECT 1
            FROM custom_stories
            WHERE published = TRUE
              AND (
                frames::text LIKE %s
                OR COALESCE(conversation_turns::text, '') LIKE %s
              )
            LIMIT 1
            """,
            (like_pattern, like_pattern),
        ).fetchone()
    )
