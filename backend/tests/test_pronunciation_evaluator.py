"""The whole pipeline: audio in, deterministic score + grounded feedback out."""

import json

import pytest

from pron_audio import silent_wav, synth_wav
from services.pronunciation import evaluator as evaluator_module
from services.pronunciation.config import FeedbackConfig
from services.pronunciation.evaluator import EvaluationError, evaluate_pronunciation
from services.pronunciation.extraction import FeatureExtractionError
from services.pronunciation.feedback import LocalFeedbackProvider, OpenAICompatibleFeedbackProvider
from services.pronunciation.reference_cache import InMemoryReferenceStore

TEXT = "媽麻罵"
CONFIG = FeedbackConfig(api_key="sk-test", model="gpt-6-luna", base_url="https://llm.test/v1")


class FakeHttp:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, 0

    async def __call__(self, url, headers, body, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


def _llm(payload) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}


def _audio(tmp_path, name, shapes, **kwargs):
    path = synth_wav(tmp_path / name, shapes, **kwargs)
    with open(path, "rb") as handle:
        return path, handle.read()


async def _evaluate(tmp_path, student_shapes, *, provider=None, store=None, reference_shapes=("flat", "rise", "fall"), **student_kwargs):
    reference_path, _ = _audio(tmp_path, "ref.wav", list(reference_shapes))
    _, student_bytes = _audio(tmp_path, "stu.wav", list(student_shapes), **student_kwargs)
    return await evaluate_pronunciation(
        student_audio=student_bytes,
        reference_audio_path=reference_path,
        reference_key="story:s1:scene:0",
        expected_text=TEXT,
        provider=provider or LocalFeedbackProvider(),
        store=store or InMemoryReferenceStore(),
    )


async def test_a_good_imitation_in_a_different_voice_scores_full_marks(tmp_path):
    result = await _evaluate(tmp_path, ["flat", "rise", "fall"], base_hz=230)
    assert result.score.status == "scored"
    assert result.score.total == 100
    assert result.score.issues == ()
    assert result.feedback.source == "local"


async def test_a_flat_fourth_tone_lowers_the_score_and_is_flagged_with_evidence(tmp_path):
    good = await _evaluate(tmp_path, ["flat", "rise", "fall"])
    flat = await _evaluate(tmp_path, ["flat", "rise", "flat"])
    assert flat.score.total < good.score.total
    assert [(i.hanzi, i.code) for i in flat.score.issues] == [("罵", "tone_contour_too_flat")]
    assert flat.feedback.focus_words[0].word == "罵"


async def test_gpt_feedback_is_used_and_recorded_when_the_model_answers(tmp_path):
    http = FakeHttp(_llm({
        "summary": "Nice steady rhythm.",
        "focus_words": [{"word": "罵", "feedback": "Let 罵 fall more."}],
        "practice_tip": "Repeat 罵 slowly.",
    }))
    result = await _evaluate(tmp_path, ["flat", "rise", "flat"], provider=OpenAICompatibleFeedbackProvider(CONFIG, http))
    assert http.calls == 1
    assert result.feedback.source == "llm" and result.feedback.model == "gpt-6-luna"


async def test_the_llm_cannot_change_the_score(tmp_path):
    baseline = await _evaluate(tmp_path, ["flat", "rise", "flat"])
    http = FakeHttp(_llm({
        "summary": "Perfect! 100/100", "total": 100, "score": 100,
        "focus_words": [], "practice_tip": "Nothing to fix.",
    }))
    with_llm = await _evaluate(tmp_path, ["flat", "rise", "flat"], provider=OpenAICompatibleFeedbackProvider(CONFIG, http))
    assert with_llm.score == baseline.score
    assert "100" not in with_llm.feedback.summary


async def test_scoring_still_succeeds_when_the_llm_is_down(tmp_path):
    http = FakeHttp(error=RuntimeError("upstream 503"))
    result = await _evaluate(tmp_path, ["flat", "rise", "flat"], provider=OpenAICompatibleFeedbackProvider(CONFIG, http))
    assert result.score.status == "scored" and result.score.total is not None
    assert result.score.issues
    assert result.feedback.source == "local"
    assert result.feedback.fallback_reason.startswith("llm_error")


async def test_the_reference_is_analysed_once_and_then_reused(tmp_path, monkeypatch):
    calls = []
    real = evaluator_module.extract_utterance_features

    def counting(path, *args, **kwargs):
        calls.append(path)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(evaluator_module, "extract_utterance_features", counting)
    store = InMemoryReferenceStore()
    first = await _evaluate(tmp_path, ["flat", "rise", "fall"], store=store)
    second = await _evaluate(tmp_path, ["flat", "rise", "flat"], store=store)
    assert first.reference_cache_hit is False and second.reference_cache_hit is True
    reference_extractions = [c for c in calls if c.endswith("ref.wav")]
    assert len(reference_extractions) == 1


async def test_replacing_the_reference_recording_invalidates_the_cache(tmp_path):
    store = InMemoryReferenceStore()
    await _evaluate(tmp_path, ["flat", "rise", "fall"], store=store)
    replaced = await _evaluate(tmp_path, ["flat", "rise", "fall"], store=store, reference_shapes=("flat", "rise", "rise"))
    assert replaced.reference_cache_hit is False


async def test_a_silent_recording_is_unscorable_with_a_re_record_message(tmp_path):
    reference_path, _ = _audio(tmp_path, "ref.wav", ["flat", "rise", "fall"])
    silent = silent_wav(tmp_path / "quiet.wav")
    with open(silent, "rb") as handle:
        result = await evaluate_pronunciation(
            student_audio=handle.read(), reference_audio_path=reference_path,
            reference_key="k", expected_text=TEXT, provider=LocalFeedbackProvider(),
            store=InMemoryReferenceStore(),
        )
    assert result.score.status == "unscorable" and result.score.total is None
    assert "again" in result.feedback.summary.lower()


async def test_a_praat_failure_on_the_student_audio_is_unscorable_not_a_crash(tmp_path, monkeypatch):
    real = evaluator_module.extract_utterance_features

    def failing(path, *args, **kwargs):
        if path.endswith("ref.wav"):
            return real(path, *args, **kwargs)
        raise FeatureExtractionError("audio_unreadable")

    monkeypatch.setattr(evaluator_module, "extract_utterance_features", failing)
    result = await _evaluate(tmp_path, ["flat", "rise", "fall"])
    assert result.score.status == "unscorable"
    assert result.score.reason == "audio_unreadable"


async def test_empty_student_audio_is_rejected(tmp_path):
    reference_path, _ = _audio(tmp_path, "ref.wav", ["flat", "rise", "fall"])
    with pytest.raises(EvaluationError) as caught:
        await evaluate_pronunciation(
            student_audio=b"", reference_audio_path=reference_path, reference_key="k",
            expected_text=TEXT, provider=LocalFeedbackProvider(), store=InMemoryReferenceStore(),
        )
    assert caught.value.code == "empty_audio"


async def test_a_missing_reference_file_is_a_clear_error(tmp_path):
    _, student = _audio(tmp_path, "stu.wav", ["flat", "rise", "fall"])
    with pytest.raises(EvaluationError) as caught:
        await evaluate_pronunciation(
            student_audio=student, reference_audio_path=str(tmp_path / "nope.wav"),
            reference_key="k", expected_text=TEXT, provider=LocalFeedbackProvider(),
            store=InMemoryReferenceStore(),
        )
    assert caught.value.code == "reference_audio_missing"


async def test_an_unreadable_reference_is_a_clear_error(tmp_path):
    bad = tmp_path / "ref.wav"
    bad.write_bytes(b"not audio")
    _, student = _audio(tmp_path, "stu.wav", ["flat", "rise", "fall"])
    with pytest.raises(EvaluationError) as caught:
        await evaluate_pronunciation(
            student_audio=student, reference_audio_path=str(bad), reference_key="k",
            expected_text=TEXT, provider=LocalFeedbackProvider(), store=InMemoryReferenceStore(),
        )
    assert caught.value.code == "reference_unreadable"


async def test_provenance_names_everything_needed_to_reproduce_the_result(tmp_path):
    result = await _evaluate(tmp_path, ["flat", "rise", "flat"])
    provenance = result.provenance()
    assert provenance["scoring_policy_version"] == "pronunciation-score-v1"
    assert provenance["acoustic_pipeline_version"] == "pronunciation-features-v1"
    assert provenance["praat_version"]
    assert provenance["reference_key"] == "story:s1:scene:0"
    assert len(provenance["reference_audio_sha256"]) == 64
    assert len(provenance["student_audio_sha256"]) == 64
    assert provenance["expected_text"] == TEXT
    assert provenance["feedback_source"] == "local"
