from dataclasses import replace

import pytest

from analytics.learner_model.bkt.core import (
    BKT_CONFIG,
    guess_slip_for,
    mastery_status,
    replay_bkt,
    replay_bkt_typed,
    update_bkt,
)


def test_correct_response_increases_mastery():
    assert update_bkt(0.4, True) > 0.4


def test_incorrect_response_reduces_mastery():
    assert update_bkt(0.4, False) < 0.4


def test_probability_is_clamped_to_safe_range():
    for correct in (True, False):
        value = update_bkt(0.0, correct)
        assert 0.000001 <= value <= 0.999999
        value = update_bkt(1.0, correct)
        assert 0.000001 <= value <= 0.999999


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_probability_is_rejected(value):
    with pytest.raises(ValueError, match="must be finite"):
        update_bkt(value, True)


@pytest.mark.parametrize(
    "field",
    ["minimum_observations", "required_diagnostic_quizzes", "review_count"],
)
def test_non_positive_count_configuration_is_rejected(field):
    invalid = replace(BKT_CONFIG, **{field: 0})
    with pytest.raises(ValueError, match="count settings must be positive"):
        update_bkt(BKT_CONFIG.initial_mastery, True, invalid)


def test_replay_is_deterministic_and_order_sensitive():
    first = replay_bkt([False, True, True])
    second = replay_bkt([False, True, True])
    reordered = replay_bkt([True, True, False])
    assert first == second
    assert first != reordered


def test_default_configuration_is_centralized_and_temporary():
    assert BKT_CONFIG.initial_mastery == 0.2
    assert BKT_CONFIG.mastery_threshold == 0.95


def test_sparse_evidence_stays_unassessed():
    assert mastery_status(0, BKT_CONFIG.initial_mastery) == "UNASSESSED"
    assert mastery_status(BKT_CONFIG.minimum_observations - 1, 0.99) == "UNASSESSED"


@pytest.mark.parametrize(
    ("observation_count", "p_learned", "selected_for_review", "expected"),
    [
        (3, 0.40, False, "DEVELOPING"),
        (3, 0.40, True, "NEEDS_PRACTICE"),
        (3, BKT_CONFIG.mastery_threshold, False, "STRONG"),
    ],
)
def test_mastery_status_uses_evidence_before_threshold(
    observation_count, p_learned, selected_for_review, expected,
):
    assert mastery_status(
        observation_count,
        p_learned,
        selected_for_review=selected_for_review,
    ) == expected


@pytest.mark.parametrize("field", [
    "initial_mastery",
    "learn_rate",
    "guess_rate",
    "slip_rate",
    "mastery_threshold",
])
def test_update_rejects_invalid_probability_configuration(field):
    invalid = replace(BKT_CONFIG, **{field: 1.1})
    with pytest.raises(ValueError, match=field):
        update_bkt(BKT_CONFIG.initial_mastery, True, invalid)


def test_replay_with_no_observations_returns_initial_mastery():
    assert replay_bkt([]) == pytest.approx(BKT_CONFIG.initial_mastery)


def test_format_aware_rates_reward_typed_correctness_more_than_mcq():
    mcq = update_bkt(0.2, True, guess=0.20, slip=0.10)
    typed = update_bkt(0.2, True, guess=0.05, slip=0.15)

    assert guess_slip_for("basic_meaning_mcq") == pytest.approx((0.20, 0.10))
    assert guess_slip_for("character_to_pinyin_typing") == pytest.approx((0.05, 0.15))
    assert typed > mcq


def test_format_aware_typed_incorrectness_is_less_punitive_than_mcq():
    mcq = update_bkt(0.2, False, guess=0.20, slip=0.10)
    typed = update_bkt(0.2, False, guess=0.05, slip=0.15)

    assert typed > mcq


def test_format_aware_replay_has_a_stable_mixed_golden_vector():
    responses = [
        (True, "basic_meaning_mcq"),
        (True, "character_to_pinyin_typing"),
        (False, "context_cloze_mcq"),
        (True, "character_to_pinyin_typing"),
        (True, "context_cloze_mcq"),
    ]

    assert replay_bkt_typed(responses) == pytest.approx(0.9979619773755845)


def test_guess_slip_configuration_requires_meaningful_discrimination():
    invalid_mcq = replace(BKT_CONFIG, guess_rate=0.9, slip_rate=0.101)
    invalid_typed = replace(BKT_CONFIG, guess_rate_typed=0.85, slip_rate_typed=0.151)

    with pytest.raises(ValueError, match="meaningfully greater"):
        update_bkt(0.2, True, invalid_mcq)
    with pytest.raises(ValueError, match="meaningfully greater"):
        update_bkt(0.2, True, invalid_typed)
    with pytest.raises(ValueError, match="meaningfully greater"):
        update_bkt(0.2, True, guess=0.9, slip=0.101)
