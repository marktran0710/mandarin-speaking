"""Student-friendly feedback on a finished, deterministic pronunciation score.

The language model here is an explanation layer only. It is handed the score
and the ranked issues the scoring policy already produced - never audio, never
pitch arrays - and whatever it returns is sanitised against that evidence:
score claims are discarded, words it was not given evidence for are dropped,
and it can invent no error. The interactive API requires model feedback and
reports failures explicitly. Offline callers may opt into deterministic local
feedback when the model is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable, Optional, Protocol

import httpx

from domain.pronunciation.compare import (
    FLAG_DIRECTION,
    FLAG_LONG,
    FLAG_NARROW,
    FLAG_NOT_LEVEL,
    FLAG_SHAPE,
    FLAG_SHORT,
    FLAG_TOO_FLAT,
)
from domain.pronunciation.scoring import STATUS_SCORED, Issue, PronunciationScore
from services.pronunciation.config import FeedbackConfig

logger = logging.getLogger(__name__)

MAX_ITEM_CHARS = 320

#: What each flag means, handed to the model so it explains rather than guesses.
ISSUE_MEANINGS = {
    FLAG_TOO_FLAT: "The pitch stayed flatter than the reference; the tone needed a clearer movement.",
    FLAG_NOT_LEVEL: "The reference keeps this tone level but the pitch moved up or down.",
    FLAG_DIRECTION: "The pitch moved in a different direction than the reference.",
    FLAG_NARROW: "The pitch moved the right way but not as far as the reference.",
    FLAG_SHAPE: "The pitch moved in the same direction as the reference but its shape was different.",
    FLAG_LONG: "This syllable was noticeably longer than the rest, compared with the reference.",
    FLAG_SHORT: "This syllable was noticeably shorter than the rest, compared with the reference.",
}

_DIRECTION_WORDS = {
    "fall": "falling", "rise": "rising", "dip": "dipping", "flat": "level", "other": "uneven",
}
_DIRECTION_VERBS = {
    "fall": "fall", "rise": "rise", "dip": "dip down and come back up", "flat": "stay level",
}

#: Wording bands for the local summary. Presentation only - never a score input.
_CLEAR_FROM = 85
_MOSTLY_CLEAR_FROM = 65

_SCORE_CLAIM = re.compile(
    r"\d{1,3}\s*(?:/\s*\d{1,3}|%|percent|points?|分|điểm)"
    r"|(?:score|scored|marks?|分數|điểm)\W{0,12}\d",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = """\
You write short pronunciation feedback for a beginner learner of Mandarin.
You are given the result of an automatic acoustic analysis (pitch contour and \
timing compared with a teacher recording). The numeric score and every issue \
were produced by fixed rules; you only explain them.

Rules:
- Return only JSON: {"summary": string, "focus_words": [{"word": string, "feedback": string}], "practice_tip": string}
- Never change, recompute or restate the numeric score. Do not write any number out of 100 or any percentage.
- Only mention syllables that appear in "issues", using the syllable's hanzi as "word". Never claim an error that is not listed. If "issues" is empty, focus_words must be [].
- Mention at most 3 words, most important first.
- Evidence "strong" may be stated plainly, "moderate" gently, and "weak" must be hedged (for example "may" or "might").
- Do not comment on anything listed in "not_measured".
- Be encouraging and concrete, at most two short sentences per item. Do not use technical terms such as F0, Hz, semitone or Praat.
- Write in {language}. Keep Chinese characters and pinyin exactly as given.
"""


class FeedbackRejected(Exception):
    """The model's reply could not be used; the reason is a short stable code."""


@dataclass(frozen=True)
class FocusWord:
    word: str
    feedback: str

    def to_dict(self) -> dict[str, str]:
        return {"word": self.word, "feedback": self.feedback}


@dataclass(frozen=True)
class PronunciationFeedback:
    summary: str
    focus_words: tuple[FocusWord, ...]
    practice_tip: str
    #: "llm" or "local".
    source: str
    model: Optional[str] = None
    fallback_reason: Optional[str] = None
    #: Sanitiser actions taken on the model's reply, for provenance.
    adjustments: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "focus_words": [w.to_dict() for w in self.focus_words],
            "practice_tip": self.practice_tip,
            "source": self.source,
            "model": self.model,
            "fallback_reason": self.fallback_reason,
            "adjustments": list(self.adjustments),
        }


@dataclass(frozen=True)
class FeedbackInput:
    sentence: str
    score: PronunciationScore
    max_issues: int = 3

    @property
    def issues(self) -> tuple[Issue, ...]:
        """Most important first, one per syllable, capped."""
        seen: set[int] = set()
        chosen: list[Issue] = []
        for issue in self.score.issues:
            if issue.syllable_index in seen:
                continue
            seen.add(issue.syllable_index)
            chosen.append(issue)
        return tuple(chosen[: self.max_issues])

    def to_llm_payload(self) -> dict[str, Any]:
        score: dict[str, Any] = {"total": self.score.total}
        for dimension in self.score.dimensions:
            if dimension.points is not None:
                score[dimension.key] = {"points": dimension.points, "out_of": dimension.max_points}
        return {
            "sentence": self.sentence,
            "score": score,
            "not_measured": [d.key for d in self.score.dimensions if d.points is None],
            "issues": [
                {
                    "syllable": issue.hanzi,
                    "in_word": issue.word,
                    "pinyin": issue.pinyin,
                    "expected_tone": issue.expected_tone,
                    "severity": issue.severity,
                    "evidence": issue.evidence,
                    "issue": issue.code,
                    "issue_meaning": ISSUE_MEANINGS.get(issue.code, ""),
                    "tone_similarity": issue.tone_similarity,
                    "reference_pitch": issue.reference_direction,
                    "student_pitch": issue.student_direction,
                }
                for issue in self.issues
            ],
        }


def build_feedback_input(sentence: str, score: PronunciationScore, *, max_issues: int = 3) -> FeedbackInput:
    return FeedbackInput(sentence=sentence, score=score, max_issues=max_issues)


class PronunciationFeedbackProvider(Protocol):
    async def generate_feedback(self, feedback_input: FeedbackInput) -> PronunciationFeedback: ...


# ── deterministic local feedback ─────────────────────────────────────────

_UNSCORABLE_MESSAGES = {
    "no_measurable_tones": (
        "We could not measure enough pitch in this recording. "
        "Please record again, closer to the microphone and somewhere quiet."
    ),
    "speaking_rate_implausible": (
        "This recording did not sound like the whole sentence. "
        "Please record again and say the full sentence."
    ),
    "recording_unusable": (
        "We could not hear enough clear speech in this recording. "
        "Please record again in a quiet place."
    ),
    "no_voiced_speech": (
        "We could not hear enough clear speech in this recording. "
        "Please record again in a quiet place."
    ),
    "audio_unreadable": "We could not read this recording. Please record again.",
    "alignment_failed": "We could not match this recording to the sentence. Please record again and say the full sentence.",
}


def _local_focus_text(issue: Issue) -> str:
    label = f"{issue.hanzi} ({issue.pinyin})"
    ref = _DIRECTION_WORDS.get(issue.reference_direction, "")
    stu = _DIRECTION_WORDS.get(issue.student_direction, "")
    if issue.code == FLAG_TOO_FLAT:
        verb = _DIRECTION_VERBS.get(issue.reference_direction, "move")
        text = f"{label} stayed flatter than the reference. Let your pitch {verb} more clearly."
    elif issue.code == FLAG_NOT_LEVEL:
        text = f"{label} moved up and down more than the reference. Try to keep your pitch steady and level."
    elif issue.code == FLAG_DIRECTION:
        text = (
            f"{label} went a different way than the reference (reference: {ref}, yours: {stu}). "
            "Listen to the model and copy its movement."
        )
    elif issue.code == FLAG_NARROW:
        text = f"{label} moved the right way but not far enough. Make the movement a little bigger."
    elif issue.code == FLAG_SHAPE:
        text = (
            f"{label} moved the same way as the reference, but its pitch shape was a little different. "
            "Listen to the model and copy the shape."
        )
    elif issue.code == FLAG_LONG:
        text = f"{label} was noticeably longer than the rest of the sentence compared with the reference. Keep your syllables more even."
    elif issue.code == FLAG_SHORT:
        text = f"{label} was noticeably shorter than the rest of the sentence compared with the reference. Give it a little more time."
    else:
        text = f"{label} differed from the reference."
    if issue.evidence == "weak":
        text += " (This is uncertain - listen and compare it yourself.)"
    return text


def _local_summary(score: PronunciationScore) -> str:
    if score.status != STATUS_SCORED:
        return _UNSCORABLE_MESSAGES.get(
            score.reason or "", "We could not score this recording. Please record again."
        )
    total = score.total or 0
    if total >= _CLEAR_FROM:
        return "Your pronunciation was clear and close to the reference."
    if total >= _MOSTLY_CLEAR_FROM:
        return "Your pronunciation was mostly clear, with a few places to sharpen."
    return "Several tones and timing patterns differed from the reference. Let's work on them step by step."


def _local_tip(issues: tuple[Issue, ...], score: PronunciationScore) -> str:
    if score.status != STATUS_SCORED:
        return "Record the whole sentence again in a quiet place."
    if issues:
        return f"Practice {issues[0].word} slowly first, then say the whole sentence at a natural speed."
    return "Keep practising: say the whole sentence again at a natural speed."


class LocalFeedbackProvider:
    """Always available; wording is a pure function of the evidence."""

    async def generate_feedback(self, feedback_input: FeedbackInput) -> PronunciationFeedback:
        score = feedback_input.score
        issues = feedback_input.issues if score.status == STATUS_SCORED else ()
        return PronunciationFeedback(
            summary=_local_summary(score),
            focus_words=tuple(FocusWord(issue.hanzi, _local_focus_text(issue)) for issue in issues),
            practice_tip=_local_tip(issues, score),
            source="local",
        )


# ── LLM provider ─────────────────────────────────────────────────────────

HttpPost = Callable[[str, dict, dict, float], Awaitable[dict]]


async def _httpx_post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=body)
    if response.status_code != 200:
        # The body may quote part of the key, so only the status leaves this function.
        logger.warning("Pronunciation feedback model returned HTTP %s", response.status_code)
        raise FeedbackRejected(f"llm_http_{response.status_code}")
    return response.json()


def _strip_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _clean_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or _SCORE_CLAIM.search(text):
        return None
    return text[:MAX_ITEM_CHARS]


def sanitize_reply(reply: Any, feedback_input: FeedbackInput, local: PronunciationFeedback, model: str) -> PronunciationFeedback:
    """Keep only what the evidence supports from a model reply.

    Anything dropped or replaced is recorded in ``adjustments``. The numeric
    score is not part of the result type at all, so it cannot be altered here.
    """
    if not isinstance(reply, dict):
        raise FeedbackRejected("reply_not_an_object")

    adjustments: list[str] = []
    summary = _clean_text(reply.get("summary"))
    if summary is None:
        if not isinstance(reply.get("summary"), str) or not reply["summary"].strip():
            raise FeedbackRejected("missing_summary")
        summary = local.summary
        adjustments.append("summary_replaced")

    tip = _clean_text(reply.get("practice_tip"))
    if tip is None:
        tip = local.practice_tip
        adjustments.append("practice_tip_replaced")

    allowed = {issue.hanzi for issue in feedback_input.issues}
    focus: list[FocusWord] = []
    raw_focus = reply.get("focus_words")
    for item in raw_focus if isinstance(raw_focus, list) else []:
        word = item.get("word") if isinstance(item, dict) else None
        text = _clean_text(item.get("feedback")) if isinstance(item, dict) else None
        if not isinstance(word, str) or word not in allowed:
            adjustments.append(f"focus_word_dropped:{word}")
            continue
        if text is None or any(existing.word == word for existing in focus):
            adjustments.append(f"focus_word_dropped:{word}")
            continue
        focus.append(FocusWord(word, text))
    if len(focus) > feedback_input.max_issues:
        adjustments.append("focus_words_truncated")
        focus = focus[: feedback_input.max_issues]

    return PronunciationFeedback(
        summary=summary,
        focus_words=tuple(focus),
        practice_tip=tip,
        source="llm",
        model=model,
        adjustments=tuple(adjustments),
    )


class OpenAICompatibleFeedbackProvider:
    def __init__(self, config: FeedbackConfig, http_post: HttpPost = _httpx_post) -> None:
        self._config = config
        self._http_post = http_post

    async def generate_feedback(self, feedback_input: FeedbackInput) -> PronunciationFeedback:
        config = self._config
        body = {
            "model": config.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT.replace("{language}", config.language)},
                {"role": "user", "content": json.dumps(feedback_input.to_llm_payload(), ensure_ascii=False)},
            ],
        }
        reply = await self._http_post(
            f"{config.base_url}/chat/completions",
            {"Authorization": f"Bearer {config.api_key}"},
            body,
            config.timeout_seconds,
        )
        try:
            content = reply["choices"][0]["message"]["content"]
            data = json.loads(_strip_fence(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise FeedbackRejected("invalid_reply") from exc
        local = await LocalFeedbackProvider().generate_feedback(feedback_input)
        return sanitize_reply(data, feedback_input, local, config.model)


def build_feedback_provider(config: Optional[FeedbackConfig] = None) -> PronunciationFeedbackProvider:
    config = config or FeedbackConfig.from_env()
    return OpenAICompatibleFeedbackProvider(config) if config.enabled else LocalFeedbackProvider()


async def generate_feedback_safely(
    provider: PronunciationFeedbackProvider, feedback_input: FeedbackInput, *, require_llm: bool = False
) -> PronunciationFeedback:
    """Use explicit failures when LLM feedback is required; otherwise allow fallback."""
    local = await LocalFeedbackProvider().generate_feedback(feedback_input)
    if require_llm and feedback_input.score.status != STATUS_SCORED:
        raise FeedbackRejected("recording_unscorable")
    if require_llm and isinstance(provider, LocalFeedbackProvider):
        raise FeedbackRejected("llm_not_configured")
    if feedback_input.score.status != STATUS_SCORED or isinstance(provider, LocalFeedbackProvider):
        return local  # nothing to coach on, or no model configured
    try:
        feedback = await provider.generate_feedback(feedback_input)
        if require_llm and (
            feedback.source != "llm"
            or any(action.endswith("_replaced") for action in feedback.adjustments)
        ):
            raise FeedbackRejected("llm_reply_requires_local_feedback")
        return feedback
    except FeedbackRejected as exc:
        reason = str(exc) or "llm_rejected"
    except asyncio.TimeoutError:
        reason = "llm_timeout"
    except httpx.TimeoutException:
        reason = "llm_timeout"
    except Exception as exc:  # the score must survive any provider failure
        logger.warning("Pronunciation feedback provider failed: %s", type(exc).__name__)
        reason = f"llm_error_{type(exc).__name__}"
    if require_llm:
        raise FeedbackRejected(reason)
    return replace(local, fallback_reason=reason)
