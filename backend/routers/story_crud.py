from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb

from db import connect_db, row_to_custom_story
import security.auth as auth
import services.media as media_service
from api.schemas.models import CustomStoryRequest
from routers.story_quiz_vocabulary import router as story_quiz_vocabulary_router
from routers.story_vocabulary_metadata import router as story_vocabulary_metadata_router
from domain.vocabulary.assessment import validate_assessment_payload

# Students may read lesson content after login; story writes and generated
# media are restricted by auth.require_story_access to teacher/admin accounts.
router = APIRouter(dependencies=[Depends(auth.require_story_access)])

# Nested so both story-vocabulary responsibilities pick up this router's
# require_story_access dependency and their own require_admin dependency.
router.include_router(story_vocabulary_metadata_router)
router.include_router(story_quiz_vocabulary_router)

# Stories carried per-difficulty-tier fields before the Medium/Hard tiers
# were removed; kept for now since deleting it isn't this move's job.
_TIER_SUFFIX = {"easy": ""}


def _tier_field(base: str, tier: str) -> str:
    return f"{base}{_TIER_SUFFIX.get(tier, '')}"


@router.get("/api/custom-stories")
def list_custom_stories(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    visibility = "WHERE published = TRUE" if identity.role == "student" else ""
    with connect_db() as db:
        rows = db.execute(
            f"SELECT * FROM custom_stories {visibility} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, skip),
        ).fetchall()
    return [row_to_custom_story(row) for row in rows]


@router.post("/api/custom-stories")
async def create_custom_story(story: CustomStoryRequest):
    if story.vocabAssessment is not None:
        assessment_issues = validate_assessment_payload(story.vocabAssessment)
        if assessment_issues:
            raise HTTPException(
                status_code=422,
                detail={
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
    with connect_db() as db:
        # ON CONFLICT DO UPDATE, not the old INSERT OR REPLACE: SQLite's
        # replace was a DELETE+INSERT, so every re-save wiped the two columns
        # missing from this list (quiz_exclusions, created_at). Updating only
        # the listed columns keeps a teacher's quiz-review work and the
        # story's original position in the list.
        db.execute(
            f"""
            INSERT INTO custom_stories (
                id, title, frames, published,
                lesson_number, lesson_sub_order, rubric_scores,
                story_vocabulary, story_phrases, vocab_assessment,
                conversation_turns
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                frames = EXCLUDED.frames,
                published = EXCLUDED.published,
                lesson_number = EXCLUDED.lesson_number,
                lesson_sub_order = EXCLUDED.lesson_sub_order,
                rubric_scores = EXCLUDED.rubric_scores,
                story_vocabulary = EXCLUDED.story_vocabulary,
                story_phrases = EXCLUDED.story_phrases,
                conversation_turns = EXCLUDED.conversation_turns,
                {assessment_update}
            """,
            (
                story.id,
                story.title,
                Jsonb(stored_frames),
                story.published,
                story.lessonNumber,
                story.lessonSubOrder,
                Jsonb(story.rubricScores) if story.rubricScores is not None else None,
                Jsonb(story.storyVocabulary) if story.storyVocabulary is not None else None,
                Jsonb(story.storyPhrases) if story.storyPhrases is not None else None,
                Jsonb(story.vocabAssessment) if story.vocabAssessment is not None else None,
                Jsonb([turn.model_dump() for turn in story.conversationTurns]) if story.conversationTurns is not None else None,
            ),
        )
    return {
        **story.model_dump(),
        "frames": stored_frames,
    }


@router.delete("/api/custom-stories/{story_id}")
def delete_custom_story(story_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s",
            (story_id,),
        ).fetchone()
        db.execute("DELETE FROM custom_stories WHERE id = %s", (story_id,))
    if row:
        for frame in row["frames"] or []:
            media_service.remove_uploaded_file(frame.get("imageUrl", ""))
            media_service.remove_uploaded_file(frame.get("imageUrlMedium", ""))
            media_service.remove_uploaded_file(frame.get("imageUrlHard", ""))
            media_service.remove_uploaded_file(frame.get("listenAudioUrl", ""))
    return {"ok": True}
