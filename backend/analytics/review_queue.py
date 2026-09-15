"""Compose the review queue: weak words (BKT) ∪ due words (SM-2).

Pure combination — no DB, no model math. Weak words come from BKT's existing
``get_priority_review_words``; due words come from the SM-2 schedule. Each item
is tagged with why it surfaced (``reviewReason``: "weak" vs "due") so the UI can
show genuinely-weak words apart from mastered-but-due maintenance reviews. A
mastered word that comes due is therefore never mislabelled "weak".

Order: most-overdue due words first (spacing is time-sensitive), then the weak
list in its existing BKT priority order.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from analytics.srs import SrsState, is_due
from analytics.srs_store import load_srs_states


def combine_review_queue(
    weak_words: list[dict[str, Any]],
    mastery: list[dict[str, Any]],
    srs_states: dict[str, SrsState],
    today: date,
) -> list[dict[str, Any]]:
    """Union the BKT weak list with SM-2 due words, tagged and ordered.

    ``weak_words`` is the selected list from get_priority_review_words; ``mastery``
    is that call's per-word snapshot (used to hydrate due words not already weak).
    Inputs are not mutated.
    """
    weak_ids = {w["wordId"] for w in weak_words}
    tagged_weak = [{**w, "reviewReason": "weak"} for w in weak_words]

    mastery_by_id = {m["wordId"]: m for m in mastery}
    due_extra: list[tuple[date, dict[str, Any]]] = []
    for word_id, state in srs_states.items():
        if word_id in weak_ids or not is_due(state, today):
            continue
        row = mastery_by_id.get(word_id)
        # Only surface real, observed words; a due entry with no mastery record
        # (or zero observations) is stale scheduling, not a review candidate.
        if row is None or int(row.get("observationCount", 0)) <= 0:
            continue
        item = {**row, "reviewReason": "due", "dueOn": state.due_on.isoformat() if state.due_on else None}
        due_extra.append((state.due_on or today, item))

    # Earliest due date first (most overdue), stable by wordId.
    due_extra.sort(key=lambda pair: (pair[0], pair[1]["wordId"]))
    ordered_due = [item for _, item in due_extra]
    return ordered_due + tagged_weak


def build_review_queue(db: Any, student_id: str, options: dict[str, Any] | None = None, today: date | None = None) -> dict[str, Any]:
    """Read the combined review queue for a student.

    Thin glue: BKT's existing weak-word priority (untouched) unioned with the
    SM-2 due words. Returns the priority-review payload plus a ``queue`` field
    (the tagged, ordered union). Never changes BKT state.
    """
    from analytics.bkt_mastery import get_priority_review_words

    review = get_priority_review_words(db, student_id, options)
    today = today or date.today()
    mastery = review.get("mastery", [])
    states = load_srs_states(db, student_id, [row["wordId"] for row in mastery])
    queue = combine_review_queue(review.get("words", []), mastery, states, today)
    return {**review, "queue": queue}
