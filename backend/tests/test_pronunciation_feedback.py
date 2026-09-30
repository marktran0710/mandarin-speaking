"""GPT feedback is an explanation layer: grounded, bounded, never the score."""

import asyncio
import json

import pytest

from domain.pronunciation.compare import compare_utterances
from domain.pronunciation.scoring import score_comparison
from pron_fixtures import make_utterance
from services.pronunciation.config import FeedbackConfig
from services.pronunciation.feedback import (
    FeedbackRejected,
    LocalFeedbackProvider,
    OpenAICompatibleFeedbackProvider,
    build_feedback_input,
    generate_feedback_safely,
)

SENTENCE = "友美妳這"


def _score(student_shapes, ref_shapes=("fall", "rise", "dip", "flat"), **kwargs):
    reference = make_utterance(list(ref_shapes))
    student = make_utterance(list(student_shapes), **kwargs)
    return score_comparison(compare_utterances(student, reference))


FLAT_T4 = _score(["flat", "rise", "dip", "flat"])
PERFECT = _score(["fall", "rise", "dip", "flat"])
CONFIG = FeedbackConfig(api_key="sk-test", model="gpt-6-luna", base_url="https://llm.test/v1")


def _llm_reply(payload) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}


class FakeHttp:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": body})
        if self.error:
            raise self.error
        return self.reply


def _provider(http):
    return OpenAICompatibleFeedbackProvider(CONFIG, http_post=http)


# ── what the model is allowed to see ─────────────────────────────────────

def test_the_llm_receives_only_score_and_evidence_never_audio_or_pitch_arrays():
    payload = build_feedback_input(SENTENCE, FLAT_T4).to_llm_payload()
    assert payload["sentence"] == SENTENCE
    assert payload["score"]["total"] == FLAT_T4.total
    assert payload["score"]["tone"] == {"points": 50, "out_of": 67}
    assert "f0_points" not in json.dumps(payload) and "audio" not in json.dumps(payload)
    issue = payload["issues"][0]
    assert issue["syllable"] == "友" and issue["pinyin"] == "x4"
    assert issue["issue"] == "tone_contour_too_flat"
    assert issue["reference_pitch"] == "fall" and issue["student_pitch"] == "flat"
    assert issue["evidence"] == "strong"


def test_unmeasured_dimensions_are_declared_so_the_model_does_not_comment_on_them():
    payload = build_feedback_input(SENTENCE, FLAT_T4).to_llm_payload()
    assert set(payload["not_measured"]) == {"segmental", "intelligibility"}


def test_at_most_three_issues_are_sent_most_important_first():
    many = _score(["rise", "fall", "flat", "rise"])
    assert len(many.issues) > 3
    payload = build_feedback_input(SENTENCE, many).to_llm_payload()
    assert len(payload["issues"]) == 3
    assert [i["severity"] for i in payload["issues"]] == ["high", "high", "high"]


# ── provider behaviour ───────────────────────────────────────────────────

async def test_a_valid_reply_becomes_llm_feedback_with_the_model_recorded():
    http = FakeHttp(_llm_reply({
        "summary": "Your rhythm was steady and your rises were clear.",
        "focus_words": [{"word": "友", "feedback": "Let the pitch fall more clearly on 友."}],
        "practice_tip": "Say 友美 slowly, then at normal speed.",
    }))
    feedback = await generate_feedback_safely(_provider(http), build_feedback_input(SENTENCE, FLAT_T4))
    assert feedback.source == "llm" and feedback.model == "gpt-6-luna"
    assert feedback.fallback_reason is None
    assert feedback.focus_words[0].word == "友"
    body = http.calls[0]["body"]
    assert body["model"] == "gpt-6-luna"
    assert http.calls[0]["url"] == "https://llm.test/v1/chat/completions"
    assert http.calls[0]["headers"]["Authorization"] == "Bearer sk-test"
    assert body["response_format"] == {"type": "json_object"}


async def test_the_llm_cannot_change_the_score_even_if_it_tries():
    http = FakeHttp(_llm_reply({
        "summary": "Great job, you scored 99/100!",
        "total": 99, "score": {"total": 99},
        "focus_words": [], "practice_tip": "Keep going.",
    }))
    feedback = await generate_feedback_safely(_provider(http), build_feedback_input(SENTENCE, FLAT_T4))
    assert not hasattr(feedback, "total") and not hasattr(feedback, "score")
    assert "99" not in feedback.summary  # the score claim is discarded
    assert feedback.summary  # replaced by the deterministic summary, not blank


async def test_a_focus_word_that_is_not_in_the_evidence_is_dropped():
    http = FakeHttp(_llm_reply({
        "summary": "Clear overall.",
        "focus_words": [
            {"word": "友", "feedback": "Fall more clearly."},
            {"word": "週", "feedback": "Your 週 was wrong."},
        ],
        "practice_tip": "Practice slowly.",
    }))
    feedback = await generate_feedback_safely(_provider(http), build_feedback_input(SENTENCE, FLAT_T4))
    assert [w.word for w in feedback.focus_words] == ["友"]


async def test_the_llm_cannot_invent_errors_when_the_evidence_shows_none():
    http = FakeHttp(_llm_reply({
        "summary": "Clear overall.",
        "focus_words": [{"word": "友", "feedback": "Your tone was off."}],
        "practice_tip": "Keep practising.",
    }))
    feedback = await generate_feedback_safely(_provider(http), build_feedback_input(SENTENCE, PERFECT))
    assert feedback.focus_words == ()


async def test_more_than_three_focus_words_are_cut_to_three():
    many = _score(["rise", "fall", "flat", "rise"])
    words = [{"word": ch, "feedback": "Try again."} for ch in "友美妳這"]
    http = FakeHttp(_llm_reply({"summary": "Ok.", "focus_words": words, "practice_tip": "Slow."}))
    feedback = await generate_feedback_safely(_provider(http), build_feedback_input(SENTENCE, many))
    assert len(feedback.focus_words) == 3


# ── failure: the LLM is an enhancement, never a single point of failure ──

@pytest.mark.parametrize(
    "http",
    [
        FakeHttp(error=RuntimeError("503 upstream")),
        FakeHttp(error=asyncio.TimeoutError()),
        FakeHttp(reply={"choices": [{"message": {"content": "not json at all"}}]}),
        FakeHttp(reply={"unexpected": "shape"}),
        FakeHttp(reply=_llm_reply({"focus_words": []})),  # no summary
    ],
)
async def test_any_llm_failure_falls_back_to_local_feedback(http):
    feedback = await generate_feedback_safely(_provider(http), build_feedback_input(SENTENCE, FLAT_T4))
    assert feedback.source == "local"
    assert feedback.fallback_reason
    assert feedback.summary and feedback.practice_tip
    assert [w.word for w in feedback.focus_words] == ["友"]


async def test_local_feedback_is_deterministic_and_cites_the_measured_difference():
    local = LocalFeedbackProvider()
    feedback_input = build_feedback_input(SENTENCE, FLAT_T4)
    first = await local.generate_feedback(feedback_input)
    assert first == await local.generate_feedback(feedback_input)
    assert first.source == "local" and first.model is None
    assert "flat" in first.focus_words[0].feedback.lower()


async def test_an_unscorable_recording_gets_a_re_record_message_not_coaching():
    unscorable = _score(["neutral", "neutral", "neutral", "neutral"], ref_shapes=("neutral",) * 4)
    feedback = await LocalFeedbackProvider().generate_feedback(build_feedback_input(SENTENCE, unscorable))
    assert feedback.focus_words == ()
    assert "again" in feedback.summary.lower()


# ── configuration ────────────────────────────────────────────────────────

def test_config_defaults_to_the_requested_model_and_reuses_the_openai_key():
    config = FeedbackConfig.from_env({"OPENAI_API_KEY": "sk-abc"})
    assert config.model == "gpt-6-luna"
    assert config.api_key == "sk-abc"
    assert config.enabled


def test_a_dedicated_key_and_model_override_the_defaults():
    config = FeedbackConfig.from_env({
        "OPENAI_API_KEY": "sk-abc",
        "PRONUNCIATION_FEEDBACK_API_KEY": "sk-own",
        "PRONUNCIATION_FEEDBACK_MODEL": "other-model",
        "PRONUNCIATION_FEEDBACK_BASE_URL": "https://proxy.test/v1/",
    })
    assert (config.api_key, config.model, config.base_url) == ("sk-own", "other-model", "https://proxy.test/v1")


def test_without_a_key_the_llm_is_disabled():
    assert FeedbackConfig.from_env({}).enabled is False


@pytest.mark.parametrize("provider,reason", [
    (LocalFeedbackProvider(), "llm_not_configured"),
    (_provider(FakeHttp(error=asyncio.TimeoutError())), "llm_timeout"),
    (_provider(FakeHttp(reply={"unexpected": "shape"})), "invalid_reply"),
    (_provider(FakeHttp(reply=_llm_reply({"summary": "99/100", "practice_tip": "Go."}))), "llm_reply_requires_local_feedback"),
])
async def test_required_llm_never_substitutes_local_feedback(provider, reason):
    with pytest.raises(FeedbackRejected, match=reason):
        await generate_feedback_safely(provider, build_feedback_input(SENTENCE, FLAT_T4), require_llm=True)


async def test_required_llm_accepts_valid_model_feedback():
    provider = _provider(FakeHttp(reply=_llm_reply({"summary": "Clear overall.", "focus_words": [], "practice_tip": "Repeat slowly."})))
    feedback = await generate_feedback_safely(provider, build_feedback_input(SENTENCE, PERFECT), require_llm=True)
    assert feedback.source == "llm" and feedback.model == "gpt-6-luna"
