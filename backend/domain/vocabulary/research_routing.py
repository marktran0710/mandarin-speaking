"""Pure activity-routing policy for the Research Policy Layer (BKT x SM-2
research-mode plan, Epic 6).

Formalizes, as one documented table, which state systems a research
response is allowed to touch depending on its activity type. This is the
contract the write-time evidence scoping built across Epics 3-5 must stay
consistent with:

- Core/Practice responses feed treatment BKT (analytics/bkt_mastery.py's
  ``get_treatment_vocabulary_mastery``, scoped by quiz_mode) and production's
  shadow BKT (``rebuild_student_vocabulary_mastery``, unconditional), never
  retention.
- Review responses feed retention (``application/research_retention.py``)
  and, for a non-participant, production's shadow BKT projection - never
  treatment BKT (excluded from ``_treatment_ordered_responses``).
- Probe/Posttest (Epic 7) touch none of the three - they use their own,
  separate assessment bank and response tables, never the vocab_quiz_*
  pipeline these activity types route.

``application/vocabulary_research.py``'s ``apply_response_routing`` is the
one place that consults this live, for the single per-response decision
that genuinely varies response-by-response: whether an answer advances the
research retention schedule. The BKT replay queries are a historical
ledger scan, not a per-event dispatch, so they encode the same contract as
SQL scoping rather than calling this function row by row - a purely
mechanical difference, not a policy one.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ResearchActivityType(str, Enum):
    CORE = "diagnostic"
    PRACTICE = "personalized_practice"
    REVIEW = "scheduled_maintenance"
    PROBE = "probe"
    POSTTEST = "posttest"


@dataclass(frozen=True)
class ResponseRouting:
    treatment_bkt: bool
    # None means "optional" (the plan's own term) - a deliberate design
    # choice left open, not a third boolean state pretending to be binary.
    shadow_bkt: Optional[bool]
    retention: bool


_ROUTING_TABLE: dict[ResearchActivityType, ResponseRouting] = {
    ResearchActivityType.CORE: ResponseRouting(treatment_bkt=True, shadow_bkt=True, retention=False),
    ResearchActivityType.PRACTICE: ResponseRouting(treatment_bkt=True, shadow_bkt=True, retention=False),
    ResearchActivityType.REVIEW: ResponseRouting(treatment_bkt=False, shadow_bkt=None, retention=True),
    ResearchActivityType.PROBE: ResponseRouting(treatment_bkt=False, shadow_bkt=False, retention=False),
    ResearchActivityType.POSTTEST: ResponseRouting(treatment_bkt=False, shadow_bkt=False, retention=False),
}


def route_research_response(activity_type: "ResearchActivityType | str") -> ResponseRouting:
    return _ROUTING_TABLE[ResearchActivityType(activity_type)]


# The existing quiz `mode` values map 1:1 onto activity types (see
# analytics/bkt_mastery.py's response_rows_for_attempt, which derives the
# same activity_type string independently per-response - this table is the
# per-ATTEMPT equivalent, since one attempt is always one mode).
_MODE_TO_ACTIVITY_TYPE: dict[str, ResearchActivityType] = {
    "tier1": ResearchActivityType.CORE,
    "tier2": ResearchActivityType.CORE,
    "tier3": ResearchActivityType.CORE,
    "weak_words": ResearchActivityType.PRACTICE,
    "maintenance_review": ResearchActivityType.REVIEW,
}


def activity_type_for_mode(mode: Optional[str]) -> Optional[ResearchActivityType]:
    """None for a mode with no research-routing meaning (challenge, free) -
    Epic 7's probe/posttest flows get their own dedicated endpoints rather
    than overloading this quiz `mode` field, so they are never reached
    through this lookup either."""
    return _MODE_TO_ACTIVITY_TYPE.get(mode or "")
