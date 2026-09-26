"""Versioned BKT reference vectors for the admin verification contract."""

from __future__ import annotations

from typing import Any, Iterable

from analytics.learner_model.bkt.core import (
    BKT_CONFIG,
    BKT_MODEL_VERSION,
    bkt_parameter_fingerprint,
    guess_slip_for,
    mastery_status,
    replay_bkt_typed,
)


GOLDEN_FIXTURE_VERSION = "format-aware-bkt-v2"
GOLDEN_PARAMETER_FINGERPRINT = "53495ed0dc1c43b597d2c963df245bbc9218387f903a87ff2329f284f49d55f9"
GOLDEN_TOLERANCE = 1e-9
_REFERENCE_TYPED_TYPES = frozenset({
    "character_to_pinyin_typing",
    "contextual_productive_recall",
    "productive_recall",
})

# These values are the reviewed contract for format-aware-bkt-v2. They are
# intentionally not read from BKT_CONFIG: changing runtime config must show
# MODEL CONTRACT CHANGED rather than rewriting the research fixture.
_GOLDEN_INITIAL_MASTERY = 0.20
_GOLDEN_LEARN_RATE = 0.15
_GOLDEN_MCQ_GUESS = 0.20
_GOLDEN_MCQ_SLIP = 0.10
_GOLDEN_TYPED_GUESS = 0.05
_GOLDEN_TYPED_SLIP = 0.15
_GOLDEN_MASTERY_THRESHOLD = 0.95
_GOLDEN_MINIMUM_OBSERVATIONS = 3

GOLDEN_FIXTURES: tuple[dict[str, Any], ...] = (
    {"id": "no-response", "scenario": "No response", "observations": [], "expected": {"pLearned": 0.2, "observationCount": 0, "status": "UNASSESSED"}},
    {"id": "one-mcq-correct", "scenario": "One MCQ correct", "observations": [{"correct": True, "questionType": "basic_meaning_mcq"}], "expected": {"pLearned": 0.6, "observationCount": 1, "status": "UNASSESSED"}},
    {"id": "one-mcq-incorrect", "scenario": "One MCQ incorrect", "observations": [{"correct": False, "questionType": "basic_meaning_mcq"}], "expected": {"pLearned": 0.17575757575757578, "observationCount": 1, "status": "UNASSESSED"}},
    {"id": "one-typed-correct", "scenario": "One typed correct", "observations": [{"correct": True, "questionType": "character_to_pinyin_typing"}], "expected": {"pLearned": 0.8380952380952381, "observationCount": 1, "status": "UNASSESSED"}},
    {"id": "one-typed-incorrect", "scenario": "One typed incorrect", "observations": [{"correct": False, "questionType": "character_to_pinyin_typing"}], "expected": {"pLearned": 0.1822784810126582, "observationCount": 1, "status": "UNASSESSED"}},
    {
        "id": "three-mcq-correct",
        "scenario": "Three MCQ correct",
        "observations": [{"correct": True, "questionType": "basic_meaning_mcq"}] * 3,
        "expected": {"pLearned": 0.9773510971786833, "observationCount": 3, "status": "STRONG"},
    },
    {
        "id": "mixed-vector",
        "scenario": "Mixed golden vector",
        "observations": [
            {"correct": True, "questionType": "basic_meaning_mcq"},
            {"correct": True, "questionType": "character_to_pinyin_typing"},
            {"correct": False, "questionType": "context_cloze_mcq"},
            {"correct": True, "questionType": "character_to_pinyin_typing"},
            {"correct": True, "questionType": "context_cloze_mcq"},
        ],
        "expected": {"pLearned": 0.9979619773755845, "observationCount": 5, "status": "STRONG"},
    },
)


def golden_contract_status() -> str:
    return (
        "MATCH"
        if BKT_MODEL_VERSION == GOLDEN_FIXTURE_VERSION
        and bkt_parameter_fingerprint(BKT_CONFIG) == GOLDEN_PARAMETER_FINGERPRINT
        else "MODEL CONTRACT CHANGED"
    )


def _reference_guess_slip(question_type: str | None) -> tuple[float, float]:
    if question_type and question_type.strip().lower() in _REFERENCE_TYPED_TYPES:
        return _GOLDEN_TYPED_GUESS, _GOLDEN_TYPED_SLIP
    return _GOLDEN_MCQ_GUESS, _GOLDEN_MCQ_SLIP


def _reference_trace(observations: Iterable[dict[str, Any]], initial_mastery: float = _GOLDEN_INITIAL_MASTERY) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    mastery = initial_mastery
    for index, observation in enumerate(observations, start=1):
        guess, slip = _reference_guess_slip(observation.get("questionType"))
        if observation["correct"]:
            numerator = mastery * (1.0 - slip)
            denominator = numerator + (1.0 - mastery) * guess
        else:
            numerator = mastery * slip
            denominator = numerator + (1.0 - mastery) * (1.0 - guess)
        posterior = numerator / denominator if denominator else mastery
        resulting = posterior + (1.0 - posterior) * _GOLDEN_LEARN_RATE
        trace.append({
            "step": index,
            "prior": mastery,
            "observation": "Correct" if observation["correct"] else "Incorrect",
            "correct": bool(observation["correct"]),
            "questionType": observation.get("questionType"),
            "guess": guess,
            "slip": slip,
            "posterior": posterior,
            "learningTransition": _GOLDEN_LEARN_RATE,
            "resultingMastery": resulting,
        })
        mastery = resulting
    return trace


def _reference_status(observation_count: int, p_learned: float) -> str:
    if observation_count < _GOLDEN_MINIMUM_OBSERVATIONS:
        return "UNASSESSED"
    return "STRONG" if p_learned >= _GOLDEN_MASTERY_THRESHOLD else "DEVELOPING"


def _production_trace(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    prior = BKT_CONFIG.initial_mastery
    for index, observation in enumerate(observations, start=1):
        guess, slip = guess_slip_for(observation.get("questionType"), BKT_CONFIG)
        if observation["correct"]:
            numerator = prior * (1.0 - slip)
            denominator = numerator + (1.0 - prior) * guess
        else:
            numerator = prior * slip
            denominator = numerator + (1.0 - prior) * (1.0 - guess)
        posterior = numerator / denominator if denominator else prior
        resulting = replay_bkt_typed(
            [(bool(item["correct"]), item.get("questionType")) for item in observations[:index]],
            BKT_CONFIG,
        )
        trace.append({
            "step": index,
            "prior": prior,
            "observation": "Correct" if observation["correct"] else "Incorrect",
            "correct": bool(observation["correct"]),
            "questionType": observation.get("questionType"),
            "guess": guess,
            "slip": slip,
            "posterior": posterior,
            "learningTransition": BKT_CONFIG.learn_rate,
            "resultingMastery": resulting,
        })
        prior = resulting
    return trace


def _golden_actual(observations: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [(bool(item["correct"]), item.get("questionType")) for item in observations]
    p_learned = replay_bkt_typed(pairs, BKT_CONFIG)
    return {
        "pLearned": p_learned,
        "observationCount": len(observations),
        "status": mastery_status(len(observations), p_learned, params=BKT_CONFIG),
        "trace": _production_trace(observations),
    }


def build_golden_report() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for fixture in GOLDEN_FIXTURES:
        observations = list(fixture["observations"])
        expected = dict(fixture["expected"])
        actual = _golden_actual(observations)
        if golden_contract_status() != "MATCH":
            result = "MODEL CONTRACT CHANGED"
        else:
            result = "PASS" if (
                expected["observationCount"] == actual["observationCount"]
                and expected["status"] == actual["status"]
                and abs(float(expected["pLearned"]) - float(actual["pLearned"])) <= GOLDEN_TOLERANCE
            ) else "FAIL"
        checks.append({
            "id": fixture["id"],
            "scenario": fixture["scenario"],
            "input": observations,
            "expected": {**expected, "trace": _reference_trace(observations)},
            "actual": actual,
            "result": result,
            "tolerance": GOLDEN_TOLERANCE,
        })
    return {
        "contractStatus": golden_contract_status(),
        "fixtureVersion": GOLDEN_FIXTURE_VERSION,
        "targetParameterFingerprint": GOLDEN_PARAMETER_FINGERPRINT,
        "checks": checks,
        "summary": {"passed": sum(1 for check in checks if check["result"] == "PASS"), "total": len(checks)},
    }
