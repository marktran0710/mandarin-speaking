"""Use-case orchestration for the offline research item-assignment run
(Epic 2). This is the one place scripts/build_research_assignments.py and
its tests should call - it owns the freeze/idempotency guards and wires the
repository to the pure counterbalancing math in
domain/vocabulary/research_assignment.py.

Deliberately NOT reachable from any live HTTP route: conditions must never
be assigned dynamically during a quiz (see Epic 2's plan). Nothing imports
this module from routers/.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from domain.vocabulary.research_assignment import (
    AssignmentCondition,
    CONDITION_POLICIES,
    assign_conditions_for_student,
    group_related_sets,
    sequence_for_roster_position,
    yoke_pairs_for_student,
)
from repositories import vocabulary_research as repo

DEFAULT_RELATED_VOCAB_CSV = Path(__file__).resolve().parents[1] / "research_related_vocab.csv"


class StudyFrozenError(Exception):
    """The study is frozen - assignments are permanent and cannot be regenerated."""


class AssignmentsAlreadyExistError(Exception):
    """This study already has assignments. Pass force=True to regenerate
    (only allowed while the study is not frozen)."""


@dataclass(frozen=True)
class AssignmentRunResult:
    study_id: str
    assignment_version: str
    participants_assigned: int
    words_per_participant: int
    condition_counts: dict[str, int]
    unyoked_word_count: int


def load_related_set_map(csv_path: Optional[Path] = None) -> dict[str, str]:
    """word_id -> related_set_id, from research_related_vocab.csv. A missing
    file just means no related sets are configured yet - not an error."""
    path = csv_path or DEFAULT_RELATED_VOCAB_CSV
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["word_id"]: row["related_set_id"] for row in csv.DictReader(handle)}


def load_eligible_words(db, *, lesson_min: int, lesson_max: int) -> list[tuple[str, Optional[str], Optional[str]]]:
    """Unique (word_id, lesson_id, section_id) triples, in first-seen
    curriculum order, across every published story in [lesson_min, lesson_max].
    lesson_id is the story's lesson_number as text; section_id is the story id.
    A word already seen in an earlier story keeps that story's lesson/section
    (a word doesn't get reassigned to a later story it also happens to appear in).
    """
    rows = repo.find_published_vocab_by_lesson_range(db, lesson_min, lesson_max)
    seen: dict[str, tuple[str, Optional[str], Optional[str]]] = {}
    for row in rows:
        vocab_assessment = row.get("vocab_assessment") or []
        lesson_id = str(row["lesson_number"]) if row.get("lesson_number") is not None else None
        section_id = row["id"]
        for item in vocab_assessment:
            word_id = item.get("wordId") or item.get("word_id")
            if not word_id or word_id in seen:
                continue
            seen[word_id] = (word_id, lesson_id, section_id)
    return list(seen.values())


def build_assignments_for_study(
    db,
    study_id: str,
    *,
    assignment_version: str,
    created_at: str,
    lesson_min: int = 5,
    lesson_max: int = 8,
    related_vocab_csv_path: Optional[Path] = None,
    force: bool = False,
) -> AssignmentRunResult:
    study = repo.find_study(db, study_id)
    if study is None:
        raise ValueError(f"No such study: {study_id!r}")
    if study["status"] == "frozen":
        raise StudyFrozenError(f"Study {study_id!r} is frozen; assignments cannot be regenerated.")

    existing_count = repo.count_assignments(db, study_id)
    if existing_count > 0:
        if not force:
            raise AssignmentsAlreadyExistError(
                f"Study {study_id!r} already has {existing_count} assignments. "
                "Pass force=True to regenerate (blocked once the study is frozen)."
            )
        repo.delete_assignments_for_study(db, study_id)

    eligible_words = load_eligible_words(db, lesson_min=lesson_min, lesson_max=lesson_max)
    word_order = [word_id for word_id, _lesson, _section in eligible_words]
    word_context = {word_id: (lesson_id, section_id) for word_id, lesson_id, section_id in eligible_words}
    related_set_by_word = load_related_set_map(related_vocab_csv_path)
    units = group_related_sets(word_order, related_set_by_word)

    participants = repo.find_participants_for_study(db, study_id)
    condition_counts: dict[str, int] = {c.value: 0 for c in AssignmentCondition}
    unyoked_word_count = 0

    for position, participant in enumerate(participants):
        student_id = participant["student_id"]
        sequence_id = participant["sequence_id"] or sequence_for_roster_position(position)
        if participant["sequence_id"] is None:
            repo.set_participant_sequence(db, study_id, student_id, sequence_id)

        assignments = assign_conditions_for_student(sequence_id, units)
        yoke_pairs = yoke_pairs_for_student(assignments)

        for assignment in assignments:
            bkt_policy, retention_policy = CONDITION_POLICIES[assignment.condition]
            lesson_id, section_id = word_context.get(assignment.word_id, (None, None))
            yoke_source = yoke_pairs.get(assignment.word_id)
            if retention_policy.value == "yoked" and yoke_source is None:
                unyoked_word_count += 1
            repo.insert_assignment(
                db,
                study_id=study_id,
                student_id=student_id,
                word_id=assignment.word_id,
                lesson_id=lesson_id,
                section_id=section_id,
                bkt_policy=bkt_policy.value,
                retention_policy=retention_policy.value,
                sequence_id=sequence_id,
                related_set_id=assignment.related_set_id,
                yoke_source_word_id=yoke_source,
                assignment_version=assignment_version,
                created_at=created_at,
            )
            condition_counts[assignment.condition.value] += 1

    return AssignmentRunResult(
        study_id=study_id,
        assignment_version=assignment_version,
        participants_assigned=len(participants),
        words_per_participant=len(word_order),
        condition_counts=condition_counts,
        unyoked_word_count=unyoked_word_count,
    )
