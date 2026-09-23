"""Pure unit tests for domain/vocabulary/research_assignment.py - no database."""
from domain.vocabulary.research_assignment import (
    AssignmentCondition,
    AssignmentUnit,
    CONDITION_POLICIES,
    BktPolicy,
    RetentionPolicy,
    assign_conditions_for_student,
    condition_for_position,
    group_related_sets,
    sequence_for_roster_position,
    yoke_pairs_for_student,
)


def test_the_2x2_design_is_exactly_four_distinct_condition_policy_pairs():
    pairs = set(CONDITION_POLICIES.values())
    assert len(pairs) == 4
    assert (BktPolicy.MASTERY_BLIND, RetentionPolicy.YOKED) == CONDITION_POLICIES[AssignmentCondition.CONTROL]
    assert (BktPolicy.BKT_PERSONALIZED, RetentionPolicy.YOKED) == CONDITION_POLICIES[AssignmentCondition.BKT]
    assert (BktPolicy.MASTERY_BLIND, RetentionPolicy.ADAPTIVE_SM2) == CONDITION_POLICIES[AssignmentCondition.SRS]
    assert (BktPolicy.BKT_PERSONALIZED, RetentionPolicy.ADAPTIVE_SM2) == CONDITION_POLICIES[AssignmentCondition.BKT_SRS]


def test_roster_position_cycles_through_all_four_sequences_evenly():
    assigned = [sequence_for_roster_position(i) for i in range(8)]
    assert assigned == ["A", "B", "C", "D", "A", "B", "C", "D"]


def test_each_sequence_visits_every_condition_exactly_once_per_cycle():
    from domain.vocabulary.research_assignment import COUNTERBALANCE_SEQUENCES

    for sequence in COUNTERBALANCE_SEQUENCES.values():
        assert set(sequence) == set(AssignmentCondition)
        assert len(sequence) == 4


def test_condition_for_position_cycles_correctly():
    conditions = [condition_for_position("A", i) for i in range(8)]
    assert conditions == [
        AssignmentCondition.CONTROL, AssignmentCondition.BKT,
        AssignmentCondition.SRS, AssignmentCondition.BKT_SRS,
        AssignmentCondition.CONTROL, AssignmentCondition.BKT,
        AssignmentCondition.SRS, AssignmentCondition.BKT_SRS,
    ]


def test_group_related_sets_collapses_a_set_into_one_unit_at_its_first_seen_position():
    units = group_related_sets(
        ["前", "上", "後", "下"],
        related_set_by_word={"前": "front-back", "後": "front-back"},
    )
    assert units == [
        AssignmentUnit(word_ids=("前", "後"), related_set_id="front-back"),
        AssignmentUnit(word_ids=("上",), related_set_id=None),
        AssignmentUnit(word_ids=("下",), related_set_id=None),
    ]


def test_group_related_sets_leaves_unrelated_words_as_singleton_units_in_order():
    units = group_related_sets(["a", "b", "c"], related_set_by_word={})
    assert [u.word_ids for u in units] == [("a",), ("b",), ("c",)]


def test_assign_conditions_for_student_gives_every_word_in_a_related_set_the_same_condition():
    units = [
        AssignmentUnit(word_ids=("前", "後"), related_set_id="front-back"),
        AssignmentUnit(word_ids=("上",), related_set_id=None),
    ]
    assignments = assign_conditions_for_student("A", units)
    by_word = {a.word_id: a.condition for a in assignments}
    assert by_word["前"] == by_word["後"] == AssignmentCondition.CONTROL
    assert by_word["上"] == AssignmentCondition.BKT


def test_two_students_on_different_sequences_get_the_same_related_set_in_different_conditions():
    # This is what makes counterbalancing satisfy "a related set rotates
    # across conditions across learners" without any extra logic - the same
    # word-list position simply lands on a different condition per sequence.
    units = [AssignmentUnit(word_ids=("前", "後"), related_set_id="front-back")]
    student_a = assign_conditions_for_student("A", units)
    student_b = assign_conditions_for_student("B", units)
    assert student_a[0].condition != student_b[0].condition


def test_yoke_pairs_positionally_pair_control_with_srs_and_bkt_with_bkt_srs():
    from domain.vocabulary.research_assignment import WordAssignment

    assignments = [
        WordAssignment("c1", AssignmentCondition.CONTROL, None),
        WordAssignment("c2", AssignmentCondition.CONTROL, None),
        WordAssignment("s1", AssignmentCondition.SRS, None),
        WordAssignment("s2", AssignmentCondition.SRS, None),
        WordAssignment("b1", AssignmentCondition.BKT, None),
        WordAssignment("bs1", AssignmentCondition.BKT_SRS, None),
    ]
    pairs = yoke_pairs_for_student(assignments)
    assert pairs == {"c1": "s1", "c2": "s2", "b1": "bs1"}


def test_yoke_pairs_leaves_excess_yoked_words_unpaired_rather_than_guessing():
    from domain.vocabulary.research_assignment import WordAssignment

    assignments = [
        WordAssignment("c1", AssignmentCondition.CONTROL, None),
        WordAssignment("c2", AssignmentCondition.CONTROL, None),
        WordAssignment("s1", AssignmentCondition.SRS, None),  # only one S word for two C words
    ]
    pairs = yoke_pairs_for_student(assignments)
    assert pairs == {"c1": "s1"}
    assert "c2" not in pairs


def test_full_pipeline_end_to_end_for_one_student():
    ordered_words = ["w1", "w2", "w3", "w4", "w5", "w6", "w7", "w8"]
    units = group_related_sets(ordered_words, related_set_by_word={})
    assignments = assign_conditions_for_student(sequence_for_roster_position(0), units)
    conditions = [a.condition for a in assignments]
    # 8 words, sequence A cycles twice: C,B,S,BS,C,B,S,BS
    assert conditions == [
        AssignmentCondition.CONTROL, AssignmentCondition.BKT, AssignmentCondition.SRS, AssignmentCondition.BKT_SRS,
        AssignmentCondition.CONTROL, AssignmentCondition.BKT, AssignmentCondition.SRS, AssignmentCondition.BKT_SRS,
    ]
    pairs = yoke_pairs_for_student(assignments)
    assert pairs == {"w1": "w3", "w5": "w7", "w2": "w4", "w6": "w8"}
