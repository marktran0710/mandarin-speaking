"""Epic 8, Task 8.2/8.3: aggregates vocab_research_policy_events (plus, for
the one metric the log alone can't answer, the retention-events table
directly) into the numbers a researcher needs to check protocol adherence.
Read-only - never writes anything, unlike research_logging.py.
"""
from __future__ import annotations

from application.research.assignment_audit import audit_assignments_for_study
from repositories import research as repo


class ResearchStudyNotFoundError(Exception):
    """No study exists with this id."""


def build_fidelity_summary(db, study_id: str) -> dict:
    """Task 8.2. Practice/retention "expected" counts come from the study's
    own condition-crossed roster (every C/B/S/BS word that could have
    generated an event), not a guessed constant - see the docstring on each
    field below for exactly what it means.
    """
    event_counts = repo.count_policy_events_by_type(db, study_id)
    practice_by_condition = repo.count_word_events_by_condition(db, study_id, "practice_item_selected")
    retention_enrolled_by_condition = repo.count_word_events_by_condition(db, study_id, "retention_enrolled")
    review_delivered = event_counts.get("review_scheduled", 0) + event_counts.get("review_yoked", 0)
    probe_assigned = event_counts.get("probe_assigned", 0)
    probe_completed = event_counts.get("probe_completed", 0)

    bkt_on = practice_by_condition.get("B", 0) + practice_by_condition.get("BS", 0)
    bkt_off = practice_by_condition.get("C", 0) + practice_by_condition.get("S", 0)

    return {
        "coreCompletedCount": event_counts.get("core_completed", 0),
        "practice": {
            # Task 8.2's "BKT ON/OFF exposure difference": how many
            # practice_item_selected events each side of the BKT factor
            # actually received - equal is the whole point of Task 4.5's
            # equal-budget design, so a large gap here is itself a finding.
            "itemsSelectedByCondition": practice_by_condition,
            "bktOnCount": bkt_on,
            "bktOffCount": bkt_off,
            "sessionsCreated": event_counts.get("practice_session_created", 0),
        },
        "retention": {
            "enrolledByCondition": retention_enrolled_by_condition,
            "reviewsDelivered": review_delivered,
            "averageDelayDays": repo.average_review_delay_days(db, study_id),
        },
        "probes": {
            "assigned": probe_assigned,
            "completed": probe_completed,
            "completionRate": (probe_completed / probe_assigned) if probe_assigned else None,
        },
        # Task 8.2's "condition violations": a straight count of logged
        # policy_violation events. Always 0 in this Epic - no detector is
        # wired up yet (see application/research_logging.py's docstring);
        # this field exists so the admin summary shape is stable once one
        # is, rather than needing a schema change later.
        "policyViolations": event_counts.get("policy_violation", 0),
    }


def build_admin_summary(db, study_id: str) -> dict:
    """Task 8.3/8.4: the one call the research admin page needs - study
    status, participant counts, assignment balance (Epic 2's existing
    audit, reused rather than recomputed), and fidelity."""
    study = repo.find_study(db, study_id)
    if study is None:
        raise ResearchStudyNotFoundError(f"No such study: {study_id!r}")
    active_participants = len(repo.find_participants_for_study(db, study_id))
    total_participants = repo.count_all_participants_for_study(db, study_id)
    audit = audit_assignments_for_study(db, study_id)
    fidelity = build_fidelity_summary(db, study_id)
    return {
        "studyId": study_id,
        "name": study["name"],
        "status": study["status"],
        "participants": {"active": active_participants, "total": total_participants},
        "assignmentBalance": audit.condition_counts,
        "totalAssignments": audit.total_assignments,
        "fidelity": fidelity,
    }
