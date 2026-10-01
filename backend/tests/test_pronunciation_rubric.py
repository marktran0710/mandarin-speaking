"""Independent rubrics: transparent, configurable and never an overall score."""

import json
from dataclasses import replace

import pytest

from domain.pronunciation.rubric import RubricPolicy, score_fluency, score_prosody
from domain.pronunciation.types import AlignmentResult, PauseFeature, UtteranceFeatures, build_syllable_features
from pron_audio import synth_wav
from services.pronunciation.config import FeedbackConfig
from services.pronunciation.evaluator import EvaluationError
from services.pronunciation.feedback import OpenAICompatibleFeedbackProvider
from services.pronunciation.presenter import present_evaluation
from services.pronunciation.reference_cache import InMemoryReferenceStore
from services.pronunciation.rubric_evaluator import evaluate_rubric_pronunciation
from services.pronunciation.script import build_expected_syllables
from services.pronunciation.wav2vec2_scoring import analyze_wav2vec2, score_wav2vec2_pronunciation


@pytest.fixture(autouse=True)
def disable_wav2vec2_for_praat_unit_tests(monkeypatch):
    monkeypatch.setenv("PRONUNCIATION_WAV2VEC2_ENABLED", "false")


def features(*, pause_ms=0, leading_ms=0, script="媽麻罵"):
    expected = build_expected_syllables(script)
    syllables = []
    for i, syllable in enumerate(expected):
        start = leading_ms + i * 300 + (pause_ms if i > 0 else 0)
        points = [(start + j * 10, i + j / 10) for j in range(30)]
        syllables.append(build_syllable_features(syllable, start, start + 300, points, intensity_mean=.5))
    return UtteranceFeatures(script, len(syllables) * 300 + pause_ms + leading_ms,
                             tuple(syllables), (PauseFeature(leading_ms + 300, leading_ms + 300 + pause_ms, 0),) if pause_ms else (),
                             len(syllables) * 300, AlignmentResult("test", 1, False))


def test_same_recording_selects_level_five_in_each_praat_dimension():
    ref = features()
    for dimension in (score_fluency(ref, ref, RubricPolicy()), score_prosody(ref, ref, RubricPolicy())):
        assert dimension["score"] == dimension["rubric_level"] == 5
        assert dimension["measurements"] and dimension["criteria"]
        assert "limiting criteria" in dimension["reason"]
        assert "total" not in dimension


def test_extra_pause_lowers_fluency_but_does_not_penalize_prosody():
    ref, student = features(), features(pause_ms=1200)
    fluency = score_fluency(student, ref, RubricPolicy())
    assert fluency["score"] < 5
    assert fluency["measurements"]["pause_count"] == 1
    assert fluency["measurements"]["total_pause_duration"] == 1.2
    assert fluency["measurements"]["articulation_rate"] == pytest.approx(3 / .9)
    assert score_prosody(student, ref, RubricPolicy())["score"] == 5


def test_native_pause_is_not_an_unnecessary_pause():
    ref = features(pause_ms=600)
    result = score_fluency(ref, ref, RubricPolicy())
    assert result["measurements"]["pause_count"] == 1
    assert result["measurements"]["unnecessary_pause_count"] == 0
    assert result["score"] == 5


def test_leading_silence_does_not_lower_fluency():
    ref, student = features(), features(leading_ms=3000)
    result = score_fluency(student, ref, RubricPolicy())
    assert result["measurements"]["total_speech_duration"] == 3.9
    assert result["measurements"]["speaking_duration"] == .9
    assert result["score"] == 5


def test_policy_overrides_change_the_selected_level(monkeypatch):
    ref, student = features(), features(pause_ms=1200)
    original = score_fluency(student, ref, RubricPolicy())
    limits = {key: [10, 11, 12, 13] for key in RubricPolicy().fluency_limits}
    monkeypatch.setenv("PRONUNCIATION_RUBRIC_POLICY_JSON", json.dumps({"fluency_limits": limits}))
    policy = RubricPolicy.from_env()
    assert score_fluency(student, ref, policy)["score"] == 5 > original["score"]
    assert policy.to_dict()["fluency_limits"] == limits


@pytest.mark.parametrize("override", [
    {"pitch_distance_scale_semitones": 0}, {"pitch_range_floor_semitones": float("nan")},
    {"min_alignment_confidence": 2}, {"pause_duration_tolerance_seconds": -.1},
    {"fluency_limits": {}}, {"prosody_limits": {"rhythm_similarity": [1, 2, 3, 4]}},
])
def test_invalid_thresholds_are_rejected(override):
    with pytest.raises(ValueError):
        RubricPolicy(**override)


@pytest.mark.parametrize("override", [
    {"version": "teacher-validated"},
    {"validation_status": "teacher-validated"},
])
def test_configuration_cannot_label_thresholds_validated_without_evidence(override):
    with pytest.raises(ValueError, match="calibrat|version"):
        RubricPolicy(**override)


def test_weak_alignment_returns_unavailable_instead_of_full_marks():
    ref = features()
    weak = replace(ref, alignment=AlignmentResult("equal", .25, True))
    for dimension in (score_fluency(weak, ref, RubricPolicy()), score_prosody(weak, ref, RubricPolicy())):
        assert dimension["score"] is None
        assert "confidence" in dimension["reason"]


def test_insufficient_pitch_keeps_prosody_unavailable():
    ref = features()
    student = replace(ref, syllables=tuple(replace(s, f0_points=()) for s in ref.syllables))
    assert score_prosody(student, ref, RubricPolicy())["score"] is None
    assert score_fluency(student, ref, RubricPolicy())["score"] == 5


def test_wav2vec2_scores_initial_final_and_praat_tone_without_persisting_vectors(monkeypatch, tmp_path):
    class FakeEmbedder:
        model_name = "test-wav2vec2"

        def __init__(self, **kwargs):
            pass

        def frame_embeddings(self, path):
            times = __import__("numpy").arange(0, 1.0, 0.02, dtype=float)
            vectors = __import__("numpy").stack([__import__("numpy").sin(times * 3), __import__("numpy").cos(times * 2)], axis=1)
            return times, vectors

    import services.pronunciation.wav2vec2_scoring as wav2vec_module
    monkeypatch.setenv("PRONUNCIATION_WAV2VEC2_ENABLED", "true")
    monkeypatch.setattr(wav2vec_module, "SyllableEmbedder", FakeEmbedder)
    ref = features()
    evidence = analyze_wav2vec2(
        student_audio_path=str(tmp_path / "student.wav"), reference_audio_path=str(tmp_path / "reference.wav"),
        student=ref, reference=ref, policy=RubricPolicy(),
    )
    result = score_wav2vec2_pronunciation(evidence, RubricPolicy())
    assert result["score"] == 5
    assert result["pronunciation_errors"] == []
    assert result["tone_errors"] == []
    assert evidence["model"] == "test-wav2vec2"
    assert all("vector" not in key for key in evidence)
    assert all("vectors" not in item for item in evidence["syllables"])


def test_wav2vec2_thresholds_create_segmental_and_tone_errors():
    policy = RubricPolicy()
    evidence = {
        "initial_similarity": .5, "final_similarity": .95, "tone_similarity": .2,
        "syllables": [{"index": 0, "hanzi": "媽", "pinyin": "ma1",
                        "initial_similarity": .5, "final_similarity": .95,
                        "tone_similarity": .2, "tone_flags": ["tone_direction_mismatch"]}],
    }
    result = score_wav2vec2_pronunciation(evidence, policy)
    assert result["score"] == 1
    assert result["pronunciation_errors"][0]["kind"] == "initial"
    assert result["tone_errors"][0]["flags"] == ["tone_direction_mismatch"]


async def provider_http(url, headers, body, timeout):
    payload = json.loads(body["messages"][1]["content"])
    assert payload["pronunciation"]["score"] is None
    assert "score" not in payload and "total" not in payload
    assert "no audio" in body["messages"][0]["content"]
    assert all(not isinstance(value, list) for dimension in (payload["fluency"], payload["prosody"])
               for value in dimension["measurements"].values())
    assert "pitch_contour_samples" not in payload["prosody"]["measurements"]
    return {"choices": [{"message": {"content": json.dumps({
        "summary": "Practise the sentence with the reference.",
        "pronunciation_feedback": "The pronunciation model is not available for this recording.",
        "fluency_feedback": "Keep each phrase flowing.",
        "prosody_feedback": "Follow the sentence pitch movement and rhythm.",
        "practice_tip": "Listen, then repeat one phrase at a time.",
        "accuracy_score": 5, "overall_score": 100,  # ignored; model cannot add scores
    })}}]}


async def evaluate(tmp_path, *, http=provider_http, base_hz=230):
    ref = synth_wav(tmp_path / "ref.wav", ["flat", "rise", "fall"])
    student = synth_wav(tmp_path / "student.wav", ["flat", "rise", "fall"], base_hz=base_hz)
    return await evaluate_rubric_pronunciation(
        student_audio=open(student, "rb").read(), reference_audio_path=ref,
        expected_text="媽麻罵", reference_key="test", store=InMemoryReferenceStore(),
        provider=OpenAICompatibleFeedbackProvider(FeedbackConfig(api_key="test"), http),
    )


async def test_real_praat_different_voice_and_luna_preserve_separate_scores(tmp_path):
    result = await evaluate(tmp_path)
    body = present_evaluation(result, include_debug=True)
    assert "score" not in body
    assert body["dimensions"]["pronunciation"]["score"] is None
    assert body["dimensions"]["fluency"]["score"] == 5
    assert body["dimensions"]["prosody"]["score"] == 5
    assert body["debug"]["policy"]["validation_status"] == "uncalibrated_engineering_defaults"
    assert body["feedback"]["model"] == "gpt-6-luna"
    assert "debug" not in present_evaluation(result, include_debug=False)


async def test_luna_numeric_score_claims_are_rejected_without_local_feedback(tmp_path):
    async def bad_http(*args):
        return {"choices": [{"message": {"content": json.dumps({
            "summary": "You scored 100/100.", "fluency_feedback": "Good.",
            "prosody_feedback": "Good.", "practice_tip": "Repeat.",
        })}}]}
    with pytest.raises(EvaluationError, match="No local feedback"):
        await evaluate(tmp_path, http=bad_http)


async def test_luna_cannot_claim_lexical_accuracy_while_pronunciation_is_unavailable(tmp_path):
    async def bad_http(*args):
        return {"choices": [{"message": {"content": json.dumps({
            "summary": "The sentence flows naturally.",
            "pronunciation_feedback": "The tones are clear.",
            "fluency_feedback": "There are no long pauses.",
            "prosody_feedback": "The tones are clear.",
            "practice_tip": "Repeat after the reference.",
        })}}]}
    with pytest.raises(EvaluationError, match="No local feedback"):
        await evaluate(tmp_path, http=bad_http)


async def test_luna_failure_has_no_success_or_fake_accuracy(tmp_path):
    async def failed_http(*args):
        raise TimeoutError()
    with pytest.raises(EvaluationError) as error:
        await evaluate(tmp_path, http=failed_http)
    assert error.value.code == "llm_timeout"
