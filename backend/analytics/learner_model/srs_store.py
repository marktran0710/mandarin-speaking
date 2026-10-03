"""Persistence for the SM-2 schedule (``student_vocab_srs``).

Thin DB accessors around the ``SrsState`` value object in analytics/srs.py.
Deliberately separate from analytics/srs.py (pure algorithm) and from
bkt_mastery (BKT mastery is untouched by scheduling).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import random
import secrets
from typing import Any, Iterable

from psycopg.types.json import Jsonb

from analytics.learner_model.srs import (
    DAY_SECONDS,
    FIRST_INTERVAL_DAYS,
    INITIAL_EASE,
    SRS_ALGORITHM_VERSION,
    SrsState,
    is_due,
    quality_from_response,
    review,
    enrollment_state,
    should_advance,
)


REVIEW_ACTIVITIES = ("meaning", "pinyin", "context")
_REVIEW_ACTIVITY_BAG_VERSION = 1


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


def _decode_bag(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = {}
    if not isinstance(value, dict) or value.get("version") != _REVIEW_ACTIVITY_BAG_VERSION:
        return {}
    return value


def _shuffle_activity_cycle(seed: str, cycle: int) -> list[str]:
    """Build a reproducible pseudorandom order for one persisted bag cycle."""
    cycle_seed = int.from_bytes(sha256(f"{seed}:{cycle}".encode("utf-8")).digest(), "big")
    activities = list(REVIEW_ACTIVITIES)
    random.Random(cycle_seed).shuffle(activities)
    return activities


def reserve_review_activity(
    db: Any,
    student_id: str,
    word_id: str,
    *,
    seed: str | None = None,
) -> str:
    """Reserve the next item activity without consuming it until it is answered.

    The seed, cycle order, remaining bag, and pending activity live with the
    word's SRS schedule. A resumed/deferred session therefore receives the
    same activity, and tests can pass a fixed seed to assert the full cycle.
    """
    row = db.execute(
        "SELECT review_activity_bag FROM student_vocab_srs "
        "WHERE student_id = %s AND word_id = %s FOR UPDATE",
        (student_id, word_id),
    ).fetchone()
    if row is None:
        raise ValueError("Cannot select a review activity for a word without an SM-2 schedule.")

    bag = _decode_bag(row.get("review_activity_bag"))
    bag_seed = str(bag.get("seed") or seed or secrets.token_hex(16))
    remaining = bag.get("remaining")
    if not isinstance(remaining, list) or any(value not in REVIEW_ACTIVITIES for value in remaining):
        remaining = []
    pending = bag.get("pendingActivity")
    if pending in REVIEW_ACTIVITIES:
        return str(pending)

    cycle = max(0, int(bag.get("cycle") or 0))
    order = bag.get("order")
    if not remaining:
        cycle += 1
        order = _shuffle_activity_cycle(bag_seed, cycle)
        remaining = list(order)
    elif not isinstance(order, list) or set(order) != set(REVIEW_ACTIVITIES):
        # Recover a partially initialized/older bag without losing any valid
        # activity already queued in ``remaining``.
        order = [*remaining, *(value for value in REVIEW_ACTIVITIES if value not in remaining)]

    pending = remaining[0]
    updated_bag = {
        "version": _REVIEW_ACTIVITY_BAG_VERSION,
        "seed": bag_seed,
        "cycle": cycle,
        "order": order,
        "remaining": remaining,
        "pendingActivity": pending,
    }
    db.execute(
        "UPDATE student_vocab_srs SET review_activity_bag = %s, updated_at = %s "
        "WHERE student_id = %s AND word_id = %s",
        (Jsonb(updated_bag), datetime.now(timezone.utc).isoformat(), student_id, word_id),
    )
    return str(pending)


def complete_review_activity(db: Any, student_id: str, word_id: str, activity: str) -> bool:
    """Consume a reserved activity once its corresponding response is saved."""
    if activity not in REVIEW_ACTIVITIES:
        raise ValueError(f"Unsupported review activity: {activity}")
    row = db.execute(
        "SELECT review_activity_bag FROM student_vocab_srs "
        "WHERE student_id = %s AND word_id = %s FOR UPDATE",
        (student_id, word_id),
    ).fetchone()
    if row is None:
        return False
    bag = _decode_bag(row.get("review_activity_bag"))
    remaining = bag.get("remaining")
    if bag.get("pendingActivity") != activity or not isinstance(remaining, list) or not remaining or remaining[0] != activity:
        return False
    updated_bag = {
        **bag,
        "remaining": remaining[1:],
        "pendingActivity": None,
    }
    db.execute(
        "UPDATE student_vocab_srs SET review_activity_bag = %s, updated_at = %s "
        "WHERE student_id = %s AND word_id = %s",
        (Jsonb(updated_bag), datetime.now(timezone.utc).isoformat(), student_id, word_id),
    )
    return True


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
        enrolled_state = enrollment_state(started_at, day_seconds=day_seconds)
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
        # Whether the word is STRONG is settled earlier, before the write, in
        # vocab_quiz_attempt_service; this guard keeps a corrective weak-word
        # response from advancing SRS accidentally.
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
