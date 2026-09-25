"""Use-case orchestration for whether a student may fetch a given uploaded
media file.

Holds the ownership decision that used to live inline in
routers/media.py's serve_upload: which of a student's own audio/story-submission
records, or a published lesson's story media, the requested URL belongs to.
"""
from repositories import media_repository as repo


def is_media_access_allowed(db, student_id: str, stored_url: str) -> bool:
    """Evaluate the three ownership checks cheapest-first and stop at the
    first match. Same authorization result as testing all three, but a
    student replaying their own audio (the common case) never reaches the
    published-content check, whose JSONB text search is an unindexable
    full-table scan - kept last so it runs only when the two indexed
    lookups both miss (i.e. only for published lesson media). Conversation
    turns are published content too, but live outside the legacy frames
    payload.
    """
    if repo.owns_audio_record(db, student_id, stored_url):
        return True
    if repo.owns_story_submission_audio(db, student_id, stored_url):
        return True
    return repo.is_published_story_media(db, stored_url)
