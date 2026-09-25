"""Use-case orchestration for custom-story CRUD.

Coordinates the story repository with frame-media persistence and payload
validation. Raises StoryValidationError (not HTTPException) - the router
maps it to an HTTP status code.
"""
from db import connect_db
import services.media as media_service
from domain.vocabulary.assessment import validate_assessment_payload
from repositories.content import stories as repo
from repositories.database import row_to_custom_story


class StoryValidationError(Exception):
    def __init__(self, status_code: int, detail):
        super().__init__(detail if isinstance(detail, str) else str(detail))
        self.status_code = status_code
        self.detail = detail


def list_stories(db, *, published_only: bool, limit: int, skip: int) -> list[dict]:
    rows = repo.list_stories(db, published_only=published_only, limit=limit, skip=skip)
    return [row_to_custom_story(row) for row in rows]


def create_story(story) -> dict:
    """Opens its own ``connect_db()`` block (rather than taking an
    already-open connection) because the original router endpoint
    deliberately did frame-media persistence (file I/O) before ever opening
    a DB connection, only opening one around the SQL write itself - that
    ordering is preserved here verbatim.
    """
    if story.vocabAssessment is not None:
        assessment_issues = validate_assessment_payload(story.vocabAssessment)
        if assessment_issues:
            raise StoryValidationError(
                422,
                {
                    "message": "vocabAssessment failed validation.",
                    "issues": [issue.__dict__ for issue in assessment_issues],
                },
            )
    fields_set = getattr(story, "model_fields_set", getattr(story, "__fields_set__", set()))
    assessment_update = (
        "vocab_assessment = EXCLUDED.vocab_assessment"
        if "vocabAssessment" in fields_set
        else "vocab_assessment = custom_stories.vocab_assessment"
    )
    frames = [frame.model_dump() for frame in story.frames]
    stored_frames = media_service.persist_story_frame_images(story.id, frames)
    stored_frames = media_service.persist_story_frame_audio(story.id, stored_frames)
    stored_conversation_turns = media_service.persist_story_conversation_audio(
        story.id,
        [turn.model_dump() for turn in story.conversationTurns]
        if story.conversationTurns is not None
        else None,
    )
    # ON CONFLICT DO UPDATE, not the old INSERT OR REPLACE: SQLite's
    # replace was a DELETE+INSERT, so every re-save wiped the two columns
    # missing from this list (quiz_exclusions, created_at). Updating only
    # the listed columns keeps a teacher's quiz-review work and the
    # story's original position in the list.
    with connect_db() as db:
        repo.upsert_story(
            db,
            id=story.id,
            title=story.title,
            frames=stored_frames,
            published=story.published,
            lesson_number=story.lessonNumber,
            lesson_sub_order=story.lessonSubOrder,
            rubric_scores=story.rubricScores,
            story_vocabulary=story.storyVocabulary,
            story_phrases=story.storyPhrases,
            vocab_assessment=story.vocabAssessment,
            conversation_turns=stored_conversation_turns,
            assessment_update_clause=assessment_update,
        )
    return {
        **story.model_dump(),
        "frames": stored_frames,
        "conversationTurns": stored_conversation_turns,
    }


def delete_story(story_id: str) -> None:
    """Opens its own ``connect_db()`` block (rather than taking an
    already-open connection) because the original router endpoint
    deliberately did the frame-media file cleanup after the DB connection
    was already closed - that ordering is preserved here verbatim.
    """
    with connect_db() as db:
        row = repo.find_story_frames_row(db, story_id)
        repo.delete_story(db, story_id)
    if row:
        for frame in row["frames"] or []:
            media_service.remove_uploaded_file(frame.get("imageUrl", ""))
            media_service.remove_uploaded_file(frame.get("imageUrlMedium", ""))
            media_service.remove_uploaded_file(frame.get("imageUrlHard", ""))
            media_service.remove_uploaded_file(frame.get("listenAudioUrl", ""))
        for turn in row.get("conversation_turns") or []:
            media_service.remove_uploaded_file(turn.get("audioUrl", ""))
            media_service.remove_uploaded_file(turn.get("targetAudioUrl", ""))
