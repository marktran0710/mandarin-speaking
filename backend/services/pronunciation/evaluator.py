"""One pronunciation evaluation, end to end.

    known script -> reference features (cached) + student features (Praat)
                 -> deterministic comparison -> deterministic score
                 -> grounded feedback (LLM, with local fallback)

The score is finished before any language model is asked anything, so the model
can only ever explain it.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

from domain.pronunciation.compare import ReferenceMismatchError, UtteranceComparison, compare_utterances
from domain.pronunciation.policy import PronunciationScoringPolicy
from domain.pronunciation.scoring import PronunciationScore, score_comparison, unscorable_score
from domain.pronunciation.types import UtteranceFeatures
from services.content.verification import assess_recording_quality
from services.pronunciation.config import FeedbackConfig
from services.pronunciation.extraction import PIPELINE_VERSION, FeatureExtractionError, extract_utterance_features
from services.pronunciation.feedback import (
    PronunciationFeedback,
    PronunciationFeedbackProvider,
    build_feedback_input,
    build_feedback_provider,
    generate_feedback_safely,
)
from services.pronunciation.reference_cache import ReferenceFeatureStore, default_reference_store
from services.pronunciation.script import build_expected_syllables

REASON_RECORDING_UNUSABLE = "recording_unusable"


class EvaluationError(Exception):
    """The request cannot be evaluated; ``code`` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class PronunciationEvaluation:
    expected_text: str
    reference_key: str
    score: PronunciationScore
    comparison: Optional[UtteranceComparison]
    student_features: Optional[UtteranceFeatures]
    reference_features: UtteranceFeatures
    feedback: PronunciationFeedback
    policy: PronunciationScoringPolicy
    reference_cache_hit: bool
    reference_audio_sha256: str
    student_audio_sha256: str
    #: Recording-quality preflight details when it rejected the audio.
    quality: Optional[dict] = None

    def provenance(self) -> dict[str, Any]:
        """Everything needed to reproduce or audit this result."""
        reference = self.reference_features.provenance
        return {
            "scoring_policy_version": self.policy.version,
            "acoustic_pipeline_version": reference.get("pipeline_version", PIPELINE_VERSION),
            "praat_version": reference.get("praat_version"),
            "pitch_tracker": reference.get("pitch_tracker"),
            "aligner": reference.get("aligner"),
            "reference_key": self.reference_key,
            "reference_audio_sha256": self.reference_audio_sha256,
            "student_audio_sha256": self.student_audio_sha256,
            "expected_text": self.expected_text,
            "feedback_source": self.feedback.source,
            "feedback_model": self.feedback.model,
            "feedback_fallback_reason": self.feedback.fallback_reason,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reference_features(
    reference_audio_path: str,
    reference_key: str,
    expected_text: str,
    expected,
    store: ReferenceFeatureStore,
) -> tuple[UtteranceFeatures, bool, str]:
    try:
        with open(reference_audio_path, "rb") as handle:
            audio_sha = _sha256(handle.read())
    except OSError as exc:
        raise EvaluationError("reference_audio_missing", "The reference recording is not available.") from exc

    key = (reference_key, audio_sha, _sha256(expected_text.encode("utf-8")), PIPELINE_VERSION)
    cached = store.get(key)
    if cached is not None:
        return cached, True, audio_sha
    try:
        features = extract_utterance_features(reference_audio_path, expected_text, expected=expected)
    except FeatureExtractionError as exc:
        raise EvaluationError("reference_unreadable", f"The reference recording could not be analysed ({exc.code}).") from exc
    store.put(key, features)
    return features, False, audio_sha


def _extract_student(audio: bytes, expected_text: str, expected) -> UtteranceFeatures:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
        handle.write(audio)
        path = handle.name
    try:
        return extract_utterance_features(path, expected_text, expected=expected)
    finally:
        if os.path.exists(path):
            os.unlink(path)


async def evaluate_pronunciation(
    *,
    student_audio: bytes,
    reference_audio_path: str,
    reference_key: str,
    expected_text: str,
    policy: Optional[PronunciationScoringPolicy] = None,
    provider: Optional[PronunciationFeedbackProvider] = None,
    store: Optional[ReferenceFeatureStore] = None,
) -> PronunciationEvaluation:
    if not student_audio:
        raise EvaluationError("empty_audio", "No audio was received.")
    expected = build_expected_syllables(expected_text)
    if not expected:
        raise EvaluationError("no_syllables", "The script has no Chinese syllables to evaluate.")

    policy = policy or PronunciationScoringPolicy.from_env()
    store = store if store is not None else default_reference_store
    config = FeedbackConfig.from_env()
    provider = provider or build_feedback_provider(config)

    reference, cache_hit, reference_sha = await run_in_threadpool(
        _reference_features, reference_audio_path, reference_key, expected_text, expected, store
    )
    student_sha = _sha256(student_audio)

    comparison: Optional[UtteranceComparison] = None
    student: Optional[UtteranceFeatures] = None
    quality: Optional[dict] = None

    # The preflight is the first of two quality stages: "retry" means the signal
    # itself is unusable (too short, too quiet, no speech, clipped); "review"
    # only means pitch has not been checked yet, which extraction does next.
    preflight = assess_recording_quality(student_audio, expected_syllable_count=len(expected))
    reason_codes = preflight.get("reason_codes") or []
    if preflight.get("status") == "retry" or "low_signal_variation" in reason_codes:
        quality = {key: preflight.get(key) for key in ("status", "reason_codes", "metrics")}
        score = unscorable_score(REASON_RECORDING_UNUSABLE, policy)
    else:
        try:
            student = await run_in_threadpool(_extract_student, student_audio, expected_text, expected)
            comparison = compare_utterances(student, reference, policy)
            score = score_comparison(comparison, policy)
        except FeatureExtractionError as exc:
            score = unscorable_score(exc.code, policy)
        except ReferenceMismatchError as exc:
            raise EvaluationError("reference_mismatch", str(exc)) from exc

    feedback = await generate_feedback_safely(
        provider, build_feedback_input(expected_text, score, max_issues=config.max_issues)
    )
    return PronunciationEvaluation(
        expected_text=expected_text,
        reference_key=reference_key,
        score=score,
        comparison=comparison,
        student_features=student,
        reference_features=reference,
        feedback=feedback,
        policy=policy,
        reference_cache_hit=cache_hit,
        reference_audio_sha256=reference_sha,
        student_audio_sha256=student_sha,
        quality=quality,
    )
