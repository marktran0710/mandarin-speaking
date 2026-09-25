"""Read-only balance/integrity auditing for a completed assignment run
(Epic 2, Task 2.5). Never writes anything - scripts/audit_research_assignments.py
is the CLI wrapper around audit_assignments_for_study below.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from repositories import research as repo


@dataclass
class AssignmentAuditReport:
    study_id: str
    total_assignments: int
    condition_counts: dict[str, int]
    lesson_balance: dict[str, dict[str, int]]
    section_balance: dict[str, dict[str, int]]
    class_balance: dict[str, dict[str, int]]
    word_condition_spread: dict[str, dict[str, int]]
    participants_with_missing_words: dict[str, tuple[int, int]]  # student_id -> (have, expected)
    duplicate_student_word_pairs: list[tuple[str, str]]
    related_set_violations: list[tuple[str, str]]  # (student_id, related_set_id)
    unyoked_count: int

    @property
    def is_clean(self) -> bool:
        return not (
            self.participants_with_missing_words
            or self.duplicate_student_word_pairs
            or self.related_set_violations
            or self.unyoked_count
        )


def audit_assignments_for_study(db, study_id: str) -> AssignmentAuditReport:
    assignments = repo.find_assignments_for_study(db, study_id)
    participants = repo.find_participants_for_study(db, study_id)

    condition_counts: Counter[str] = Counter()
    lesson_balance: dict[str, Counter[str]] = defaultdict(Counter)
    section_balance: dict[str, Counter[str]] = defaultdict(Counter)
    class_balance: dict[str, Counter[str]] = defaultdict(Counter)
    word_condition_spread: dict[str, Counter[str]] = defaultdict(Counter)
    seen_pairs: Counter[tuple[str, str]] = Counter()
    words_per_student: dict[str, set[str]] = defaultdict(set)
    related_words_per_student: dict[tuple[str, str], set[str]] = defaultdict(set)
    related_conditions_per_student: dict[tuple[str, str], set[str]] = defaultdict(set)
    unyoked_count = 0

    class_by_student = {p["student_id"]: p["class_id"] for p in participants}

    for row in assignments:
        condition = _condition_from_policies(row["bkt_policy"], row["retention_policy"])
        condition_counts[condition] += 1
        if row["lesson_id"]:
            lesson_balance[row["lesson_id"]][condition] += 1
        if row["section_id"]:
            section_balance[row["section_id"]][condition] += 1
        class_id = class_by_student.get(row["student_id"])
        if class_id:
            class_balance[class_id][condition] += 1
        word_condition_spread[row["word_id"]][condition] += 1

        pair = (row["student_id"], row["word_id"])
        seen_pairs[pair] += 1
        words_per_student[row["student_id"]].add(row["word_id"])

        if row["related_set_id"]:
            key = (row["student_id"], row["related_set_id"])
            related_words_per_student[key].add(row["word_id"])
            related_conditions_per_student[key].add(condition)

        if row["retention_policy"] == "yoked" and not row["yoke_source_word_id"]:
            unyoked_count += 1

    expected_word_count = len({row["word_id"] for row in assignments})
    missing = {
        student_id: (len(words), expected_word_count)
        for student_id, words in words_per_student.items()
        if len(words) < expected_word_count
    }
    # Participants with zero assignments at all (e.g. added after the run)
    # never appear in `assignments`, so they wouldn't show up above - catch
    # them explicitly.
    for participant in participants:
        student_id = participant["student_id"]
        if student_id not in words_per_student and expected_word_count > 0:
            missing[student_id] = (0, expected_word_count)

    duplicates = [pair for pair, count in seen_pairs.items() if count > 1]
    violations = [
        key for key, conditions in related_conditions_per_student.items() if len(conditions) > 1
    ]

    return AssignmentAuditReport(
        study_id=study_id,
        total_assignments=len(assignments),
        condition_counts=dict(condition_counts),
        lesson_balance={k: dict(v) for k, v in lesson_balance.items()},
        section_balance={k: dict(v) for k, v in section_balance.items()},
        class_balance={k: dict(v) for k, v in class_balance.items()},
        word_condition_spread={k: dict(v) for k, v in word_condition_spread.items()},
        participants_with_missing_words=missing,
        duplicate_student_word_pairs=duplicates,
        related_set_violations=violations,
        unyoked_count=unyoked_count,
    )


def _condition_from_policies(bkt_policy: str, retention_policy: str) -> str:
    if bkt_policy == "mastery_blind" and retention_policy == "yoked":
        return "C"
    if bkt_policy == "bkt_personalized" and retention_policy == "yoked":
        return "B"
    if bkt_policy == "mastery_blind" and retention_policy == "adaptive_sm2":
        return "S"
    return "BS"
