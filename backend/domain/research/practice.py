"""Pure practice-session selection math for the equal-budget BKT practice
feature (BKT x SM-2 research-mode plan, Epic 4).

No database, no I/O. Everything a caller needs to decide "which words, and
how many per condition" is a deterministic function of inputs here, so the
selection is auditable and reproducible from a logged input snapshot.

The BKT-on and mastery-blind selectors are deliberately separate functions
with different, narrower input shapes (word_id + p_learned vs. word_id +
exposure_count) rather than one function with an optional p_learned field.
A mastery-blind condition must not merely ignore p(learned) - it must be
structurally impossible for it to reach this code at all. The caller
(application/research_practice_session.py) enforces this by simply never
replaying/fetching treatment BKT state for mastery-blind words.
"""
from __future__ import annotations

from domain.research.assignment import AssignmentCondition


# Fixed, deterministic order used only to decide which conditions absorb the
# practice budget's integer-division remainder. Reuses the same condition
# ordering research_assignment.py already establishes for counterbalancing,
# rather than inventing a second convention.
CONDITION_ORDER: tuple[AssignmentCondition, ...] = (
    AssignmentCondition.CONTROL,
    AssignmentCondition.BKT,
    AssignmentCondition.SRS,
    AssignmentCondition.BKT_SRS,
)


def allocate_slots(budget: int, conditions_present: list[AssignmentCondition]) -> dict[AssignmentCondition, int]:
    """Split a practice budget evenly across the conditions a student
    actually has assigned words for. E.g. budget=8 across all four
    conditions gives 2 slots each (the plan's own worked example). A
    condition absent from this student's assignment (should not happen once
    a study is frozen, but a defensive no-op if it does) gets no slots
    rather than the caller guessing a substitute.

    Any remainder from integer division goes to the earliest conditions in
    CONDITION_ORDER, so the split is deterministic and reproducible from the
    same inputs rather than depending on dict/set iteration order.
    """
    ordered_present = [condition for condition in CONDITION_ORDER if condition in conditions_present]
    if not ordered_present or budget <= 0:
        return {condition: 0 for condition in ordered_present}
    base, remainder = divmod(budget, len(ordered_present))
    return {
        condition: base + (1 if index < remainder else 0)
        for index, condition in enumerate(ordered_present)
    }


def select_bkt_ranked(candidates: list[tuple[str, float]], slots: int) -> list[str]:
    """BKT-on selection (Task 4.6): lowest treatment p(learned) first, word_id
    as a deterministic tiebreaker. ``candidates`` is (word_id, p_learned)."""
    if slots <= 0:
        return []
    ranked = sorted(candidates, key=lambda pair: (pair[1], pair[0]))
    return [word_id for word_id, _p_learned in ranked[:slots]]


def select_mastery_blind(candidates: list[tuple[str, int]], slots: int) -> list[str]:
    """BKT-off selection (Task 4.7): least-recently-practiced-by-count first,
    word_id as a deterministic tiebreaker. ``candidates`` is (word_id,
    prior_research_practice_exposure_count) - a raw count of past practice
    exposures, never accuracy, p(learned), or response time, so rotating
    through under-practiced words stays mastery-blind by construction."""
    if slots <= 0:
        return []
    ranked = sorted(candidates, key=lambda pair: (pair[1], pair[0]))
    return [word_id for word_id, _exposure_count in ranked[:slots]]
