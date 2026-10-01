"""Active AI + Praat assessment: separate 1–5 dimensions, no overall score.

Luna receives measurements only and explains Praat decisions. It cannot hear
audio, so Accuracy is explicitly unavailable, as selected by the project owner.
"""

import asyncio
from dataclasses import dataclass

import httpx
from starlette.concurrency import run_in_threadpool

from domain.pronunciation.compare import compare_utterances
from domain.pronunciation.policy import PronunciationScoringPolicy
from domain.pronunciation.rubric import RubricPolicy, score_fluency, score_prosody
from services.content.verification import assess_recording_quality
from services.pronunciation.config import FeedbackConfig
from services.pronunciation.evaluator import EvaluationError, _extract_student, _reference_features, _sha256
from services.pronunciation.extraction import FeatureExtractionError
from services.pronunciation.feedback import FeedbackRejected, OpenAICompatibleFeedbackProvider, build_feedback_provider
from services.pronunciation.reference_cache import default_reference_store
from services.pronunciation.script import build_expected_syllables


@dataclass(frozen=True)
class RubricEvaluation:
    body: dict


async def evaluate_rubric_pronunciation(
    *, student_audio: bytes, reference_audio_path: str, reference_key: str,
    expected_text: str, policy=None, provider=None, store=None,
) -> RubricEvaluation:
    if not student_audio:
        raise EvaluationError("empty_audio", "No audio was received.")
    expected = build_expected_syllables(expected_text)
    if not expected:
        raise EvaluationError("no_syllables", "The script has no Chinese syllables to evaluate.")
    try:
        policy = policy or RubricPolicy.from_env()
    except (TypeError, ValueError) as exc:
        raise EvaluationError("rubric_policy_invalid", "The configured rubric policy is invalid.") from exc
    reference, cache_hit, reference_sha = await run_in_threadpool(
        _reference_features, reference_audio_path, reference_key, expected_text, expected,
        store if store is not None else default_reference_store,
    )
    preflight = assess_recording_quality(student_audio, expected_syllable_count=len(expected))
    if preflight.get("status") == "retry" or "low_signal_variation" in (preflight.get("reason_codes") or []):
        raise EvaluationError("recording_unscorable", "Record the full sentence again in a quiet place.")
    try:
        student = await run_in_threadpool(_extract_student, student_audio, expected_text, expected)
    except FeatureExtractionError as exc:
        raise EvaluationError("recording_unscorable", f"Recording could not be measured ({exc.code}).") from exc
    accuracy = {
        "key": "accuracy", "score": None, "out_of": 5, "source": "unavailable",
        "rubric_level": None, "rubric_description": None,
        "reason": "GPT-6 Luna does not accept audio; segmental and lexical tone accuracy were not assessed.",
        "measurements": {}, "criteria": [], "ai_result": None,
    }
    fluency = score_fluency(student, reference, policy)
    prosody = score_prosody(student, reference, policy)

    def model_dimension(dimension):
        # Preserve the earlier privacy/evidence boundary: Luna can explain the
        # independent result using scalar summaries and rubric decisions, but
        # never receives audio, F0 contours, syllable timelines or feature arrays.
        scalars = {key: value for key, value in dimension["measurements"].items()
                   if isinstance(value, (str, int, float, bool)) or value is None}
        return {key: value for key, value in dimension.items() if key != "measurements"} | {
            "measurements": scalars,
        }
    config = FeedbackConfig.from_env()
    provider = provider or build_feedback_provider(config)
    evidence = {
        "sentence": expected_text, "accuracy": model_dimension(accuracy),
        "fluency": model_dimension(fluency), "prosody": model_dimension(prosody),
        "validation_status": policy.validation_status,
        "alignment": {"student": student.to_dict()["alignment"], "reference": reference.to_dict()["alignment"]},
    }
    if not isinstance(provider, OpenAICompatibleFeedbackProvider):
        raise EvaluationError("llm_not_configured", "Configure GPT-6 Luna feedback. No local feedback was substituted.")
    try:
        feedback = await provider.generate_rubric_feedback(evidence)
    except FeedbackRejected as exc:
        raise EvaluationError(str(exc), f"GPT-6 Luna feedback failed ({exc}). No local feedback was substituted.") from exc
    except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
        raise EvaluationError("llm_timeout", "GPT-6 Luna feedback timed out. Retry this recording.") from exc
    except Exception as exc:
        raise EvaluationError(f"llm_error_{type(exc).__name__}", "GPT-6 Luna feedback failed. No local feedback was substituted.") from exc
    for dimension in (fluency, prosody):
        dimension["feedback"] = feedback.dimension_feedback[dimension["key"]]
    # Acoustic comparison remains diagnostic evidence only: it does not create
    # accuracy or an overall score and is not handed to Luna as word errors.
    comparison = compare_utterances(student, reference, PronunciationScoringPolicy())
    provenance = {
        "scoring_policy_version": policy.version,
        "acoustic_pipeline_version": reference.provenance.get("pipeline_version"),
        **reference.provenance,
        "reference_key": reference_key, "expected_text": expected_text,
        "reference_audio_sha256": reference_sha, "student_audio_sha256": _sha256(student_audio),
        "feedback_source": feedback.source, "feedback_model": feedback.model,
        "accuracy_source": "unavailable", "accuracy_ai_result": None,
        "validation_status": policy.validation_status,
    }
    return RubricEvaluation({
        "target_text": expected_text, "status": "scored" if any(d["score"] is not None for d in (fluency, prosody)) else "unscorable",
        "scoring_policy": policy.to_dict(), "provenance": provenance,
        "reason": None, "dimensions": {"accuracy": accuracy, "fluency": fluency, "prosody": prosody},
        "metrics": {}, "words": [], "feedback": feedback.to_dict(),
        "model": {"scoring_version": policy.version, "acoustic_pipeline_version": provenance["acoustic_pipeline_version"],
                  "feedback_model": feedback.model, "feedback_source": feedback.source},
        "reference": {"key": reference_key, "cache_hit": cache_hit},
        "debug": {"provenance": provenance, "policy": policy.to_dict(), "issues": [],
                  "comparison": comparison.to_dict(), "reference_features": reference.to_dict(),
                  "student_features": student.to_dict(), "recording_quality": preflight},
    })
