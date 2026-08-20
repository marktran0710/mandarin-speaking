"""Teacher pronunciation-validation review flow.

Implements PARTS 5-10 and 14 of the small-teacher-validated-pilot
architecture (`benchmarking/results/pilot_teacher_validation_integration.md`):
a two-stage review over `audio_records` rows that carry pilot attempt
identity (migration 0010), writing into `teacher_pronunciation_ratings`
(migration 0011).

Stage 1 (blind, independent pronunciation rubric) and Stage 2 (system
feedback review, unlocked only after that teacher's own Stage 1 row exists)
are deliberately separate response builders below (`_blind_targets` vs
`_system_output`) rather than one function with a `blind: bool` flag --
blinding here is a hard boundary at the query/serialization layer, not a
runtime conditional a future edit could accidentally invert. Neither
function nor any Stage-1 endpoint ever reads `word_prosody[].passed`,
`analysis_version`, `assistive_state`, `e2_diagnostic_category`,
`explanation`, or any F1/E2 score off `praat_metrics` -- only the
deterministic, recording-independent expected-tone plan (the same
ground-truth "target" a paper rubric would print), which a human rater
needs regardless of what any machine later said about a specific
recording.

`teacher_id` provenance (PART 15): the frontend teacher session's
freely-typed `session.name` (`src/utils/session.ts`). This app has no
teacher password or `teachers` table -- see the existing role-separation
design -- so this reuses the same low-friction identity already used for
every other teacher-facing feature, rather than inventing new auth. This is
a real limitation worth naming plainly: `teacher_id` is self-declared, not
cryptographically authenticated. It is sufficient to keep two teachers'
independent ratings apart (PART 9), which is the property this task needs.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, Optional

import psycopg.errors
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, model_validator

from database import connect_db
import auth

router = APIRouter(
    prefix="/api/teacher-review",
    tags=["teacher-review"],
    dependencies=[Depends(auth.require_teacher_or_admin)],
)

RatingStage = Literal["stage_1_blind", "stage_2_feedback_review"]
FeedbackAppropriateness = Literal["APPROPRIATE", "PARTIALLY_APPROPRIATE", "INAPPROPRIATE"]


def _item_id(topic_id: Optional[str], image_index: Optional[int]) -> Optional[str]:
    if topic_id is None or image_index is None:
        return None
    return f"{topic_id}:{image_index}"


def _fetch_audio_record(db, audio_record_id: str) -> dict[str, Any]:
    row = db.execute(
        "SELECT * FROM audio_records WHERE id = %s", (audio_record_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Audio record not found")
    if not row.get("attempt_id") or not row.get("student_id"):
        raise HTTPException(
            status_code=400,
            detail="This recording has no pilot attempt identity and cannot be reviewed.",
        )
    return row


def _blind_targets(praat_metrics: Optional[dict]) -> list[dict[str, Any]]:
    """Stage-1 syllable targets: the expected-tone plan only. Never
    includes `assistive_state`, `e2_diagnostic_category`, `explanation`, or
    any score -- see the module docstring."""
    feedback = (praat_metrics or {}).get("assistive_feedback") or []
    return [
        {
            "syllable_index": item.get("syllable_index"),
            "character": item.get("character"),
            "expected_underlying_tone": item.get("expected_underlying_tone"),
            "accepted_surface_tones": item.get("accepted_surface_tones"),
            "context_rule": item.get("context_rule"),
            "realization": item.get("realization"),
        }
        for item in feedback
    ]


def _system_output(praat_metrics: Optional[dict]) -> list[dict[str, Any]]:
    """Stage-2 system output: adds E2's explanation and the learner-facing
    assistive state/message actually shown. Deliberately still omits raw F1
    risk probability and raw E2 continuous score -- PART 10 authorizes "E2
    explanation" (categorical + rationale), not the numeric machine opinion,
    to avoid anchoring the teacher's pedagogical judgment on a raw number.
    The raw scores remain available for later statistical validity analysis
    via `assistive_feedback/research_log.py`, never through this endpoint."""
    feedback = (praat_metrics or {}).get("assistive_feedback") or []
    return [
        {
            "syllable_index": item.get("syllable_index"),
            "character": item.get("character"),
            "expected_underlying_tone": item.get("expected_underlying_tone"),
            "accepted_surface_tones": item.get("accepted_surface_tones"),
            "context_rule": item.get("context_rule"),
            "realization": item.get("realization"),
            "e2_diagnostic_category": item.get("e2_diagnostic_category"),
            "explanation": item.get("explanation"),
            "assistive_state": item.get("assistive_state"),
            "assistive_state_label": item.get("assistive_state_label"),
            "assistive_message": item.get("assistive_message"),
        }
        for item in feedback
    ]


def _has_rating(db, teacher_id: str, attempt_id: str, stage: RatingStage) -> bool:
    row = db.execute(
        """
        SELECT 1 FROM teacher_pronunciation_ratings
        WHERE teacher_id = %s AND attempt_id = %s AND rating_stage = %s
        LIMIT 1
        """,
        (teacher_id, attempt_id, stage),
    ).fetchone()
    return row is not None


@router.get("/queue")
async def review_queue(teacher_id: str = Query(...)):
    """PART 14: pseudonymous participant/item/attempt_type/status only --
    no system prediction, no student name (participant_id is already the
    opaque roster uuid, not a display name)."""
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT
                ar.id AS audio_record_id,
                ar.student_id AS participant_id,
                ar.topic_id,
                ar.image_index,
                ar.session_id,
                ar.attempt_id,
                ar.attempt_number,
                ar.attempt_type,
                ar.created_at,
                EXISTS (
                    SELECT 1 FROM teacher_pronunciation_ratings r
                    WHERE r.teacher_id = %(teacher_id)s AND r.attempt_id = ar.attempt_id
                        AND r.rating_stage = 'stage_1_blind'
                ) AS stage1_done,
                EXISTS (
                    SELECT 1 FROM teacher_pronunciation_ratings r
                    WHERE r.teacher_id = %(teacher_id)s AND r.attempt_id = ar.attempt_id
                        AND r.rating_stage = 'stage_2_feedback_review'
                ) AS stage2_done
            FROM audio_records ar
            WHERE ar.attempt_id IS NOT NULL
            ORDER BY ar.created_at DESC
            """,
            {"teacher_id": teacher_id},
        ).fetchall()

    queue = []
    for row in rows:
        status = "NOT_STARTED"
        if row["stage2_done"]:
            status = "STAGE_2_COMPLETE"
        elif row["stage1_done"]:
            status = "STAGE_1_COMPLETE"
        queue.append({
            "audio_record_id": row["audio_record_id"],
            "participant_id": row["participant_id"],
            "item_id": _item_id(row["topic_id"], row["image_index"]),
            "session_id": row["session_id"],
            "attempt_id": row["attempt_id"],
            "attempt_number": row["attempt_number"],
            "attempt_type": row["attempt_type"],
            "review_status": status,
        })
    return queue


@router.get("/attempt/{audio_record_id}/stage1")
async def get_stage1_view(audio_record_id: str):
    with connect_db() as db:
        row = _fetch_audio_record(db, audio_record_id)

    return {
        "audio_record_id": row["id"],
        "participant_id": row["student_id"],
        "item_id": _item_id(row["topic_id"], row["image_index"]),
        "session_id": row["session_id"],
        "attempt_id": row["attempt_id"],
        "attempt_number": row["attempt_number"],
        "attempt_type": row["attempt_type"],
        "audio_url": row["audio_url"],
        "script": row["transcription"],
        "targets": _blind_targets(row["praat_metrics"]),
    }


@router.get("/attempt/{audio_record_id}/stage2")
async def get_stage2_view(audio_record_id: str, teacher_id: str = Query(...)):
    with connect_db() as db:
        row = _fetch_audio_record(db, audio_record_id)
        if not _has_rating(db, teacher_id, row["attempt_id"], "stage_1_blind"):
            raise HTTPException(
                status_code=403,
                detail="Stage 2 is locked until this teacher submits a Stage 1 rating for this attempt.",
            )

    praat_metrics = row["praat_metrics"] or {}
    return {
        "audio_record_id": row["id"],
        "participant_id": row["student_id"],
        "item_id": _item_id(row["topic_id"], row["image_index"]),
        "session_id": row["session_id"],
        "attempt_id": row["attempt_id"],
        "attempt_number": row["attempt_number"],
        "attempt_type": row["attempt_type"],
        "audio_url": row["audio_url"],
        "script": row["transcription"],
        "pitch_contour": praat_metrics.get("pitch_contour"),
        "system_output": _system_output(praat_metrics),
    }


class TeacherStage1RatingRequest(BaseModel):
    teacher_id: str
    audio_record_id: str
    # None = sentence-level rating.
    syllable_index: Optional[int] = None
    consonant_score: Optional[Literal[0, 1]] = None
    vowel_score: Optional[Literal[0, 1]] = None
    tone_score: Optional[Literal[0, 1]] = None
    accuracy_score: Optional[Literal[1, 2, 3, 4, 5]] = None
    fluency_score: Optional[Literal[1, 2, 3, 4, 5]] = None
    prosody_score: Optional[Literal[1, 2, 3, 4, 5]] = None

    @model_validator(mode="after")
    def _check_shape(self) -> "TeacherStage1RatingRequest":
        syllable_fields_set = any(
            v is not None for v in (self.consonant_score, self.vowel_score, self.tone_score)
        )
        sentence_fields_set = any(
            v is not None for v in (self.accuracy_score, self.fluency_score, self.prosody_score)
        )
        if self.syllable_index is not None:
            if not syllable_fields_set or sentence_fields_set:
                raise ValueError(
                    "A syllable-level rating (syllable_index set) must provide "
                    "consonant/vowel/tone scores only, not sentence-level scores."
                )
        else:
            if not sentence_fields_set or syllable_fields_set:
                raise ValueError(
                    "A sentence-level rating (syllable_index = null) must provide "
                    "accuracy/fluency/prosody scores only, not syllable-level scores."
                )
        return self


class TeacherStage2RatingRequest(BaseModel):
    teacher_id: str
    audio_record_id: str
    syllable_index: Optional[int] = None
    retry_recommended: bool
    feedback_appropriateness: FeedbackAppropriateness


@router.post("/ratings/stage1")
async def submit_stage1_rating(rating: TeacherStage1RatingRequest):
    with connect_db() as db:
        audio_row = _fetch_audio_record(db, rating.audio_record_id)

    rating_id = str(uuid.uuid4())
    try:
        with connect_db() as db:
            db.execute(
                """
                INSERT INTO teacher_pronunciation_ratings (
                    rating_id, teacher_id, audio_record_id, participant_id,
                    session_id, item_id, attempt_id, syllable_index,
                    consonant_score, vowel_score, tone_score,
                    accuracy_score, fluency_score, prosody_score,
                    rating_stage
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    rating_id,
                    rating.teacher_id,
                    audio_row["id"],
                    audio_row["student_id"],
                    audio_row["session_id"],
                    _item_id(audio_row["topic_id"], audio_row["image_index"]),
                    audio_row["attempt_id"],
                    rating.syllable_index,
                    rating.consonant_score,
                    rating.vowel_score,
                    rating.tone_score,
                    rating.accuracy_score,
                    rating.fluency_score,
                    rating.prosody_score,
                    "stage_1_blind",
                ),
            )
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=409,
            detail="This teacher has already submitted a Stage 1 rating for this attempt/syllable. Ratings are never overwritten.",
        ) from exc

    return {"rating_id": rating_id, "rating_stage": "stage_1_blind"}


@router.post("/ratings/stage2")
async def submit_stage2_rating(rating: TeacherStage2RatingRequest):
    with connect_db() as db:
        audio_row = _fetch_audio_record(db, rating.audio_record_id)
        if not _has_rating(db, rating.teacher_id, audio_row["attempt_id"], "stage_1_blind"):
            raise HTTPException(
                status_code=403,
                detail="Stage 2 is locked until this teacher submits a Stage 1 rating for this attempt.",
            )

    rating_id = str(uuid.uuid4())
    try:
        with connect_db() as db:
            db.execute(
                """
                INSERT INTO teacher_pronunciation_ratings (
                    rating_id, teacher_id, audio_record_id, participant_id,
                    session_id, item_id, attempt_id, syllable_index,
                    retry_recommended, feedback_appropriateness,
                    rating_stage
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    rating_id,
                    rating.teacher_id,
                    audio_row["id"],
                    audio_row["student_id"],
                    audio_row["session_id"],
                    _item_id(audio_row["topic_id"], audio_row["image_index"]),
                    audio_row["attempt_id"],
                    rating.syllable_index,
                    rating.retry_recommended,
                    rating.feedback_appropriateness,
                    "stage_2_feedback_review",
                ),
            )
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=409,
            detail="This teacher has already submitted a Stage 2 rating for this attempt/syllable. Ratings are never overwritten.",
        ) from exc

    return {"rating_id": rating_id, "rating_stage": "stage_2_feedback_review"}
