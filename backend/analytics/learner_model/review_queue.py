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

from datetime import datetime, timezone
from typing import Any

from analytics.learner_model.srs import SrsState, is_due
from analytics.learner_model.srs_store import load_srs_states


def combine_review_queue(
    weak_words: list[dict[str, Any]],
    mastery: list[dict[str, Any]],
    srs_states: dict[str, SrsState],
    now: datetime,
) -> list[dict[str, Any]]:
    """Union the BKT weak list with SM-2 due words, tagged and ordered.

    ``weak_words`` is the selected list from get_priority_review_words; ``mastery``
    is that call's per-word snapshot (used to hydrate due words not already weak).
    Inputs are not mutated.
    """
    mastery_by_id = {m["wordId"]: m for m in mastery}
    due_extra: list[tuple[datetime, dict[str, Any]]] = []
    for word_id, state in srs_states.items():
        if not is_due(state, now):
            continue
        row = mastery_by_id.get(word_id)
        # Only surface real, observed words; a due entry with no mastery record
        # (or zero observations) is stale scheduling, not a review candidate.
        if row is None or int(row.get("observationCount", 0)) <= 0:
            continue
        # Enrollment is the BKT/diagnostic gate. After enrollment, SM-2 owns
        # due timing even if a later maintenance answer lowers one BKT
        # component. A lapse must not silently unenroll the word.
        item = {**row, "reviewReason": "due", "dueOn": state.due_on.isoformat() if state.due_on else None}
        due_extra.append((state.due_on or now, item))

    # Earliest due time first (most overdue), stable by wordId.
    due_extra.sort(key=lambda pair: (pair[0], pair[1]["wordId"]))
    ordered_due = [item for _, item in due_extra]
    due_ids = {item["wordId"] for item in ordered_due}
    # An enrolled word that is due gets one maintenance question. Do not
    # duplicate it in the personalized part of the same queue.
    tagged_weak = [
        {**word, "reviewReason": "weak"}
        for word in weak_words
        if word["wordId"] not in due_ids
    ]
    return ordered_due + tagged_weak


def build_review_queue(
    db: Any,
    student_id: str,
    options: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read the combined review queue for a student.

    Thin glue: BKT's existing weak-word priority (untouched) unioned with the
    SM-2 due words. Returns the priority-review payload plus a ``queue`` field
    (the tagged, ordered union). Never changes BKT state.
    """
    from analytics.learner_model.bkt.mastery import get_priority_review_words

    review = get_priority_review_words(db, student_id, options)
    now = now or datetime.now(timezone.utc)
    mastery = review.get("mastery", [])
    states = load_srs_states(db, student_id, [row["wordId"] for row in mastery])
    # The mastery projection may have been built with the real clock while a
    # development caller asks for a simulated review date. Keep the nested
    # scheduling state aligned with the queue's clock.
    for row in mastery:
        state = states.get(row["wordId"])
        if state is not None and row.get("vocabularyState"):
            row["vocabularyState"]["scheduling"]["status"] = "DUE_FOR_REVIEW" if is_due(state, now) else "SCHEDULED"
    queue = combine_review_queue(review.get("words", []), mastery, states, now)
    return {**review, "queue": queue}


def build_all_learned_review_queue(
    db: Any,
    student_id: str,
    options: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Combine due and weak words from lessons with completed diagnostics.

    Diagnostic completion remains scoped to each lesson. BKT states are
    replayed by canonical word across the learner's whole history, so a
    repeated word is not treated as a new skill in each lesson.
    """
    from analytics.learner_model.bkt.mastery import (
        bottom_k_review_key,
        get_priority_review_words,
        serving_bkt_config,
    )
    from analytics.learner_model.bkt.core import BKT_CONFIG

    options = options or {}
    now = now or datetime.now(timezone.utc)
    active_config = serving_bkt_config(db, BKT_CONFIG)
    review_count = max(1, min(int(options.get("reviewCount", active_config.review_count)), 50))
    stories = db.execute(
        "SELECT id, vocabulary_version FROM custom_stories WHERE published = TRUE ORDER BY id"
    ).fetchall()
    learned_stories: list[dict[str, Any]] = []
    mastery_by_id: dict[str, dict[str, Any]] = {}
    weak_by_id: dict[str, dict[str, Any]] = {}

    for story in stories:
        story_id = str(story["id"])
        review = get_priority_review_words(
            db,
            student_id,
            {"storyId": story_id, "includeAllWeak": True, "reviewCount": review_count},
        )
        if not review.get("unlocked"):
            continue
        learned_stories.append({"storyId": story_id, "vocabularyVersion": story.get("vocabulary_version")})
        for row in review.get("mastery", []):
            word_id = row["wordId"]
            source_ids = [*mastery_by_id.get(word_id, {}).get("sourceStoryIds", []), story_id]
            source_versions = {
                **mastery_by_id.get(word_id, {}).get("sourceStoryVersions", {}),
                story_id: story.get("vocabulary_version"),
            }
            if word_id not in mastery_by_id:
                mastery_by_id[word_id] = {
                    **row,
                    "sourceStoryId": story_id,
                    "sourceStoryIds": source_ids,
                    "sourceStoryVersions": source_versions,
                    "vocabularyVersion": story.get("vocabulary_version"),
                }
            else:
                mastery_by_id[word_id]["sourceStoryIds"] = list(dict.fromkeys(source_ids))
                mastery_by_id[word_id]["sourceStoryVersions"] = source_versions
        for row in review.get("words", []):
            existing_weak = weak_by_id.get(row["wordId"])
            if existing_weak is None:
                weak_by_id[row["wordId"]] = {
                    **row,
                    "sourceStoryId": story_id,
                    "sourceStoryIds": [story_id],
                    "vocabularyVersion": story.get("vocabulary_version"),
                }
            else:
                existing_weak["sourceStoryIds"] = list(dict.fromkeys([*existing_weak["sourceStoryIds"], story_id]))

    mastery = sorted(mastery_by_id.values(), key=bottom_k_review_key)
    ordered_weak = sorted(weak_by_id.values(), key=bottom_k_review_key)
    weak = ordered_weak if options.get("includeAllWeak") else ordered_weak[:review_count]
    for rank, row in enumerate(weak, start=1):
        row["reviewRank"] = rank
    for row in mastery:
        if row["wordId"] not in weak_by_id:
            row["reviewRank"] = None

    states = load_srs_states(db, student_id, [row["wordId"] for row in mastery])
    for row in mastery:
        state = states.get(row["wordId"])
        if state is not None and row.get("vocabularyState"):
            row["vocabularyState"]["scheduling"]["status"] = "DUE_FOR_REVIEW" if is_due(state, now) else "SCHEDULED"
    queue = combine_review_queue(weak, mastery, states, now)
    return {
        "scope": "all_learned",
        "unlocked": bool(learned_stories),
        "requiredDiagnosticQuizzes": 3,
        "completedDiagnosticQuizzes": 3 if learned_stories else 0,
        "diagnosticComplete": bool(learned_stories),
        "learnedStories": learned_stories,
        "learnedStoryCount": len(learned_stories),
        "reviewCount": review_count,
        "words": weak,
        "mastery": mastery,
        "queue": queue,
    }
