"""Shape an evaluation for the API.

Students get the scores, feedback and a limited reference-relative comparison
for visualization. Extraction details and the full debug view remain available
to teachers and admins.
"""

from __future__ import annotations

from typing import Any

from services.pronunciation.evaluator import PronunciationEvaluation
from services.pronunciation.rubric_evaluator import RubricEvaluation


def _reference_comparison(comparison: dict[str, Any]) -> dict[str, Any]:
    """Expose scalar similarity evidence and aligned contours, without debug."""
    debug = comparison.get("debug") or {}
    reference = debug.get("reference_pitch_contour") or []
    student = debug.get("student_pitch_contour") or []
    reference_contour, student_contour = [], []
    for student_index, reference_index in debug.get("dtw_path") or []:
        if not (0 <= student_index < len(student) and 0 <= reference_index < len(reference)):
            continue
        time, reference_pitch = reference[reference_index]
        reference_contour.append([time, reference_pitch])
        student_contour.append([time, student[student_index][1]])
    return {
        "status": comparison["status"], "backend": comparison["backend"],
        "reason": comparison.get("reason"),
        "evidence_quality": comparison.get("evidence_quality"),
        "measurements": comparison.get("measurements") or {},
        "contours": {"reference": reference_contour, "student": student_contour},
    }


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


def present_evaluation(evaluation: PronunciationEvaluation | RubricEvaluation, *, include_debug: bool) -> dict[str, Any]:
    if isinstance(evaluation, RubricEvaluation):
        body = {key: value for key, value in evaluation.body.items() if include_debug or key != "debug"}
        comparison = (evaluation.body.get("debug") or {}).get("librosa_comparison")
        if comparison:
            body["reference_comparison"] = _reference_comparison(comparison)
        return body
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
