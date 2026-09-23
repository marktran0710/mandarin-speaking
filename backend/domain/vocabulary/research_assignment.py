"""Pure counterbalancing/condition math for the frozen item-assignment engine
(BKT x SM-2 research-mode plan, Epic 2).

No database, no I/O, no randomness - every function here is a deterministic
mapping from inputs to outputs, so the same word list + participant roster
always produces the same assignments no matter how many times it's run.
That determinism is what makes an assignment run auditable and safe to
diff before freezing.

## The 2x2 design

Four conditions come from crossing two independent factors:

    bkt_policy:       mastery_blind      | bkt_personalized
    retention_policy: yoked              | adaptive_sm2

    C  (control)        = mastery_blind      + yoked
    B  (BKT only)        = bkt_personalized   + yoked
    S  (SRS only)         = mastery_blind      + adaptive_sm2
    BS (BKT + SRS)         = bkt_personalized   + adaptive_sm2

A "yoked" word doesn't get its own retention schedule - it mirrors a
same-BKT-policy word that DOES get an adaptive schedule (C mirrors an S
word, B mirrors a BS word), so retention policy is the only thing that
differs within a yoke pair. See yoke_pairs_for_student().

## Counterbalancing

Each student is assigned exactly one of four sequences (A/B/C/D), a fixed
cyclic order of the four conditions. As a student's eligible word list is
walked in presentation order, each word's condition is
``sequence[position % 4]``. Assigning sequences round-robin across a roster
(ordered by student_id) balances which condition a student sees FIRST
across the whole study, without needing randomness.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AssignmentCondition(str, Enum):
    CONTROL = "C"
    BKT = "B"
    SRS = "S"
    BKT_SRS = "BS"


class BktPolicy(str, Enum):
    MASTERY_BLIND = "mastery_blind"
    BKT_PERSONALIZED = "bkt_personalized"


class RetentionPolicy(str, Enum):
    YOKED = "yoked"
    ADAPTIVE_SM2 = "adaptive_sm2"


CONDITION_POLICIES: dict[AssignmentCondition, tuple[BktPolicy, RetentionPolicy]] = {
    AssignmentCondition.CONTROL: (BktPolicy.MASTERY_BLIND, RetentionPolicy.YOKED),
    AssignmentCondition.BKT: (BktPolicy.BKT_PERSONALIZED, RetentionPolicy.YOKED),
    AssignmentCondition.SRS: (BktPolicy.MASTERY_BLIND, RetentionPolicy.ADAPTIVE_SM2),
    AssignmentCondition.BKT_SRS: (BktPolicy.BKT_PERSONALIZED, RetentionPolicy.ADAPTIVE_SM2),
}

# The assignment table persists bkt_policy/retention_policy per word, not the
# condition letter itself (see vocab_research_assignments). Epic 4's practice
# budget needs to balance slots per condition, so this reverses the mapping
# above rather than introducing a second, potentially-divergent source of
# truth for what a (bkt_policy, retention_policy) pair means.
_POLICY_PAIR_TO_CONDITION: dict[tuple[BktPolicy, RetentionPolicy], AssignmentCondition] = {
    policies: condition for condition, policies in CONDITION_POLICIES.items()
}


def condition_for_policies(bkt_policy: BktPolicy, retention_policy: RetentionPolicy) -> AssignmentCondition:
    return _POLICY_PAIR_TO_CONDITION[(bkt_policy, retention_policy)]

# A yoked-condition word mirrors a same-BKT-policy adaptive word, isolating
# the retention-policy factor: C only ever differs from S in retention
# policy (both mastery_blind); B only ever differs from BS in retention
# policy (both bkt_personalized).
YOKE_SOURCE_CONDITION: dict[AssignmentCondition, AssignmentCondition] = {
    AssignmentCondition.CONTROL: AssignmentCondition.SRS,
    AssignmentCondition.BKT: AssignmentCondition.BKT_SRS,
}

COUNTERBALANCE_SEQUENCES: dict[str, tuple[AssignmentCondition, ...]] = {
    "A": (AssignmentCondition.CONTROL, AssignmentCondition.BKT, AssignmentCondition.SRS, AssignmentCondition.BKT_SRS),
    "B": (AssignmentCondition.BKT, AssignmentCondition.SRS, AssignmentCondition.BKT_SRS, AssignmentCondition.CONTROL),
    "C": (AssignmentCondition.SRS, AssignmentCondition.BKT_SRS, AssignmentCondition.CONTROL, AssignmentCondition.BKT),
    "D": (AssignmentCondition.BKT_SRS, AssignmentCondition.CONTROL, AssignmentCondition.BKT, AssignmentCondition.SRS),
}
SEQUENCE_IDS: tuple[str, ...] = tuple(sorted(COUNTERBALANCE_SEQUENCES))  # ("A", "B", "C", "D")


def sequence_for_roster_position(position: int) -> str:
    """Round-robin A, B, C, D, A, B, C, D, ... across a roster ordered by
    student_id. Deterministic and balanced regardless of roster size."""
    return SEQUENCE_IDS[position % len(SEQUENCE_IDS)]


def condition_for_position(sequence_id: str, position: int) -> AssignmentCondition:
    sequence = COUNTERBALANCE_SEQUENCES[sequence_id]
    return sequence[position % len(sequence)]


@dataclass(frozen=True)
class AssignmentUnit:
    """One assignable slot in a student's word list: a single word, or the
    representative of a related set (see group_related_sets) that must all
    share one condition for this student."""

    word_ids: tuple[str, ...]
    related_set_id: str | None


def group_related_sets(
    ordered_word_ids: list[str],
    related_set_by_word: dict[str, str],
) -> list[AssignmentUnit]:
    """Collapses a word list into assignment units: a related set becomes
    ONE unit (taking the presentation position of its first-seen member) so
    every member gets the same condition; other words stay their own unit.
    Preserves first-seen order otherwise, so word position in the source
    curriculum still drives condition assignment via the sequence cycle.
    """
    units: list[AssignmentUnit] = []
    seen_sets: dict[str, int] = {}  # related_set_id -> index into units
    for word_id in ordered_word_ids:
        set_id = related_set_by_word.get(word_id)
        if set_id is None:
            units.append(AssignmentUnit(word_ids=(word_id,), related_set_id=None))
            continue
        existing_index = seen_sets.get(set_id)
        if existing_index is None:
            seen_sets[set_id] = len(units)
            units.append(AssignmentUnit(word_ids=(word_id,), related_set_id=set_id))
        else:
            existing = units[existing_index]
            units[existing_index] = AssignmentUnit(
                word_ids=existing.word_ids + (word_id,), related_set_id=set_id
            )
    return units


@dataclass(frozen=True)
class WordAssignment:
    word_id: str
    condition: AssignmentCondition
    related_set_id: str | None


def assign_conditions_for_student(
    sequence_id: str, units: list[AssignmentUnit]
) -> list[WordAssignment]:
    """Walks a student's assignment units in order, cycling the student's
    sequence, and expands each unit back out to one WordAssignment per word
    (every word in a related set gets the unit's single condition)."""
    assignments: list[WordAssignment] = []
    for position, unit in enumerate(units):
        condition = condition_for_position(sequence_id, position)
        for word_id in unit.word_ids:
            assignments.append(
                WordAssignment(word_id=word_id, condition=condition, related_set_id=unit.related_set_id)
            )
    return assignments


def yoke_pairs_for_student(
    assignments: list[WordAssignment],
) -> dict[str, str]:
    """Positionally pairs each yoked-condition word with a same-BKT-policy
    adaptive word for the same student: the i-th C word yokes to the i-th S
    word, the i-th B word yokes to the i-th BS word. If a yoked condition
    has more words than its adaptive counterpart (uneven due to word-list
    length not being a multiple of 4, or related-set clumping), the excess
    yoked words are left unpaired (absent from the returned dict) rather
    than guessed at - the caller must treat that as an audit finding, not
    silently pick an arbitrary source.

    Returns {word_id: yoke_source_word_id}.
    """
    by_condition: dict[AssignmentCondition, list[str]] = {c: [] for c in AssignmentCondition}
    for assignment in assignments:
        by_condition[assignment.condition].append(assignment.word_id)

    pairs: dict[str, str] = {}
    for yoked_condition, source_condition in YOKE_SOURCE_CONDITION.items():
        yoked_words = by_condition[yoked_condition]
        source_words = by_condition[source_condition]
        for yoked_word, source_word in zip(yoked_words, source_words):
            pairs[yoked_word] = source_word
    return pairs
