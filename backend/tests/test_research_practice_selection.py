"""Epic 4, Task 4.5/4.6/4.7: pure practice-session selection math."""
from domain.research.assignment import AssignmentCondition, BktPolicy, RetentionPolicy, condition_for_policies
from domain.research.practice import allocate_slots, select_bkt_ranked, select_mastery_blind


def test_condition_for_policies_matches_the_2x2_design():
    assert condition_for_policies(BktPolicy.MASTERY_BLIND, RetentionPolicy.YOKED) == AssignmentCondition.CONTROL
    assert condition_for_policies(BktPolicy.BKT_PERSONALIZED, RetentionPolicy.YOKED) == AssignmentCondition.BKT
    assert condition_for_policies(BktPolicy.MASTERY_BLIND, RetentionPolicy.ADAPTIVE_SM2) == AssignmentCondition.SRS
    assert condition_for_policies(BktPolicy.BKT_PERSONALIZED, RetentionPolicy.ADAPTIVE_SM2) == AssignmentCondition.BKT_SRS


def test_allocate_slots_splits_the_plans_own_worked_example_evenly():
    slots = allocate_slots(8, [AssignmentCondition.CONTROL, AssignmentCondition.BKT, AssignmentCondition.SRS, AssignmentCondition.BKT_SRS])
    assert slots == {
        AssignmentCondition.CONTROL: 2, AssignmentCondition.BKT: 2,
        AssignmentCondition.SRS: 2, AssignmentCondition.BKT_SRS: 2,
    }


def test_allocate_slots_gives_remainder_to_earliest_conditions_deterministically():
    slots = allocate_slots(9, [AssignmentCondition.CONTROL, AssignmentCondition.BKT, AssignmentCondition.SRS, AssignmentCondition.BKT_SRS])
    # 9 // 4 = 2 remainder 1 -> the extra slot goes to CONTROL (first in
    # CONDITION_ORDER), never to whichever condition happens to sort first
    # in a dict/set.
    assert slots == {
        AssignmentCondition.CONTROL: 3, AssignmentCondition.BKT: 2,
        AssignmentCondition.SRS: 2, AssignmentCondition.BKT_SRS: 2,
    }


def test_allocate_slots_only_pays_out_conditions_actually_present():
    slots = allocate_slots(8, [AssignmentCondition.BKT, AssignmentCondition.SRS])
    assert slots == {AssignmentCondition.BKT: 4, AssignmentCondition.SRS: 4}
    assert AssignmentCondition.CONTROL not in slots


def test_allocate_slots_handles_zero_budget_and_no_conditions():
    assert allocate_slots(0, [AssignmentCondition.CONTROL]) == {AssignmentCondition.CONTROL: 0}
    assert allocate_slots(8, []) == {}


def test_select_bkt_ranked_picks_lowest_p_learned_first():
    candidates = [("w-high", 0.9), ("w-low", 0.1), ("w-mid", 0.5)]
    assert select_bkt_ranked(candidates, slots=2) == ["w-low", "w-mid"]


def test_select_bkt_ranked_breaks_ties_by_word_id():
    candidates = [("z-word", 0.4), ("a-word", 0.4)]
    assert select_bkt_ranked(candidates, slots=1) == ["a-word"]


def test_select_bkt_ranked_respects_the_slot_cap_and_zero_slots():
    candidates = [("a", 0.1), ("b", 0.2), ("c", 0.3)]
    assert len(select_bkt_ranked(candidates, slots=2)) == 2
    assert select_bkt_ranked(candidates, slots=0) == []


def test_select_mastery_blind_picks_least_exposed_first():
    candidates = [("w-seen-5", 5), ("w-seen-0", 0), ("w-seen-2", 2)]
    assert select_mastery_blind(candidates, slots=2) == ["w-seen-0", "w-seen-2"]


def test_select_mastery_blind_breaks_ties_by_word_id_not_by_any_performance_signal():
    # Same exposure count for both - the only thing that can break the tie is
    # word_id, never something that would smuggle in an accuracy signal.
    candidates = [("z-word", 1), ("a-word", 1)]
    assert select_mastery_blind(candidates, slots=1) == ["a-word"]
