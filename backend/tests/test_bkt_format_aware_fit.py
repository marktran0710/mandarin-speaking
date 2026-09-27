"""Offline format-aware BKT fit: recovery, identifiability and report gates."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from analytics.learner_model.bkt.core import BKT_CONFIG, replay_bkt_typed
from analytics.learner_model.bkt.format_aware_fit import (
    baseline_parameters,
    calibrate_format_aware_bkt,
    config_from_parameters,
    fit_format_aware_parameters,
    identifiability,
    score_records,
)
from analytics.learner_model.knowledge_tracing import ResponseRecord


TRUE_PARAMETERS = {
    "prior": 0.35, "learn": 0.25, "guess": 0.25, "slip": 0.08, "guess_typed": 0.03, "slip_typed": 0.20,
}
MCQ, TYPED = "basic_meaning_mcq", "character_to_pinyin_typing"


def simulate(parameters, *, students=40, words=20, per_word=4, seed=7):
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records, tick = [], 0
    for student in range(students):
        for word in range(words):
            known = rng.random() < parameters["prior"]
            for position in range(per_word):
                typed = position % 2 == 1
                guess = parameters["guess_typed" if typed else "guess"]
                slip = parameters["slip_typed" if typed else "slip"]
                correct = rng.random() >= slip if known else rng.random() < guess
                records.append(ResponseRecord(
                    student_id=f"S{student:03d}", concept_id=f"W{word:02d}", correct=correct,
                    occurred_at=start + timedelta(seconds=tick), attempt_id=f"a-{student}-{position}",
                    question_index=word, question_kind=TYPED if typed else MCQ,
                ))
                tick += 1
                if not known and rng.random() < parameters["learn"]:
                    known = True
    return records


def test_fit_recovers_known_parameters_from_repeated_answers():
    fitted, diagnostic = fit_format_aware_parameters(simulate(TRUE_PARAMETERS))

    assert diagnostic["status"] == "success"
    assert set(diagnostic["free"]) == {"prior", "learn", "guess", "slip", "guess_typed", "slip_typed"}
    for name, expected in TRUE_PARAMETERS.items():
        assert fitted[name] == pytest.approx(expected, abs=0.08), name


def test_single_answer_evidence_holds_learn_rate_and_warns():
    records = simulate(TRUE_PARAMETERS, per_word=1)
    report = identifiability(records)
    fitted, diagnostic = fit_format_aware_parameters(records)

    assert report["transitions"] == 0
    assert report["free"]["learn"] is False
    assert report["free"]["typed_pair"] is False  # position 0 is always MCQ here
    assert "learn" not in diagnostic["free"]
    assert fitted["learn"] == BKT_CONFIG.learn_rate
    assert fitted["guess_typed"] == BKT_CONFIG.guess_rate_typed
    assert fitted["slip_typed"] == BKT_CONFIG.slip_rate_typed
    assert any("P(T) held at baseline" in warning for warning in report["warnings"])
    assert any("weakly separable" in warning for warning in report["warnings"])


def test_scoring_matches_production_replay_arithmetic():
    records = simulate(TRUE_PARAMETERS, students=1, words=1, per_word=5)
    parameters = baseline_parameters()
    outcomes, predictions = score_records(records, parameters)

    mastery = BKT_CONFIG.initial_mastery
    for record, prediction in zip(records, predictions):
        guess, slip = (
            (BKT_CONFIG.guess_rate_typed, BKT_CONFIG.slip_rate_typed)
            if record.question_kind == TYPED
            else (BKT_CONFIG.guess_rate, BKT_CONFIG.slip_rate)
        )
        assert prediction == pytest.approx(mastery * (1 - slip) + (1 - mastery) * guess, abs=1e-12)
        mastery = replay_bkt_typed([(record.correct, record.question_kind)], BKT_CONFIG, initial_mastery=mastery)
    assert outcomes == [record.correct for record in records]


def test_report_beats_defaults_out_of_sample_and_passes_gates():
    report = calibrate_format_aware_bkt(simulate(TRUE_PARAMETERS))

    assert report["gates_passed"] is True
    assert report["promotable"] is True
    assert report["metrics"]["candidate"]["log_loss"] < report["metrics"]["production"]["log_loss"]
    assert all(not fold["student_overlap"] for fold in report["folds"])
    assert report["gates"]["production_model_compatibility"] is True


def test_synthetic_evidence_is_never_promotable():
    report = calibrate_format_aware_bkt(simulate(TRUE_PARAMETERS), synthetic=True)

    assert report["gates_passed"] is True
    assert report["promotable"] is False


def test_config_keeps_policy_fields_from_the_base():
    config = config_from_parameters(TRUE_PARAMETERS)

    assert config.learn_rate == TRUE_PARAMETERS["learn"]
    assert config.guess_rate_typed == TRUE_PARAMETERS["guess_typed"]
    assert config.mastery_threshold == BKT_CONFIG.mastery_threshold
    assert config.minimum_observations == BKT_CONFIG.minimum_observations
