from datetime import datetime, timezone

from analytics.learner_model.bkt.core import BKT_CONFIG, update_bkt_trace
from analytics.learner_model.srs import SrsState, enrollment_state, review
from services.algorithm_verifier_reference import bkt_sequence, sm2_transition


def test_reference_bkt_is_independent_and_matches_production_steps():
    observations = [
        {"correct": True, "questionType": "basic_meaning_mcq"},
        {"correct": True, "questionType": "character_to_pinyin_typing"},
        {"correct": False, "questionType": "context_cloze_mcq"},
    ]
    expected = bkt_sequence(
        observations,
        initial_mastery=BKT_CONFIG.initial_mastery,
        learn_rate=BKT_CONFIG.learn_rate,
        mcq_guess=BKT_CONFIG.guess_rate,
        mcq_slip=BKT_CONFIG.slip_rate,
        typed_guess=BKT_CONFIG.guess_rate_typed,
        typed_slip=BKT_CONFIG.slip_rate_typed,
    )
    actual = []
    prior = BKT_CONFIG.initial_mastery
    for observation in observations:
        guess, slip = (
            (BKT_CONFIG.guess_rate_typed, BKT_CONFIG.slip_rate_typed)
            if observation["questionType"] in {"character_to_pinyin_typing", "productive_recall", "contextual_productive_recall"}
            else (BKT_CONFIG.guess_rate, BKT_CONFIG.slip_rate)
        )
        step = update_bkt_trace(prior, observation["correct"], guess=guess, slip=slip)
        actual.append(step)
        prior = step["resultingMastery"]
    assert [step["resultingMastery"] for step in expected] == [step["resultingMastery"] for step in actual]


def test_reference_sm2_matches_production_transition_and_exposes_raw_interval():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    state = SrsState(reps=2, ease=2.5, interval_days=3)
    reference = sm2_transition(
        repetitions=state.reps,
        interval_days=state.interval_days,
        ease=state.ease,
        quality=4,
        now=now,
        day_seconds=86400,
    )
    actual = review(state, 4, now)
    assert reference["rawInterval"] == 7.5
    assert (reference["repetitions"], reference["intervalDays"], reference["ease"]) == (
        actual.reps,
        actual.interval_days,
        actual.ease,
    )
    assert reference["nextDue"] == actual.due_on


def test_enrollment_state_is_the_first_one_day_schedule():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    state = enrollment_state(now)
    assert (state.reps, state.interval_days, state.ease) == (1, 1, 2.5)
    assert state.due_on == datetime(2026, 8, 2, tzinfo=timezone.utc)
