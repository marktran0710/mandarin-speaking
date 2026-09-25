"""Persistence for the SM-2 schedule (``student_vocab_srs``).

Thin DB accessors around the ``SrsState`` value object in analytics/srs.py.
Deliberately separate from analytics/srs.py (pure algorithm) and from
bkt_mastery (BKT mastery is untouched by scheduling).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from analytics.learner_model.srs import (
    DAY_SECONDS,
    FIRST_INTERVAL_DAYS,
    INITIAL_EASE,
    SRS_ALGORITHM_VERSION,
    SrsState,
    is_due,
    quality_from_response,
    review,
    should_advance,
)


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _row_to_state(row: Any) -> SrsState:
    return SrsState(
        reps=int(row["reps"]),
        ease=float(row["ease"]),
        interval_days=int(row["interval_days"]),
        due_on=_to_datetime(row["due_on"]),
        last_reviewed_on=_to_datetime(row["last_reviewed_on"]),
    )


_SELECT = (
    "SELECT word_id, reps, ease, interval_days, due_on, last_reviewed_on "
    "FROM student_vocab_srs WHERE student_id = %s"
)


def load_srs_states(db: Any, student_id: str, word_ids: Iterable[str] | None = None) -> dict[str, SrsState]:
    """Load the SM-2 state for a student, optionally scoped to some words."""
    if word_ids is not None:
        ids = list(word_ids)
        if not ids:
            return {}
        rows = db.execute(f"{_SELECT} AND word_id = ANY(%s)", (student_id, ids)).fetchall()
    else:
        rows = db.execute(_SELECT, (student_id,)).fetchall()
    return {str(row["word_id"]): _row_to_state(row) for row in rows}


def upsert_srs_state(db: Any, student_id: str, word_id: str, state: SrsState) -> None:
    """Write (insert or update) one word's SM-2 schedule."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO student_vocab_srs
            (student_id, word_id, reps, ease, interval_days, due_on,
             last_reviewed_on, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (student_id, word_id) DO UPDATE SET
            reps = EXCLUDED.reps,
            ease = EXCLUDED.ease,
            interval_days = EXCLUDED.interval_days,
            due_on = EXCLUDED.due_on,
            last_reviewed_on = EXCLUDED.last_reviewed_on,
            updated_at = EXCLUDED.updated_at
        """,
        (
            student_id, word_id, state.reps, state.ease, state.interval_days,
            state.due_on, state.last_reviewed_on, now, now,
        ),
    )


def record_srs_event(
    db: Any,
    student_id: str,
    word_id: str,
    event_type: str,
    old_state: SrsState,
    new_state: SrsState,
    *,
    source_response_id: str,
    quiz_id: str | None = None,
    attempt_id: str | None = None,
    correct: bool | None = None,
    quality: int | None = None,
    occurred_at: datetime | None = None,
) -> bool:
    """Append one immutable transition and report whether it was new.

    The caller must insert the event before updating the current projection.
    Both statements use the same transaction and learner lock, so a replayed
    source response cannot advance the projection after the event has already
    been accepted.
    """
    cursor = db.execute(
        """
        INSERT INTO student_vocab_srs_events
            (student_id, word_id, source_response_id, quiz_id, attempt_id,
             event_type, correct, quality, old_reps, new_reps, old_ease,
             new_ease, old_interval_days, new_interval_days, old_due_on,
             new_due_on, algorithm_version, occurred_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s)
        ON CONFLICT (student_id, word_id, source_response_id) DO NOTHING
        RETURNING id
        """,
        (
            student_id, word_id, source_response_id, quiz_id, attempt_id,
            event_type, correct, quality, old_state.reps, new_state.reps,
            old_state.ease, new_state.ease, old_state.interval_days,
            new_state.interval_days, old_state.due_on, new_state.due_on,
            SRS_ALGORITHM_VERSION, occurred_at or new_state.last_reviewed_on,
        ),
    )
    return cursor.fetchone() is not None


def enroll_strong_words(
    db: Any,
    student_id: str,
    mastery_rows: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    day_seconds: float = DAY_SECONDS,
) -> int:
    """Create the first schedule for newly official strong words only.

    Enrollment is deliberately distinct from grading a scheduled review. It
    never overwrites an existing schedule, so a corrective practice answer
    cannot move an already scheduled word's due date.
    """
    rows = list(mastery_rows)
    word_ids = [str(row["wordId"]) for row in rows if row.get("wordId")]
    existing = load_srs_states(db, student_id, word_ids)
    enrolled = 0
    started_at = now or datetime.now(timezone.utc)
    for row in rows:
        word_id = str(row.get("wordId") or "")
        if not word_id or word_id in existing:
            continue
        vocabulary_state = row.get("vocabularyState") or {}
        if (vocabulary_state.get("review") or {}).get("status") != "STRONG":
            continue
        # A newly official word receives its first one-day interval. This is
        # enrollment, not a maintenance answer: no artificial q=5 review is
        # generated and the ease remains at the configured initial value.
        enrolled_state = SrsState(
            reps=1,
            ease=INITIAL_EASE,
            interval_days=FIRST_INTERVAL_DAYS,
            due_on=started_at + timedelta(seconds=day_seconds * FIRST_INTERVAL_DAYS),
            last_reviewed_on=started_at,
        )
        accepted = record_srs_event(
            db,
            student_id,
            word_id,
            "enrollment",
            SrsState(),
            enrolled_state,
            source_response_id=f"enrollment:{word_id}",
            occurred_at=started_at,
        )
        if not accepted:
            continue
        upsert_srs_state(db, student_id, word_id, enrolled_state)
        enrolled += 1
    return enrolled


def _word_id_of(result: dict[str, Any]) -> str | None:
    value = result.get("conceptId") or result.get("word")
    return str(value) if value else None


def apply_srs_updates(
    db: Any,
    student_id: str,
    question_results: Iterable[dict[str, Any]],
    now: datetime | None = None,
    day_seconds: float = DAY_SECONDS,
) -> int:
    """Advance the SM-2 schedule for each word answered in a review session.

    One graded advance per word per ``day_seconds`` cycle (``should_advance``);
    the last answer for a word in the batch wins. Returns how many words were
    rescheduled. Scheduling only — the caller still feeds these answers to BKT
    unchanged. ``day_seconds`` lets a caller compress the whole cycle (e.g. for
    fast manual/demo testing) without changing anything else about the algorithm.
    """
    now = now or datetime.now(timezone.utc)
    last_by_word: dict[str, dict[str, Any]] = {}
    for result in question_results:
        if result.get("authoritativeResolved") is not True:
            # SRS is a research schedule, so a client-provided correctness
            # value from an unknown/stale assessment item must never mutate it.
            continue
        if result.get("activityType") in {"personalized_practice", "practice"}:
            # Corrective practice updates BKT only; it never advances SRS.
            continue
        word_id = _word_id_of(result)
        if word_id is not None and isinstance(result.get("correct"), bool):
            last_by_word[word_id] = result
    if not last_by_word:
        return 0
    states = load_srs_states(db, student_id, list(last_by_word))
    updated = 0
    for word_id, result in last_by_word.items():
        state = states.get(word_id)
        if state is None:
            # Maintenance is allowed to update an existing schedule only.
            # Enrollment is exclusively driven by server-derived STRONG state.
            continue
        # A scheduled-maintenance caller may only grade a word once it is due.
        # This guard is intentionally here as well as at the route boundary so
        # a corrective weak-word response can never advance SRS accidentally.
        if not is_due(state, now) or not should_advance(state, now, day_seconds=day_seconds):
            continue
        source_response_id = (
            str(result.get("sourceResponseId") or result.get("responseId") or result.get("quizId"))
            if (result.get("sourceResponseId") or result.get("responseId") or result.get("quizId"))
            else None
        )
        if not source_response_id:
            # A maintenance transition without a stable source identity cannot
            # be made idempotent, so it must not mutate the research schedule.
            continue
        time_ms = result.get("timeMs")
        if time_ms is None:
            time_ms = result.get("time_ms")
        q = quality_from_response(bool(result["correct"]), time_ms)
        next_state = review(state, q, now, day_seconds=day_seconds)
        accepted = record_srs_event(
            db,
            student_id,
            word_id,
            "maintenance_success" if result["correct"] else "maintenance_failure",
            state,
            next_state,
            source_response_id=source_response_id,
            quiz_id=str(result["quizId"]) if result.get("quizId") else None,
            attempt_id=str(result["attemptId"]) if result.get("attemptId") else None,
            correct=bool(result["correct"]),
            quality=q,
            occurred_at=now,
        )
        if not accepted:
            continue
        upsert_srs_state(db, student_id, word_id, next_state)
        updated += 1
    return updated
