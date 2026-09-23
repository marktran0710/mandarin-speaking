"""Pure rules for the vocabulary Research Policy Layer (see the BKT x SM-2
research-mode plan, Epic 1).

No database, no FastAPI, no HTTP - inputs in, a decision out. This module
answers exactly one question: given what's known about a student's research
participation, which progression policy applies to them right now?

It does NOT decide how either policy actually grades a round or unlocks
speaking - "production_accuracy" continues to mean whatever
frontend/src/utils/quizTiers.ts and lessonGroups.ts already do today
(untouched by this Epic). "research_coverage" has no behavior yet; it is
introduced here only as a value this module can return, wired to nothing
until Epic 3.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VocabularyProgressionPolicy(str, Enum):
    """Which rule decides when a vocabulary round/story counts as complete."""

    PRODUCTION_ACCURACY = "production_accuracy"
    RESEARCH_COVERAGE = "research_coverage"


# A study only actually changes a participant's experience once it has left
# planning. "draft" and "frozen" are administrative states with no live
# participants yet; "completed" studies no longer apply their policy to new
# activity. "pilot" is included because pilot participants specifically
# exist to exercise the real research flow before the study goes active.
_LIVE_STUDY_STATUSES = frozenset({"pilot", "active"})


@dataclass(frozen=True)
class ResearchContext:
    """Everything the application needs to know about one student's research
    participation for one request. Internal/full shape - see
    api/schemas for the student-safe subset an API response may expose
    (never return this dataclass directly to a student)."""

    active: bool
    study_id: str | None
    study_status: str | None
    policy_version: str | None
    assignment_version: str | None
    practice_budget: int | None
    progression_policy: VocabularyProgressionPolicy


def build_research_context(
    *,
    study_id: str | None,
    study_status: str | None,
    policy_version: str | None,
    assignment_version: str | None,
    practice_budget: int | None,
    participant_active: bool,
) -> ResearchContext:
    """Resolves the effective research context from raw participant/study
    fields. ``participant_active`` is the participant row's own ``active``
    flag (a participant can be individually deactivated - e.g. withdrawn -
    without the whole study changing status).

    A student with no study/participant row at all should be represented by
    calling this with every field None/False, which resolves to an inactive,
    production-policy context - the default for every student today.
    """
    active = bool(participant_active) and study_status in _LIVE_STUDY_STATUSES
    return ResearchContext(
        active=active,
        study_id=study_id,
        study_status=study_status,
        policy_version=policy_version,
        assignment_version=assignment_version,
        practice_budget=practice_budget,
        progression_policy=(
            VocabularyProgressionPolicy.RESEARCH_COVERAGE
            if active
            else VocabularyProgressionPolicy.PRODUCTION_ACCURACY
        ),
    )
