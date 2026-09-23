"""Use-case orchestration for the vocabulary Research Policy Layer.

Coordinates the research repository with the pure policy decisions in
domain/vocabulary/research_policy.py and research_routing.py. Routers must
not query vocab_research_participants/vocab_research_studies directly, and
(Epic 6, Task 6.2) must not keep adding their own `if research...`
response-routing branches - that decision lives in apply_response_routing
below, the one place that decides whether an answer advances the research
retention schedule or production's SM-2 schedule.
"""
from datetime import datetime
from typing import Any, Iterable, Optional

from analytics.bkt_mastery import diagnostic_status
from analytics.srs import DAY_SECONDS
from analytics.srs_store import apply_srs_updates
from application.research_logging import record_policy_event
from application.research_probes import enroll_section_probes
from application.research_retention import apply_retention_review, enroll_section_retention
from domain.vocabulary.research_policy import ResearchContext, build_research_context
from domain.vocabulary.research_routing import ResearchActivityType, activity_type_for_mode, route_research_response
from repositories import vocabulary_research as repo


def get_research_context(db, student_id: str) -> ResearchContext:
    row = repo.find_active_participation(db, student_id)
    if row is None:
        return build_research_context(
            study_id=None,
            study_status=None,
            policy_version=None,
            assignment_version=None,
            practice_budget=None,
            participant_active=False,
        )

    config = row.get("config_json") or {}
    return build_research_context(
        study_id=row["study_id"],
        study_status=row["study_status"],
        policy_version=row["policy_version"],
        assignment_version=row["assignment_version"],
        practice_budget=config.get("practiceBudget"),
        participant_active=bool(row["participant_active"]),
    )


def _event_results(attempt: Any, question_results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a stable per-question source identity before either scheduler
    sees a response batch.

    A whole review round is typically submitted under ONE quiz id, so
    without this each answer in the batch would fall back to the same
    ``quizId``-only idempotency key and every answer after the first would
    silently no-op as a duplicate. Shared by both the production SM-2 path
    and the research retention path (Epic 6, Task 6.2/6.3) - this exact bug
    existed in the research path alone until this Epic unified them onto one
    helper instead of two independently-written ones.
    """
    def value(name: str, default: Any = None) -> Any:
        return attempt.get(name, default) if isinstance(attempt, dict) else getattr(attempt, name, default)

    attempt_id = value("id")
    return [
        {
            **result,
            "sourceResponseId": f"{result.get('quizId') or attempt_id}:{index}",
            "attemptId": attempt_id,
            "quizId": result.get("quizId") or attempt_id,
        }
        for index, result in enumerate(question_results)
    ]


def apply_response_routing(
    db, student_id: str, research_context: ResearchContext, attempt: Any, question_results: Iterable[dict[str, Any]],
    *, now_override: Optional[datetime] = None, day_seconds: float = DAY_SECONDS,
) -> None:
    """Epic 6, Task 6.1/6.2: the one place that decides, per the routing
    table in research_routing.py, whether a review-activity answer advances
    the separate research retention schedule (an active participant) or
    production's SM-2 schedule (everyone else) - moved out of routers/
    vocab_quiz_attempts.py so the router does not keep accumulating its own
    `if research...` branch per Epic. A no-op for any activity type that
    is not a review (core/practice responses reach BKT through
    record_attempt_and_rebuild, called unconditionally by the router - see
    Task 6.4, production's attempt path is unchanged).
    """
    mode = attempt.get("mode") if isinstance(attempt, dict) else attempt.mode
    activity_type = activity_type_for_mode(mode)
    if activity_type != ResearchActivityType.REVIEW:
        return
    routing = route_research_response(activity_type)
    event_results = _event_results(attempt, question_results)
    if research_context.active and research_context.study_id and routing.retention:
        updated = apply_retention_review(
            db, student_id, research_context.study_id, event_results,
            now=now_override, day_seconds=day_seconds,
        )
        record_policy_event(
            db, study_id=research_context.study_id, student_id=student_id, event_type="review_completed",
            payload={"wordsUpdated": updated}, occurred_at=now_override,
        )
    else:
        apply_srs_updates(db, student_id, event_results, now=now_override, day_seconds=day_seconds)


def _completed_core_section_id(db, student_id: str, research_context: ResearchContext, attempt: Any) -> Optional[str]:
    """Shared guard for the two core-completion enrollment hooks (retention
    Task 5.3, probes Task 7.3): resolves the section/story id only when the
    attempt is a just-completed core round for an active participant whose
    diagnostic is actually unlocked. Both callers no-op when this is None.
    """
    def value(name: str, default: Any = None) -> Any:
        return attempt.get(name, default) if isinstance(attempt, dict) else getattr(attempt, name, default)

    if not research_context.active or not research_context.study_id or value("mode") not in ("tier1", "tier2", "tier3"):
        return None
    story_id = value("baseStoryId") or value("storyId")
    if not story_id or not diagnostic_status(db, student_id, story_id=story_id)["unlocked"]:
        return None
    return story_id


def log_core_completion_event(
    db, student_id: str, research_context: ResearchContext, attempt: Any, *, now: Optional[datetime] = None,
) -> None:
    """Epic 8, Task 8.1: assignment_loaded + core_completed - the two
    events that mark the same core-round-completion moment
    enroll_research_retention_for_attempt/enroll_research_probes_for_attempt
    act on. Logged once per attempt via the same shared guard, independent
    of whether those two hooks actually find anything to enroll (a section
    with zero eligible words is still a real, loggable completion)."""
    story_id = _completed_core_section_id(db, student_id, research_context, attempt)
    if story_id is None:
        return
    record_policy_event(
        db, study_id=research_context.study_id, student_id=student_id, event_type="assignment_loaded",
        payload={"sectionId": story_id}, occurred_at=now,
    )
    record_policy_event(
        db, study_id=research_context.study_id, student_id=student_id, event_type="core_completed",
        payload={"sectionId": story_id}, occurred_at=now,
    )


def enroll_research_retention_for_attempt(
    db, student_id: str, research_context: ResearchContext, attempt: Any, *, now: Optional[datetime] = None, day_seconds: float = DAY_SECONDS,
) -> None:
    """Epic 5/6: once an active research participant's core rounds for a
    section are complete, every word assigned to them in that section
    enters the retention pipeline - regardless of BKT status, unlike
    production's enroll_strong_words. Lives here (not the router) per Task
    6.2 - the router should not accumulate its own research branches.
    """
    story_id = _completed_core_section_id(db, student_id, research_context, attempt)
    if story_id is None:
        return
    enroll_section_retention(
        db, student_id, research_context.study_id, story_id,
        now=now, day_seconds=day_seconds,
    )


def enroll_research_probes_for_attempt(
    db, student_id: str, research_context: ResearchContext, attempt: Any, *, now: Optional[datetime] = None,
) -> None:
    """Epic 7, Task 7.3: sibling of enroll_research_retention_for_attempt -
    the same core-completion moment also schedules that section's disjoint
    probe pools. Same no-op conditions, same reason for living here."""
    story_id = _completed_core_section_id(db, student_id, research_context, attempt)
    if story_id is None:
        return
    enroll_section_probes(db, student_id, research_context.study_id, story_id, now=now)
