"""Persistence for the SM-2 schedule (``student_vocab_srs``).

Thin DB accessors around the ``SrsState`` value object in analytics/srs.py.
Deliberately separate from analytics/srs.py (pure algorithm) and from
bkt_mastery (BKT mastery is untouched by scheduling).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from analytics.srs import FAST_RESPONSE_MS, SrsState, quality_from_response, review, should_advance


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value[:10])
    return None


def _row_to_state(row: Any) -> SrsState:
    return SrsState(
        reps=int(row["reps"]),
        ease=float(row["ease"]),
        interval_days=int(row["interval_days"]),
        due_on=_to_date(row["due_on"]),
        last_reviewed_on=_to_date(row["last_reviewed_on"]),
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


def _word_id_of(result: dict[str, Any]) -> str | None:
    value = result.get("conceptId") or result.get("word")
    return str(value) if value else None


def apply_srs_updates(db: Any, student_id: str, question_results: Iterable[dict[str, Any]], today: date | None = None) -> int:
    """Advance the SM-2 schedule for each word answered in a review session.

    One graded advance per word per day (``should_advance``); the last answer
    for a word in the batch wins. Returns how many words were rescheduled.
    Scheduling only — the caller still feeds these answers to BKT unchanged.
    """
    today = today or date.today()
    last_by_word: dict[str, dict[str, Any]] = {}
    for result in question_results:
        word_id = _word_id_of(result)
        if word_id is not None and isinstance(result.get("correct"), bool):
            last_by_word[word_id] = result
    if not last_by_word:
        return 0
    states = load_srs_states(db, student_id, list(last_by_word))
    updated = 0
    for word_id, result in last_by_word.items():
        state = states.get(word_id, SrsState())
        if not should_advance(state, today):
            continue
        time_ms = result.get("timeMs")
        if time_ms is None:
            time_ms = result.get("time_ms")
        q = quality_from_response(bool(result["correct"]), time_ms, FAST_RESPONSE_MS)
        upsert_srs_state(db, student_id, word_id, review(state, q, today))
        updated += 1
    return updated
