"""Wav2Vec2 segmental evidence for the independent pronunciation rubric.

Wav2Vec2 is used here as a reference-relative acoustic representation. It does
not magically produce phoneme labels: each student's initial and final segment
is compared with the matching teacher segment from the known script. Praat F0
remains the evidence for lexical tone, because pitch contour is the relevant
observable for that part of Mandarin pronunciation.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Optional

import numpy as np

from domain.pronunciation.compare import compare_utterances
from domain.pronunciation.policy import PronunciationScoringPolicy
from domain.pronunciation.rubric import RubricPolicy
from domain.pronunciation.types import UtteranceFeatures
from pronunciation.embeddings import SyllableEmbedder, pool_span


class Wav2Vec2Unavailable(RuntimeError):
    """The configured Wav2Vec2 model cannot provide evidence."""


_INITIALS = (
    "zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
    "j", "q", "x", "r", "z", "c", "s", "y", "w",
)
_TONE_SUFFIX = re.compile(r"[1-5]$")


def _initial_boundary(pinyin: str) -> tuple[bool, float]:
    plain = _TONE_SUFFIX.sub("", pinyin.lower().strip())
    for initial in _INITIALS:
        if plain.startswith(initial):
            # Keep the boundary configurable through the policy rather than
            # pretending this is a measured phoneme boundary.
            return True, 0.34
    return False, 0.0


def _cosine(left: np.ndarray, right: np.ndarray) -> Optional[float]:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 1e-9 or right_norm <= 1e-9:
        return None
    return max(-1.0, min(1.0, float(np.dot(left, right) / (left_norm * right_norm))))


def _similarity(
    student_times: np.ndarray,
    student_vectors: np.ndarray,
    reference_times: np.ndarray,
    reference_vectors: np.ndarray,
    student_start: float,
    student_end: float,
    reference_start: float,
    reference_end: float,
) -> Optional[float]:
    student = pool_span(student_times, student_vectors, student_start, student_end)
    reference = pool_span(reference_times, reference_vectors, reference_start, reference_end)
    if student is None or reference is None:
        return None
    return _cosine(student, reference)


def _model_config() -> tuple[str, int, Optional[str]]:
    if (os.environ.get("PRONUNCIATION_WAV2VEC2_ENABLED", "true").strip().lower()
            in {"0", "false", "off", "no"}):
        raise Wav2Vec2Unavailable("Wav2Vec2 pronunciation scoring is disabled by configuration.")
    model = (os.environ.get("PRONUNCIATION_WAV2VEC2_MODEL") or "").strip() or None
    layer_raw = (os.environ.get("PRONUNCIATION_WAV2VEC2_LAYER") or "6").strip()
    try:
        layer = int(layer_raw)
    except ValueError as exc:
        raise Wav2Vec2Unavailable("PRONUNCIATION_WAV2VEC2_LAYER must be an integer.") from exc
    cache = (os.environ.get("PRONUNCIATION_WAV2VEC2_CACHE_DIR") or "").strip() or None
    return model or "TencentGameMate/chinese-wav2vec2-base", layer, cache


def _safe_similarity(value: Optional[float]) -> Optional[float]:
    return None if value is None or not math.isfinite(value) else round((value + 1.0) / 2.0, 4)


def analyze_wav2vec2(
    *,
    student_audio_path: str,
    reference_audio_path: str,
    student: UtteranceFeatures,
    reference: UtteranceFeatures,
    policy: RubricPolicy,
) -> dict[str, Any]:
    """Return scalar Wav2Vec2 evidence and Praat tone evidence.

    The returned object deliberately contains no neural embedding vectors. Raw
    vectors are private model intermediates; persisted evidence is the segment
    span, similarity, model provenance and the decisions derived from them.
    """
    if len(student.syllables) != len(reference.syllables):
        raise Wav2Vec2Unavailable("The student and reference have different syllable counts.")
    model_name, layer, cache_dir = _model_config()
    try:
        embedder = SyllableEmbedder(model_name=model_name, layer=layer, cache_dir=cache_dir)
        student_times, student_vectors = embedder.frame_embeddings(student_audio_path)
        reference_times, reference_vectors = embedder.frame_embeddings(reference_audio_path)
        loaded_model = embedder.model_name
    except Exception as exc:  # noqa: BLE001 - turn optional model failures into evidence status
        raise Wav2Vec2Unavailable(f"Wav2Vec2 model unavailable: {type(exc).__name__}") from exc

    syllables: list[dict[str, Any]] = []
    initial_values: list[float] = []
    final_values: list[float] = []
    tone_comparison = compare_utterances(student, reference, PronunciationScoringPolicy())
    for student_syllable, reference_syllable in zip(student.syllables, reference.syllables):
        has_initial, boundary = _initial_boundary(student_syllable.expected.pinyin)
        student_start = student_syllable.start_ms / 1000.0
        student_end = student_syllable.end_ms / 1000.0
        reference_start = reference_syllable.start_ms / 1000.0
        reference_end = reference_syllable.end_ms / 1000.0
        student_boundary = student_start + (student_end - student_start) * boundary
        reference_boundary = reference_start + (reference_end - reference_start) * boundary
        initial = (
            _safe_similarity(
                _similarity(
                    student_times, student_vectors, reference_times, reference_vectors,
                    student_start, student_boundary, reference_start, reference_boundary,
                )
            )
            if has_initial else None
        )
        final = _safe_similarity(
            _similarity(
                student_times, student_vectors, reference_times, reference_vectors,
                student_boundary, student_end, reference_boundary, reference_end,
            )
        )
        tone = tone_comparison.syllables[student_syllable.expected.index].tone_similarity
        if initial is not None:
            initial_values.append(initial)
        if final is not None:
            final_values.append(final)
        syllables.append({
            "index": student_syllable.expected.index,
            "hanzi": student_syllable.expected.hanzi,
            "pinyin": student_syllable.expected.pinyin,
            "has_initial": has_initial,
            "initial_span_ratio": [0.0, boundary] if has_initial else None,
            "final_span_ratio": [boundary, 1.0],
            "initial_similarity": initial,
            "final_similarity": final,
            "tone_similarity": tone,
            "tone_flags": list(tone_comparison.syllables[student_syllable.expected.index].flags),
        })

    tone_values = [item["tone_similarity"] for item in syllables if item["tone_similarity"] is not None]
    return {
        "model": loaded_model,
        "layer": layer,
        "embedding_source": "wav2vec2_reference_segment_similarity",
        "tone_source": "praat_f0_reference_contour",
        "syllables": syllables,
        "initial_similarity": round(sum(initial_values) / len(initial_values), 4) if initial_values else None,
        "final_similarity": round(sum(final_values) / len(final_values), 4) if final_values else None,
        "tone_similarity": round(sum(tone_values) / len(tone_values), 4) if tone_values else None,
        "initial_coverage": round(len(initial_values) / len(syllables), 4) if syllables else 0.0,
        "final_coverage": round(len(final_values) / len(syllables), 4) if syllables else 0.0,
        "tone_coverage": round(len(tone_values) / len(syllables), 4) if syllables else 0.0,
        "thresholds": policy.pronunciation_limits,
    }


def _level(value: Optional[float], thresholds: tuple[float, ...]) -> Optional[int]:
    if value is None:
        return None
    return next((5 - index for index, threshold in enumerate(thresholds) if value >= threshold), 1)


def score_wav2vec2_pronunciation(evidence: dict[str, Any], policy: RubricPolicy) -> dict[str, Any]:
    """Convert Wav2Vec2/Praat evidence to one independent 1–5 score."""
    criteria = []
    values = {
        "initial_similarity": evidence.get("initial_similarity"),
        "final_similarity": evidence.get("final_similarity"),
        "tone_similarity": evidence.get("tone_similarity"),
    }
    for feature, value in values.items():
        thresholds = policy.pronunciation_limits[feature]
        criteria.append({
            "feature": feature,
            "value": value,
            "level": _level(value, thresholds),
            "thresholds_levels_5_to_2": list(thresholds),
            "comparison": ">=",
        })
    available = [item["level"] for item in criteria if item["level"] is not None]
    score = min(available) if available else None
    errors = []
    for item in evidence.get("syllables", []):
        for kind, key in (("initial", "initial_similarity"), ("final", "final_similarity")):
            value = item.get(key)
            if value is not None and value < policy.pronunciation_limits[f"{key}"][2]:
                errors.append({
                    "syllable_index": item["index"], "hanzi": item["hanzi"], "pinyin": item["pinyin"],
                    "kind": kind, "similarity": value, "evidence": "wav2vec2_reference_segment",
                })
    tone_errors = [
        {"syllable_index": item["index"], "hanzi": item["hanzi"], "pinyin": item["pinyin"],
         "similarity": item["tone_similarity"], "flags": item["tone_flags"], "evidence": "praat_f0_reference_contour"}
        for item in evidence.get("syllables", [])
        if item.get("tone_similarity") is not None
        and item.get("tone_similarity") < policy.pronunciation_limits["tone_similarity"][2]
    ]
    if score is None:
        reason = "Wav2Vec2 or Praat produced insufficient pronunciation evidence."
        description = None
    else:
        reason = "Level %s: the pronunciation score is limited by the lowest initial, final or tone criterion." % score
        description = {
            5: "Initials, finals and lexical tone closely match the reference.",
            4: "Pronunciation is close to the reference with minor segmental or tone differences.",
            3: "Noticeable segmental or tone differences remain.",
            2: "Frequent segmental or tone differences affect several syllables.",
            1: "Large differences affect the segmental and/or tone pattern.",
        }[score]
    return {
        "key": "pronunciation", "score": score, "out_of": 5, "source": "wav2vec2_plus_praat",
        "rubric_level": score, "rubric_description": description, "reason": reason,
        "measurements": evidence, "criteria": criteria,
        "pronunciation_errors": errors, "tone_errors": tone_errors,
    }
