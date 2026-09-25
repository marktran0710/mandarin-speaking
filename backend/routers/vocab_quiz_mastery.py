from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
from analytics.learner_model.bkt.mastery import (
    diagnostic_status,
    get_priority_review_words,
    get_vocabulary_mastery,
    seen_item_ids,
)
from analytics.learner_model.review_queue import build_review_queue
from db import connect_db
from routers.vocab_quiz_attempts import _dev_srs_today


router = APIRouter()


def _assert_student_scope(identity: auth.Identity, student_id: str) -> None:
    if identity.role == "student" and identity.id != student_id:
        raise HTTPException(status_code=403, detail="Students may only view their own vocabulary mastery.")


@router.get("/api/students/{student_id}/weak-words")
def get_student_priority_review_words(
    student_id: str,
    review_count: Optional[int] = None,
    story_id: Optional[str] = None,
    include_all: bool = False,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Return learner-relative Bottom-K BKT review priorities."""
    _assert_student_scope(identity, student_id)
    options = {key: value for key, value in (("reviewCount", review_count), ("storyId", story_id)) if value is not None}
    if include_all:
        options["includeAllWeak"] = True
    with connect_db() as db:
        return get_priority_review_words(db, student_id, options)


@router.get("/api/students/{student_id}/review-queue")
async def get_student_review_queue(
    student_id: str,
    review_count: Optional[int] = None,
    story_id: Optional[str] = None,
    include_all: bool = False,
    today: Optional[str] = None,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Weak words (BKT) plus due words (SM-2), tagged weak|due for the UI."""
    _assert_student_scope(identity, student_id)
    options = {key: value for key, value in (("reviewCount", review_count), ("storyId", story_id)) if value is not None}
    if include_all:
        options["includeAllWeak"] = True
    with connect_db() as db:
        return build_review_queue(db, student_id, options, now=_dev_srs_today(today))


@router.get("/api/students/{student_id}/vocabulary-mastery")
def get_student_vocabulary_mastery(
    student_id: str,
    story_id: Optional[str] = None,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    _assert_student_scope(identity, student_id)
    with connect_db() as db:
        return {
            **diagnostic_status(db, student_id, story_id=story_id),
            "words": get_vocabulary_mastery(db, student_id, story_id=story_id),
        }


@router.get("/api/students/{student_id}/vocabulary-mastery/{word_id:path}/seen-items")
def get_seen_vocabulary_items(
    student_id: str,
    word_id: str,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    _assert_student_scope(identity, student_id)
    with connect_db() as db:
        return {"itemIds": seen_item_ids(db, student_id, word_id)}


@router.get("/api/vocab-quiz-attempts/weak-words")
def get_weak_words(
    story_id: str,
    include_all: bool = False,
    identity: auth.Identity = Depends(auth.require_student),
):
    """Compatibility-shaped response backed by guarded standard BKT."""
    with connect_db() as db:
        result = get_priority_review_words(db, identity.id, {"storyId": story_id, "includeAllWeak": include_all})
    return {
        "words": [word["word"] for word in result["words"]],
        "diagnostic": {
            key: result[key]
            for key in (
                "unlocked", "requiredDiagnosticQuizzes", "completedDiagnosticQuizzes",
                "requiredWords", "sufficientWords", "wordCoverage", "roundPresence", "diagnosticComplete",
            )
        },
    }
