"""Pure retention-scheduling rules for the Epic 5 adaptive SM-2 + yoked
review feature.

No database, no I/O. Reuses ``analytics/srs.py``'s SM-2 math unchanged (the
plan is explicit: "reuse existing SM-2 math" / "keep analytics/srs.py
mathematically unchanged") - this module only adds the ONE new rule
production's scheduler has no concept of: a yoked word's schedule mirrors
its paired adaptive word's schedule instead of being earned by its own
graded answers (Task 5.5/5.6).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from analytics.learner_model.srs import INITIAL_EASE, FIRST_INTERVAL_DAYS, SrsState


def initial_enrollment_state(now: datetime, day_seconds: float) -> SrsState:
    """The first schedule a newly-enrolled word gets (Task 5.3) - identical
    for an adaptive word and a yoked word at the moment of enrollment. They
    only diverge later, once the adaptive word earns its first real review
    and the yoked word mirrors that change (see mirror_yoked_state)."""
    return SrsState(
        reps=1,
        ease=INITIAL_EASE,
        interval_days=FIRST_INTERVAL_DAYS,
        due_on=now + timedelta(seconds=day_seconds * FIRST_INTERVAL_DAYS),
        last_reviewed_on=now,
    )


def mirror_yoked_state(source_state: SrsState) -> SrsState:
    """Task 5.6: "adaptive source schedule changes -> yoked item receives
    matched due schedule." The yoked word's schedule becomes an exact copy
    of its source's current schedule - never a function of the yoked word's
    own correctness, which this function does not even take as an input."""
    return SrsState(
        reps=source_state.reps,
        ease=source_state.ease,
        interval_days=source_state.interval_days,
        due_on=source_state.due_on,
        last_reviewed_on=source_state.last_reviewed_on,
    )
