"""Contextual tone realization rules.

Every test here is a linguistic claim, so each one says which claim it is
making. Where Mandarin genuinely allows more than one realization the test
asserts that *both* are accepted rather than picking a winner — an app that
insists on one reading of 我很好 is wrong about half the time.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tone_context import (
    FULL_THIRD,
    HALF_THIRD,
    RULE_BU,
    RULE_NEUTRAL_OPTIONAL,
    RULE_T3_CHAIN,
    RULE_T3_T3,
    RULE_YI,
    THIRD_CHAIN,
    THIRD_SANDHI,
    plan_expected_tones,
    plan_for_tokens,
)


def accepted(plan):
    return [tuple(item.accepted_surface_tones) for item in plan]


# ── A / B / F: third-tone sandhi, including across token boundaries ───────


def test_ni_hao_first_syllable_accepts_the_rising_realization():
    """你好: T3+T3 → the first is produced as a rising T2."""
    plan = plan_expected_tones(["你", "好"], [3, 3])
    assert accepted(plan) == [(2,), (3,)]
    assert plan[0].underlying_tone == 3, "the dictionary tone must survive"
    assert plan[0].realization == THIRD_SANDHI
    assert plan[0].rule == RULE_T3_T3


def test_hen_hao_gets_sandhi_even_though_jieba_splits_it():
    """很好 is the bug this layer exists for.

    jieba segments it as 很 / 好, and the legacy per-token sandhi therefore
    saw a lone T3 with nothing after it and scored 很 against a full dipping
    template. Planning over the whole utterance sees the pair.
    """
    plan = plan_for_tokens(["很", "好"])
    assert [item.char for item in plan] == ["很", "好"]
    assert accepted(plan) == [(2,), (3,)]
    assert plan[0].rule == RULE_T3_T3
    # The token boundary is still recorded, for later prosodic work.
    assert plan[0].token_index == 0 and plan[1].token_index == 1
    assert plan[1].boundary_before is True


def test_youmei_keeps_its_already_correct_behaviour():
    """友美 was already handled (one jieba token) and must not regress."""
    plan = plan_for_tokens(["友美"])
    assert plan[0].underlying_tone == 3
    assert 2 in plan[0].accepted_surface_tones
    assert plan[1].accepted_surface_tones == (3,)


def test_a_run_of_three_third_tones_accepts_both_groupings():
    """我很好: documented behaviour, not a claim that one reading is right.

    Whether this is [2,2,3] or [3,2,3] depends on where the speaker groups the
    phrase, and nothing in the pipeline knows that. Both readings are accepted
    for the non-final syllables; the final one stays T3 either way. Narrowing
    this needs phrase boundaries the analyzer does not yet produce.
    """
    plan = plan_for_tokens(["我", "很", "好"])
    assert accepted(plan) == [(2, 3), (2, 3), (3,)]
    assert plan[0].realization == THIRD_CHAIN
    assert plan[0].rule == RULE_T3_CHAIN
    assert plan[2].accepted_surface_tones == (3,)


# ── C: half third ─────────────────────────────────────────────────────────


def test_third_tone_before_a_fourth_is_marked_half_third():
    """妳這: T3 keeps its class but is realized as the low part only.

    The learner does not have to produce a full fall-rise here, so the shape
    the scorer should eventually expect is different. The class stays T3 — no
    fake fifth tone class is invented.
    """
    plan = plan_expected_tones(["妳", "這"], [3, 4])
    assert plan[0].accepted_surface_tones == (3,)
    assert plan[0].realization == HALF_THIRD


def test_a_final_third_tone_stays_full():
    plan = plan_expected_tones(["好"], [3])
    assert plan[0].realization == FULL_THIRD
    plan = plan_expected_tones(["你", "好"], [3, 3])
    assert plan[1].realization == FULL_THIRD


# ── D: 不 ─────────────────────────────────────────────────────────────────


def test_bu_rises_before_a_fourth_tone():
    """不是 bú shì. pypinyin happens to list this one; the rule must not
    depend on that — see the next test."""
    plan = plan_for_tokens(["不是"])
    assert plan[0].underlying_tone == 4, "不's citation tone is T4"
    assert plan[0].accepted_surface_tones == (2,)
    assert plan[0].rule == RULE_BU


def test_bu_rises_before_a_fourth_tone_pypinyin_does_not_know():
    """不去 bú qù — pypinyin returns bù qù for this, so a lookup-only
    implementation gets it wrong. The rule catches it."""
    plan = plan_for_tokens(["不去"])
    assert plan[0].accepted_surface_tones == (2,)


def test_bu_keeps_its_falling_tone_elsewhere():
    for word in ("不好", "不吃"):
        plan = plan_for_tokens([word])
        assert plan[0].accepted_surface_tones == (4,), word


# ── E: 一 ─────────────────────────────────────────────────────────────────


def test_yi_before_a_fourth_tone_rises():
    """一次 yí cì."""
    plan = plan_for_tokens(["一次"])
    assert plan[0].underlying_tone == 1
    assert plan[0].accepted_surface_tones == (2,)
    assert plan[0].rule == RULE_YI


def test_yi_falls_before_other_tones():
    """一天 yì tiān."""
    plan = plan_for_tokens(["一天"])
    assert plan[0].accepted_surface_tones == (4,)


def test_yi_keeps_its_citation_tone_as_an_ordinal_and_in_isolation():
    plan = plan_for_tokens(["第一"])
    assert plan[1].accepted_surface_tones == (1,)
    plan = plan_expected_tones(["一"], [1])
    assert plan[0].accepted_surface_tones == (1,)


def test_yi_before_a_neutral_syllable_accepts_both_readings():
    """一個: the neutral syllable's underlying tone is gone, so the rule has
    nothing to condition on. Accepting both beats guessing."""
    plan = plan_expected_tones(["一", "個"], [1, 5])
    assert set(plan[0].accepted_surface_tones) == {2, 4}


# ── F: contextual neutral ─────────────────────────────────────────────────


def test_zhege_accepts_both_the_full_tone_and_neutral():
    """這個: 個 is usually destressed but a full T4 is not an error."""
    plan = plan_for_tokens(["這個"])
    assert plan[1].char == "個"
    assert set(plan[1].accepted_surface_tones) == {4, 5}
    assert plan[1].rule == RULE_NEUTRAL_OPTIONAL


def test_lexical_neutral_is_not_measurable_by_contour():
    """麼 is neutral, and neutral tone has no contour target at all — the
    scorer's constant 75 for it is not a measurement."""
    plan = plan_expected_tones(["什", "麼"], [2, 5])
    assert plan[1].accepted_surface_tones == (5,)
    assert plan[1].measurable_by_contour is False
    assert plan[0].measurable_by_contour is True


# ── G: nothing else moves ─────────────────────────────────────────────────


@pytest.mark.parametrize("tone", [1, 2, 4])
def test_an_isolated_non_third_tone_is_unchanged(tone):
    plan = plan_expected_tones(["書"], [tone])
    assert plan[0].accepted_surface_tones == (tone,)
    assert plan[0].underlying_tone == tone
    assert plan[0].rule is None


def test_the_dictionary_tone_is_never_overwritten():
    """Provenance is the point: the underlying tone stays readable even when
    the accepted surface form is something else entirely."""
    plan = plan_for_tokens(["不是"])
    assert (plan[0].underlying_tone, plan[0].accepted_surface_tones) == (4, (2,))
    plan = plan_expected_tones(["你", "好"], [3, 3])
    assert (plan[0].underlying_tone, plan[0].accepted_surface_tones) == (3, (2,))


def test_empty_and_mismatched_input_is_survivable():
    assert plan_expected_tones([], []) == []
    assert plan_expected_tones(["你"], [3, 3]) == []
    assert plan_for_tokens(["hello", "123"]) == []
