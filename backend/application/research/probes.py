"""Use-case orchestration for the Epic 7 independent outcome bank + probes.

Mirrors application/research_retention.py's shape: enrollment on core
completion, plus a student-safe read + a server-graded write. A probe is
never submitted through the quiz-attempt API (Task 7.5) and its response
never carries correctness back to the student (Task 7.6) - unlike core/
practice/review, this is a read-only measurement, not a treatment.
"""
from __future__ import annotations

from datetime import datetime, timezone

from application.research.logging import condition_label, record_policy_event
from domain.research.probes import PROBE_TYPES, due_at_for_probe_type, partition_probe_pool
from repositories import research as repo


class ResearchProbeUnavailableError(Exception):
    """The student is not an active research participant right now."""


class ResearchProbeAssignmentNotFoundError(Exception):
    """No such probe assignment exists for this student."""


def enroll_section_probes(db, student_id: str, study_id: str, section_id: str, *, now: datetime | None = None) -> int:
    """Task 7.3: once a research participant's core rounds for one section
    complete, schedule a probe for each of that section's assigned words
    that already has an outcome-bank item - split into disjoint 7-day/
    21-day/final-retention pools per student (Task 7.7). A word with no
    assessment-bank item yet is skipped; content authoring is separate from
    this scheduling step. Idempotent: a word already scheduled is left alone.
    """
    now = now or datetime.now(timezone.utc)
    assignments = [row for row in repo.find_assignments_for_student(db, study_id, student_id) if row["section_id"] == section_id]
    if not assignments:
        return 0
    word_ids = [row["word_id"] for row in assignments]
    condition_by_word = {row["word_id"]: condition_label(row["bkt_policy"], row["retention_policy"]) for row in assignments}
    already_scheduled = repo.find_probe_assignments_for_student(db, study_id, student_id, word_ids)
    pending_word_ids = [word_id for word_id in word_ids if word_id not in already_scheduled]
    if not pending_word_ids:
        return 0

    pool = partition_probe_pool(student_id, pending_word_ids)
    scheduled = 0
    for probe_type in PROBE_TYPES:
        pool_word_ids = [word_id for word_id, assigned_type in pool.items() if assigned_type == probe_type]
        if not pool_word_ids:
            continue
        items = repo.find_assessment_items_for_words(db, study_id, pool_word_ids, probe_type)
        due_at = due_at_for_probe_type(probe_type, now)
        for word_id in pool_word_ids:
            item = items.get(word_id)
            if item is None:
                continue
            repo.insert_probe_assignment(
                db, study_id=study_id, student_id=student_id, word_id=word_id,
                assessment_item_id=item["id"], probe_type=probe_type,
                due_at=due_at, assigned_at=now, created_at=now.isoformat(),
            )
            record_policy_event(
                db, study_id=study_id, student_id=student_id, event_type="probe_assigned", word_id=word_id,
                payload={"condition": condition_by_word.get(word_id)}, occurred_at=now,
            )
            scheduled += 1
    return scheduled


def build_due_probes(db, student_id: str) -> dict:
    """Task 7.5: which of this student's probes are due and unanswered
    right now. Student-safe shape only: word, question content, and choices
    - never probe_type, study_id, or the correct answer (Task 7.6)."""
    from application.research.response_routing import get_research_context

    context = get_research_context(db, student_id)
    if not context.active or not context.study_id:
        raise ResearchProbeUnavailableError("Student is not an active research participant.")
    now = datetime.now(timezone.utc)
    rows = repo.find_due_probe_assignments(db, context.study_id, student_id, now)
    questions = []
    for row in rows:
        item = repo.find_assessment_item(db, row["assessment_item_id"])
        if item is None:
            continue
        questions.append({
            "assignmentId": row["id"],
            "wordId": row["word_id"],
            "questionType": item["question_type"],
            "prompt": item["prompt"],
            "choices": item["choices"],
        })
    return {"questions": questions}


def submit_probe_response(
    db, student_id: str, assignment_id: int, response_value: str, *, source_response_id: str, now: datetime | None = None,
) -> dict:
    """Task 7.6: server grades in isolation; the caller only ever learns
    that the response was accepted, never whether it was correct - showing
    feedback here would itself be an intervention on the outcome measure."""
    now = now or datetime.now(timezone.utc)
    assignment = repo.find_probe_assignment_by_id(db, assignment_id, student_id)
    if assignment is None:
        raise ResearchProbeAssignmentNotFoundError("No such probe assignment for this student.")
    if repo.find_probe_response(db, assignment_id) is not None:
        return {"accepted": True}
    item = repo.find_assessment_item(db, assignment["assessment_item_id"])
    correct = item is not None and response_value == item["correct_answer"]
    repo.insert_probe_response(
        db, probe_assignment_id=assignment_id, study_id=assignment["study_id"], student_id=student_id,
        word_id=assignment["word_id"], assessment_item_id=assignment["assessment_item_id"],
        response_value=response_value, correct=correct, source_response_id=source_response_id,
        responded_at=now, created_at=now.isoformat(),
    )
    # The log may hold `correct` (Task 8.2's outcome data, later exported by
    # Epic 9) even though the HTTP response to the student never does.
    record_policy_event(
        db, study_id=assignment["study_id"], student_id=student_id, event_type="probe_completed",
        word_id=assignment["word_id"], payload={"probeType": assignment["probe_type"], "correct": correct}, occurred_at=now,
    )
    return {"accepted": True}
