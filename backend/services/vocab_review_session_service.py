"""Server-owned, resumable sessions for combined personalized and due review."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from analytics.learner_model.bkt.mastery import lock_student_bkt, normalize_word_id
from analytics.learner_model.review_queue import build_all_learned_review_queue
from api.schemas.models import VocabQuizAttemptRequest, VocabQuizQuestionResult
from services import vocab_quiz_attempt_service


MAX_REVIEW_SESSION_QUESTIONS = 12
REVIEW_SESSION_TTL = timedelta(days=7)
_QUESTION_TYPE_FOR_DIMENSION = {
    "meaning": "basic_meaning_mcq",
    "pinyin": "character_to_pinyin_typing",
    "context": "context_cloze_mcq",
}
_DIMENSION_FOR_QUESTION_TYPE = {value: key for key, value in _QUESTION_TYPE_FOR_DIMENSION.items()}


class ReviewSessionConflictError(Exception):
    """A session answer conflicts with its server-owned slot or prior answer."""


class ReviewSessionStaleError(ReviewSessionConflictError):
    """Published lesson vocabulary changed while a review session was open."""


def _json_value(value: Any) -> Any:
    # psycopg returns JSONB as native Python values. Keep fake/integration DBs
    # that expose strings usable as well.
    if isinstance(value, str):
        import json

        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _mix_queue(queue: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Take due:weak in a 2:1 rhythm, falling back when one side runs out."""
    due = [row for row in queue if row.get("reviewReason") == "due"]
    weak = [row for row in queue if row.get("reviewReason") == "weak"]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    positions = {"due": 0, "weak": 0}
    pattern = ("due", "due", "weak")
    pattern_position = 0
    while len(selected) < limit and (positions["due"] < len(due) or positions["weak"] < len(weak)):
        preferred = pattern[pattern_position % len(pattern)]
        pattern_position += 1
        reason = preferred
        if positions[reason] >= len(due if reason == "due" else weak):
            reason = "weak" if reason == "due" else "due"
        source = due if reason == "due" else weak
        if positions[reason] >= len(source):
            break
        row = source[positions[reason]]
        positions[reason] += 1
        word_id = str(row.get("wordId") or "")
        if word_id and word_id not in seen:
            seen.add(word_id)
            selected.append(row)
    return selected


def _requested_question_type(row: dict[str, Any]) -> str | None:
    if row.get("reviewReason") == "weak":
        dimension = ((row.get("vocabularyState") or {}).get("practice") or {}).get("nextDimension")
        return _QUESTION_TYPE_FOR_DIMENSION.get(str(dimension))

    seen_types = {str(value) for value in row.get("seenQuestionTypes", [])}
    choices = list(_QUESTION_TYPE_FOR_DIMENSION.values())
    repetitions = int((((row.get("vocabularyState") or {}).get("scheduling") or {}).get("reps")) or 0)
    start = repetitions % len(choices)
    choices = choices[start:] + choices[:start]
    unseen = [question_type for question_type in choices if question_type not in seen_types]
    return (unseen or choices)[0]


def _load_session_question(
    db: Any,
    row: dict[str, Any],
    position: int,
) -> dict[str, Any] | None:
    story_id = row.get("sourceStoryId")
    if not story_id:
        return None
    story = db.execute(
        "SELECT id, vocabulary_version, vocab_assessment FROM custom_stories "
        "WHERE id = %s AND published = TRUE FOR SHARE",
        (story_id,),
    ).fetchone()
    if not story:
        raise ReviewSessionStaleError("Lesson content changed. Reload the lesson and start a new review session.")
    expected_version = row.get("vocabularyVersion")
    if expected_version is not None and story.get("vocabulary_version") != expected_version:
        raise ReviewSessionStaleError("Lesson vocabulary changed. Reload the lesson and start a new review session.")

    requested_type = _requested_question_type(row)
    if not requested_type:
        return None
    word_id = normalize_word_id(str(row.get("wordId") or ""))
    assessment = _json_value(story.get("vocab_assessment")) or []
    item = next((
        candidate for candidate in assessment
        if isinstance(candidate, dict)
        and candidate.get("questionType") == requested_type
        and normalize_word_id(str(candidate.get("wordId") or "")) == word_id
        and candidate.get("questionId")
    ), None)
    if not item:
        # A weak dimension should have a published diagnostic item because
        # the lesson gate requires all three rounds. A missing item is not a
        # reason to substitute an unrelated skill or mark the learner wrong.
        return None
    if requested_type != "character_to_pinyin_typing" and not isinstance(item.get("options"), list):
        return None

    dimension = _DIMENSION_FOR_QUESTION_TYPE[requested_type]
    mode = "weak_words" if row.get("reviewReason") == "weak" else "maintenance_review"
    return {
        "slotId": f"slot-{position + 1}-{uuid4().hex[:10]}",
        "wordId": word_id,
        "word": str(item.get("targetWord") or row.get("word") or ""),
        "sourceStoryId": str(story["id"]),
        "vocabularyVersion": story.get("vocabulary_version"),
        "itemId": str(item["questionId"]),
        "questionType": requested_type,
        "dimension": dimension,
        "reviewReason": row.get("reviewReason"),
        "mode": mode,
        "answerFormat": item.get("answerFormat") or (
            "free_text" if requested_type == "character_to_pinyin_typing" else "single_choice"
        ),
        "prompt": str(item.get("prompt") or ""),
        "options": [str(value) for value in item.get("options", []) if isinstance(value, str)],
        "explanation": str(item.get("explanation") or ""),
    }


def _public_question(slot: dict[str, Any], index: int, count: int) -> dict[str, Any]:
    return {
        "slotId": slot["slotId"],
        "position": index + 1,
        "totalQuestions": count,
        "word": slot["word"],
        "sourceStoryId": slot["sourceStoryId"],
        "questionType": slot["questionType"],
        "dimension": slot["dimension"],
        "reviewReason": slot["reviewReason"],
        "answerFormat": slot["answerFormat"],
        "prompt": slot["prompt"],
        "options": slot["options"],
    }


def _session_payload(row: dict[str, Any]) -> dict[str, Any]:
    slots = _json_value(row.get("slots")) or []
    responses = _json_value(row.get("responses")) or {}
    answered = set(responses)
    current = next((index for index, slot in enumerate(slots) if slot["slotId"] not in answered), None)
    return {
        "sessionId": row["id"],
        "status": row["status"],
        "questionCount": len(slots),
        "completedCount": len(answered),
        "currentQuestion": _public_question(slots[current], current, len(slots)) if current is not None else None,
    }


def _read_active_session(db: Any, student_id: str) -> dict[str, Any] | None:
    return db.execute(
        "SELECT id, student_id, status, slots, responses, story_ids, expires_at, created_at, updated_at "
        "FROM vocab_review_sessions WHERE student_id = %s AND status = 'active' FOR UPDATE",
        (student_id,),
    ).fetchone()


def create_or_resume_review_session(db: Any, student_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Resume the active session or build one from the current global queue."""
    now = now or datetime.now(timezone.utc)
    lock_student_bkt(db, student_id)
    active = _read_active_session(db, student_id)
    if active:
        expires_at = active["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now:
            return {"session": _session_payload(active), "availableCount": len(_json_value(active.get("slots")) or [])}
        db.execute(
            "UPDATE vocab_review_sessions SET status = 'expired', updated_at = %s WHERE id = %s",
            (now, active["id"]),
        )

    review = build_all_learned_review_queue(
        db,
        student_id,
        {"includeAllWeak": True},
        now=now,
    )
    slots: list[dict[str, Any]] = []
    for candidate in _mix_queue(review.get("queue", []), MAX_REVIEW_SESSION_QUESTIONS):
        slot = _load_session_question(db, candidate, len(slots))
        if slot is not None:
            slots.append(slot)
    if not slots:
        return {"session": None, "availableCount": 0}

    session_id = str(uuid4())
    story_ids = list(dict.fromkeys(slot["sourceStoryId"] for slot in slots))
    created = db.execute(
        """
        INSERT INTO vocab_review_sessions
            (id, student_id, status, story_ids, slots, responses, expires_at, created_at, updated_at)
        VALUES (%s, %s, 'active', %s, %s, '{}'::jsonb, %s, %s, %s)
        RETURNING id, student_id, status, slots, responses, story_ids, expires_at, created_at, updated_at
        """,
        (session_id, student_id, story_ids, Jsonb(slots), now + REVIEW_SESSION_TTL, now, now),
    ).fetchone()
    return {"session": _session_payload(created), "availableCount": len(slots)}


def get_review_session(db: Any, student_id: str, session_id: str) -> dict[str, Any]:
    row = db.execute(
        "SELECT id, student_id, status, slots, responses, story_ids, expires_at, created_at, updated_at "
        "FROM vocab_review_sessions WHERE id = %s AND student_id = %s",
        (session_id, student_id),
    ).fetchone()
    if not row:
        raise ReviewSessionConflictError("Review session was not found.")
    payload = _session_payload(row)
    payload["responses"] = [
        {"slotId": key, **value}
        for key, value in sorted((_json_value(row.get("responses")) or {}).items(), key=lambda pair: pair[1].get("position", 0))
    ]
    return payload


def answer_review_session_question(
    db: Any,
    student_id: str,
    session_id: str,
    slot_id: str,
    selected_answer: str,
    response_time_ms: int,
    *,
    now: datetime,
    day_seconds: float,
) -> dict[str, Any]:
    """Grade a server-selected slot and persist ledger + session atomically."""
    lock_student_bkt(db, student_id)
    row = db.execute(
        "SELECT id, student_id, status, slots, responses, story_ids, expires_at "
        "FROM vocab_review_sessions WHERE id = %s AND student_id = %s FOR UPDATE",
        (session_id, student_id),
    ).fetchone()
    if not row:
        raise ReviewSessionConflictError("Review session was not found.")
    slots = _json_value(row["slots"]) or []
    responses = _json_value(row["responses"]) or {}
    previous = responses.get(slot_id)
    if previous is not None:
        if previous.get("selectedAnswer") != selected_answer:
            raise ReviewSessionConflictError("This question already has a different saved answer.")
        return {"result": previous, "session": _session_payload(row)}
    if row["status"] != "active":
        raise ReviewSessionConflictError("This review session is no longer active.")

    slot_index = next((index for index, slot in enumerate(slots) if slot["slotId"] == slot_id), None)
    if slot_index is None:
        raise ReviewSessionConflictError("Question does not belong to this review session.")
    next_index = next((index for index, slot in enumerate(slots) if slot["slotId"] not in responses), None)
    if slot_index != next_index:
        raise ReviewSessionConflictError("Answer the current question before continuing.")

    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise ReviewSessionConflictError("This review session expired. Start a new session to continue.")

    slot = slots[slot_index]
    story = db.execute(
        "SELECT vocabulary_version FROM custom_stories WHERE id = %s AND published = TRUE FOR SHARE",
        (slot["sourceStoryId"],),
    ).fetchone()
    if not story or story["vocabulary_version"] != slot["vocabularyVersion"]:
        raise ReviewSessionStaleError("Lesson vocabulary changed. Reload the lesson and start a new review session.")

    answered_at = now.isoformat()
    quiz_id = f"review-{session_id}-{slot_index + 1}"
    attempt = VocabQuizAttemptRequest(
        id=quiz_id,
        storyId=slot["sourceStoryId"],
        baseStoryId=slot["sourceStoryId"],
        vocabularyVersion=slot["vocabularyVersion"],
        studentName="Student",
        mode=slot["mode"],
        completedAt=answered_at,
        totalQuestions=1,
        correctCount=0,
        totalTimeMs=response_time_ms,
        questionResults=[VocabQuizQuestionResult(
            word=slot["word"],
            correct=False,  # The authoritative assessment resolver replaces this.
            timeMs=response_time_ms,
            itemId=slot["itemId"],
            conceptId=slot["wordId"],
            questionKind=slot["questionType"],
            knowledgeDimension={
                "meaning": "meaning",
                "pinyin": "pinyin_production",
                "context": "contextual_recall",
            }[slot["dimension"]],
            activityType="personalized_practice" if slot["mode"] == "weak_words" else "scheduled_maintenance",
            baseStoryId=slot["sourceStoryId"],
            selectedAnswer=selected_answer,
            presentedOptions=slot["options"],
            questionPrompt=slot["prompt"],
            answeredAt=answered_at,
            questionIndex=0,
            quizId=quiz_id,
        )],
    )
    authoritative = vocab_quiz_attempt_service.record_response(
        db,
        attempt,
        student_id,
        now=now,
        day_seconds=day_seconds,
    )
    resolved = authoritative[0]
    result = {
        "slotId": slot_id,
        "position": slot_index + 1,
        "word": resolved["word"],
        "reviewReason": slot["reviewReason"],
        "dimension": slot["dimension"],
        "correct": bool(resolved["correct"]),
        "correctAnswer": resolved["correctAnswer"],
        "explanation": slot["explanation"],
        "selectedAnswer": selected_answer,
        "answeredAt": answered_at,
    }
    responses[slot_id] = result
    status = "completed" if len(responses) == len(slots) else "active"
    updated = db.execute(
        """
        UPDATE vocab_review_sessions
        SET responses = %s, status = %s, updated_at = %s
        WHERE id = %s
        RETURNING id, student_id, status, slots, responses, story_ids, expires_at, created_at, updated_at
        """,
        (Jsonb(responses), status, now, session_id),
    ).fetchone()
    return {"result": result, "session": _session_payload(updated)}


def defer_review_session(db: Any, student_id: str, session_id: str, *, now: datetime) -> dict[str, Any]:
    lock_student_bkt(db, student_id)
    row = db.execute(
        "UPDATE vocab_review_sessions SET status = 'deferred', updated_at = %s "
        "WHERE id = %s AND student_id = %s AND status = 'active' "
        "RETURNING id, student_id, status, slots, responses, story_ids, expires_at, created_at, updated_at",
        (now, session_id, student_id),
    ).fetchone()
    if not row:
        raise ReviewSessionConflictError("This review session is no longer active.")
    return _session_payload(row)
