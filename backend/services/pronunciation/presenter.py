"""Shape an evaluation for the API.

Students get the score, the per-word findings and the feedback text. Raw pitch
data, policy internals and provenance are for teachers and admins only: a
student never needs F0 numbers, and the debug view exists to answer "why 84
and not 90" from measurements.
"""

from __future__ import annotations

from typing import Any

from services.pronunciation.evaluator import PronunciationEvaluation


def _score_block(evaluation: PronunciationEvaluation) -> dict[str, Any]:
    score = evaluation.score
    return {
        "total": score.total,
        "renormalized": score.renormalized,
        "dimensions": [
            {
                "key": d.key,
                "basis": d.basis,
                "points": d.points,
                "out_of": d.max_points,
                "note": d.note,
            }
            for d in score.dimensions
        ],
    }


def _metrics_block(evaluation: PronunciationEvaluation) -> dict[str, Any]:
    comparison = evaluation.comparison
    if comparison is None:
        return {}
    return {
        "tone_similarity": comparison.tone_similarity,
        "rhythm_similarity": comparison.rhythm_similarity,
        "duration_similarity": comparison.duration_similarity,
        "pause_similarity": comparison.pause_similarity,
    }


def _words_block(evaluation: PronunciationEvaluation) -> list[dict[str, Any]]:
    comparison = evaluation.comparison
    if comparison is None:
        return []
    return [
        {
            "word": s.hanzi,
            "pinyin": s.pinyin,
            "expected_tone": s.expected_tone,
            "tone_similarity": s.tone_similarity,
            "reference_shape": s.reference_direction,
            "student_shape": s.student_direction,
            "duration_ratio": s.duration_ratio,
            "evidence": s.evidence,
            "flags": list(s.flags),
        }
        for s in comparison.syllables
    ]


def present_evaluation(evaluation: PronunciationEvaluation, *, include_debug: bool) -> dict[str, Any]:
    feedback = evaluation.feedback
    provenance = evaluation.provenance()
    body: dict[str, Any] = {
        "status": evaluation.score.status,
        "reason": evaluation.score.reason,
        "score": _score_block(evaluation),
        "metrics": _metrics_block(evaluation),
        "words": _words_block(evaluation),
        "feedback": (
            feedback.to_dict()
            if include_debug
            else {
                "summary": feedback.summary,
                "focus_words": [w.to_dict() for w in feedback.focus_words],
                "practice_tip": feedback.practice_tip,
            }
        ),
        "model": {
            "scoring_version": provenance["scoring_policy_version"],
            "acoustic_pipeline_version": provenance["acoustic_pipeline_version"],
            "feedback_model": feedback.model,
            "feedback_source": feedback.source,
        },
        "reference": {
            "key": evaluation.reference_key,
            "cache_hit": evaluation.reference_cache_hit,
        },
    }
    if include_debug:
        body["debug"] = {
            "provenance": provenance,
            "policy": evaluation.policy.to_dict(),
            "issues": [issue.to_dict() for issue in evaluation.score.issues],
            "comparison": evaluation.comparison.to_dict() if evaluation.comparison else None,
            "reference_features": evaluation.reference_features.to_dict(),
            "student_features": evaluation.student_features.to_dict() if evaluation.student_features else None,
            "recording_quality": evaluation.quality,
        }
    return body
