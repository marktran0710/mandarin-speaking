"""The scoring policy is the single home for every weight and threshold."""

import pytest

from domain.pronunciation.policy import PronunciationScoringPolicy


def test_default_policy_uses_the_documented_weights_and_a_version():
    policy = PronunciationScoringPolicy()
    assert policy.version == "pronunciation-score-v1"
    assert policy.weights.as_dict() == {
        "tone": 0.40,
        "segmental": 0.30,
        "fluency": 0.20,
        "intelligibility": 0.10,
    }


def test_weights_are_overridable_from_the_environment():
    policy = PronunciationScoringPolicy.from_env(
        {
            "PRONUNCIATION_WEIGHT_TONE": "0.5",
            "PRONUNCIATION_WEIGHT_FLUENCY": "0.25",
        }
    )
    assert policy.weights.tone == 0.5
    assert policy.weights.fluency == 0.25
    # Untouched dimensions keep their defaults.
    assert policy.weights.segmental == 0.30


@pytest.mark.parametrize(
    "bad",
    [{"PRONUNCIATION_WEIGHT_TONE": "-1"}, {"PRONUNCIATION_WEIGHT_TONE": "abc"}],
)
def test_invalid_weight_configuration_fails_loudly(bad):
    # A research score must never silently fall back to different weights.
    with pytest.raises(ValueError):
        PronunciationScoringPolicy.from_env(bad)


def test_all_zero_weights_are_rejected():
    with pytest.raises(ValueError):
        PronunciationScoringPolicy.from_env(
            {
                "PRONUNCIATION_WEIGHT_TONE": "0",
                "PRONUNCIATION_WEIGHT_SEGMENTAL": "0",
                "PRONUNCIATION_WEIGHT_FLUENCY": "0",
                "PRONUNCIATION_WEIGHT_INTELLIGIBILITY": "0",
            }
        )


def test_policy_serialises_for_provenance():
    snapshot = PronunciationScoringPolicy().to_dict()
    assert snapshot["version"] == "pronunciation-score-v1"
    assert snapshot["weights"]["tone"] == 0.40
    assert "similarity" in snapshot
