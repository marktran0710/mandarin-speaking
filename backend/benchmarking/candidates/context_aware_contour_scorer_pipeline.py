"""Candidate E2's evaluation pipeline: STEP 6 (T3-context test, all 6
contexts, proper alignment) through STEP 10 (freeze). No OMPAL anywhere.

    python -m benchmarking.candidates.context_aware_contour_scorer_pipeline
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import jieba

import chinese_tones
from praat_analyzer import _intensity_contour_from_sound, _load_sound, _pitch_contour_from_sound, extract_pitch
from tone_scoring.alignment import EnergyAligner
from tone_context import han_break_flags, plan_expected_tones

from benchmarking.candidates.contour_scorer_v2 import score_segment_v2
from benchmarking.candidates.context_aware_contour_scorer import score_segment_e2
from benchmarking.candidates.contour_scorer_v2_pipeline import (
    FAMILIES,
    THRESHOLD,
    build_test_cases as build_32case_test_cases,
    _baseline_a_score,
)
from benchmarking.t3_context_audit import VOICES

AUDIO_DIR = Path("benchmarking/external/t3_context_audio")

DESIGN_MD = Path("benchmarking/results/candidate_e2_design.md")
T3_CONTEXT_TEST_MD = Path("benchmarking/results/candidate_e2_t3_context_test.md")
CONTROLLED_TEST_MD = Path("benchmarking/results/candidate_e2_controlled_test.md")
CONTROLLED_PREDICTIONS_CSV = Path("benchmarking/results/candidate_e2_controlled_predictions.csv")
PROTOCOL_JSON = Path("benchmarking/results/candidate_e2_protocol.json")

#: All 6 T3 contexts (STEP 6 explicitly names all of them, extending the
#: previous task's 4-context alignment scope to include isolated and
#: phrase_final too, so every context is measured with the SAME (proper,
#: EnergyAligner) methodology here).
BASE_CHAR = "馬"  # T3
CONTEXT_TEXT = {
    "isolated": (BASE_CHAR,),
    "plus_t1": (BASE_CHAR, "天"),
    "plus_t2": (BASE_CHAR, "人"),
    "plus_t3": (BASE_CHAR, "好"),
    "plus_t4": (BASE_CHAR, "是"),
    "phrase_final": ("三", BASE_CHAR),
}
UNDERLYING_TONE = {"馬": 3, "天": 1, "人": 2, "好": 3, "是": 4, "三": 1}
#: Which position in CONTEXT_TEXT[context] is the T3 syllable under test.
BASE_POSITION = {"isolated": 0, "plus_t1": 0, "plus_t2": 0, "plus_t3": 0, "plus_t4": 0, "phrase_final": 1}


# ---------------------------------------------------------------------------
# Shared: build the real ExpectedTone list for one context (reuses
# tone_context.plan_expected_tones directly -- no parallel rule system).
# ---------------------------------------------------------------------------


def expected_tones_for_context(context: str) -> list:
    chars = CONTEXT_TEXT[context]
    text = "".join(chars)
    tokens = jieba.lcut(text)
    token_indices: list[int] = []
    for token_index, token in enumerate(tokens):
        for _ in token:
            token_indices.append(token_index)
    underlying = [UNDERLYING_TONE[c] for c in chars]
    breaks = han_break_flags(text)
    return plan_expected_tones(list(chars), underlying, token_indices, breaks)


# ---------------------------------------------------------------------------
# STEP 6 -- T3-context test, all 6 contexts, proper EnergyAligner alignment
# ---------------------------------------------------------------------------


def _aligned_base_syllable_frames(audio_path: str, context: str) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    """Returns (frames for the base/T3 syllable, diagnostics dict)."""
    sound = _load_sound(audio_path)
    raw_contour = _pitch_contour_from_sound(sound)
    intensity = _intensity_contour_from_sound(sound)
    n_syllables = len(CONTEXT_TEXT[context])

    if len(raw_contour) < 4:
        return [], {"error": "too few raw pitch frames", "n_raw_frames": len(raw_contour)}

    spans = EnergyAligner().align(raw_contour, syllable_count=n_syllables, intensity=intensity)
    if len(spans) != n_syllables:
        return [], {"error": f"EnergyAligner returned {len(spans)} spans, expected {n_syllables}"}

    base_span = spans[BASE_POSITION[context]]
    frames = base_span.frames(raw_contour)
    diagnostics = {
        "error": "", "n_raw_frames": len(raw_contour), "n_base_frames": len(frames),
        "base_span_start": base_span.start, "base_span_end": base_span.end,
        "base_span_duration": base_span.duration,
    }
    return frames, diagnostics


def run_t3_context_test() -> list[dict[str, Any]]:
    rows = []
    for context in CONTEXT_TEXT:
        expected_list = expected_tones_for_context(context)
        base_expected = expected_list[BASE_POSITION[context]]
        for voice in VOICES:
            audio_path = str(AUDIO_DIR / f"{voice}_3_{context}.wav")
            frames, diag = _aligned_base_syllable_frames(audio_path, context)
            if diag.get("error"):
                rows.append({
                    "voice": voice, "context": context, "underlying_tone": base_expected.underlying_tone,
                    "accepted_surface_tones": str(base_expected.accepted_surface_tones),
                    "realization": base_expected.realization, "rule": base_expected.rule or "none",
                    "e_v1_score": None, "e_v1_pass": None,
                    "e2_score": None, "e2_pass": None, "e2_matched_tone": None, "e2_provenance": None,
                    "error": diag["error"],
                })
                continue

            normalized = chinese_tones.normalize_pitch_contour(frames)
            if len(normalized) < 4:
                rows.append({
                    "voice": voice, "context": context, "underlying_tone": base_expected.underlying_tone,
                    "accepted_surface_tones": str(base_expected.accepted_surface_tones),
                    "realization": base_expected.realization, "rule": base_expected.rule or "none",
                    "e_v1_score": None, "e_v1_pass": None,
                    "e2_score": None, "e2_pass": None, "e2_matched_tone": None, "e2_provenance": None,
                    "error": "too few normalized frames",
                })
                continue
            smoothed = chinese_tones._smooth_for_directional_scoring(normalized)

            e_v1_score, e_v1_prov = score_segment_v2(smoothed, base_expected.underlying_tone)
            e2_score, e2_prov, e2_matched = score_segment_e2(smoothed, base_expected)

            rows.append({
                "voice": voice, "context": context, "underlying_tone": base_expected.underlying_tone,
                "accepted_surface_tones": str(base_expected.accepted_surface_tones),
                "realization": base_expected.realization, "rule": base_expected.rule or "none",
                "e_v1_score": round(e_v1_score, 2), "e_v1_pass": int(e_v1_score >= THRESHOLD),
                "e2_score": round(e2_score, 2), "e2_pass": int(e2_score >= THRESHOLD),
                "e2_matched_tone": e2_matched, "e2_provenance": e2_prov,
                "error": "",
            })
    return rows


# ---------------------------------------------------------------------------
# STEP 7 -- full 32-case controlled test: Baseline A vs E V1 vs E2
# ---------------------------------------------------------------------------


def _expected_tone_for_isolated_reference(reference_char: str, reference_tone: int) -> Any:
    """The 32-case test's audio is always a single isolated syllable, so
    the ExpectedTone the reference character would get, via the SAME real
    planner, is built the same way -- no ad hoc substitute."""
    breaks = han_break_flags(reference_char)
    plan = plan_expected_tones([reference_char], [reference_tone], [0], breaks)
    return plan[0]


def run_32case_test() -> list[dict[str, Any]]:
    cases = build_32case_test_cases()
    rows = []
    for case in cases:
        baseline_score, baseline_judged = _baseline_a_score(case["audio_file"], case["reference_character"])
        raw_contour = extract_pitch(case["audio_file"])
        normalized = chinese_tones.normalize_pitch_contour(raw_contour)
        e_v1_score = e2_score = None
        e2_matched = None
        if len(normalized) >= 4:
            smoothed = chinese_tones._smooth_for_directional_scoring(normalized)
            e_v1_score, _ = score_segment_v2(smoothed, case["reference_tone"])
            expected = _expected_tone_for_isolated_reference(case["reference_character"], case["reference_tone"])
            e2_score, _e2_prov, e2_matched = score_segment_e2(smoothed, expected)

        rows.append({
            **case,
            "baseline_a_score": round(baseline_score, 2) if baseline_score is not None else None,
            "baseline_a_judged": baseline_judged,
            "baseline_a_pass": int(baseline_score >= THRESHOLD) if baseline_judged and baseline_score is not None else None,
            "e_v1_score": round(e_v1_score, 2) if e_v1_score is not None else None,
            "e_v1_pass": int(e_v1_score >= THRESHOLD) if e_v1_score is not None else None,
            "e2_score": round(e2_score, 2) if e2_score is not None else None,
            "e2_pass": int(e2_score >= THRESHOLD) if e2_score is not None else None,
            "e2_matched_tone": e2_matched,
        })
    return rows


def _confusion(expected: list[int], predicted: list[int | None]) -> dict[str, Any]:
    pairs = [(e, p) for e, p in zip(expected, predicted) if p is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "accuracy": None, "balanced_accuracy": None, "sensitivity": None,
                "specificity": None, "false_rejection_rate": None, "false_acceptance_rate": None}
    tp = sum(1 for e, p in pairs if e == 1 and p == 1)
    tn = sum(1 for e, p in pairs if e == 0 and p == 0)
    fp = sum(1 for e, p in pairs if e == 0 and p == 1)
    fn = sum(1 for e, p in pairs if e == 1 and p == 0)
    sensitivity = tp / (tp + fn) if (tp + fn) else None
    specificity = tn / (tn + fp) if (tn + fp) else None
    balanced = (sensitivity + specificity) / 2 if sensitivity is not None and specificity is not None else None
    return {
        "n": n, "accuracy": (tp + tn) / n, "balanced_accuracy": balanced,
        "sensitivity": sensitivity, "specificity": specificity,
        "false_rejection_rate": fn / (tp + fn) if (tp + fn) else None,
        "false_acceptance_rate": fp / (tn + fp) if (tn + fp) else None,
    }


def compare_32case(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = [row["expected_tone_correct"] for row in rows]
    overall = {
        "baseline_a": _confusion(expected, [row["baseline_a_pass"] for row in rows]),
        "e_v1": _confusion(expected, [row["e_v1_pass"] for row in rows]),
        "e2": _confusion(expected, [row["e2_pass"] for row in rows]),
    }
    by_tone = {}
    for tone in (1, 2, 3, 4):
        tone_rows = [row for row in rows if row["reference_tone"] == tone]
        tone_expected = [row["expected_tone_correct"] for row in tone_rows]
        by_tone[tone] = {
            "baseline_a": _confusion(tone_expected, [row["baseline_a_pass"] for row in tone_rows]),
            "e_v1": _confusion(tone_expected, [row["e_v1_pass"] for row in tone_rows]),
            "e2": _confusion(tone_expected, [row["e2_pass"] for row in tone_rows]),
        }
    return {"overall": overall, "by_tone": by_tone}


# ---------------------------------------------------------------------------
# STEP 9 -- score-scale audit
# ---------------------------------------------------------------------------


def score_scale_audit(t3_context_rows: list[dict[str, Any]], case32_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    def _range(scores: list[float]) -> dict[str, Any]:
        if not scores:
            return {"n": 0, "min": None, "median": None, "max": None}
        return {"n": len(scores), "min": min(scores), "median": float(np.median(scores)), "max": max(scores)}

    matched_32 = lambda tone: [
        r["e2_score"] for r in case32_rows
        if r["reference_tone"] == tone and r["expected_tone_correct"] == 1 and r["e2_score"] is not None
    ]
    t3_matched = lambda context: [
        r["e2_score"] for r in t3_context_rows if r["context"] == context and r["e2_score"] is not None
    ]

    return {
        "T1": _range(matched_32(1)),
        "T2": _range(matched_32(2)),
        "T4": _range(matched_32(4)),
        "full_T3_isolated": _range(t3_matched("isolated")),
        "half_third_T3": _range(t3_matched("plus_t1") + t3_matched("plus_t2") + t3_matched("plus_t4")),
        "T3_to_T2_sandhi": _range(t3_matched("plus_t3")),
    }


# ---------------------------------------------------------------------------
# STEP 10 -- freeze
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_protocol(scale_audit: dict[str, Any], known_limitations: list[str]) -> None:
    from benchmarking.candidates.context_aware_contour_scorer import (
        HALF_THIRD_FALL_OFFSET,
        HALF_THIRD_FALL_SCALE,
        HALF_THIRD_RISE_CEILING,
        HALF_THIRD_RISE_REJECT_SLOPE,
    )

    protocol = {
        "candidate": "E2",
        "version": "v1-pre-ompal",
        "candidate_e_v1_dependency": {
            "module": "benchmarking/candidates/contour_scorer_v2.py",
            "sha256": _file_hash(Path("benchmarking/candidates/contour_scorer_v2.py")),
            "reused_functions": ["_score_t1", "_score_t2", "_score_t3", "_score_t4", "_linear_slope", "_half_split"],
            "note": "imported read-only; not modified by Candidate E2",
        },
        "tone_context_dependency": {
            "module": "tone_context.py",
            "sha256": _file_hash(Path("tone_context.py")),
            "reused_functions": ["plan_expected_tones", "han_break_flags"],
            "note": "imported read-only; no planner rules modified",
        },
        "energy_aligner_dependency": {
            "module": "tone_scoring/alignment.py",
            "sha256": _file_hash(Path("tone_scoring/alignment.py")),
            "class": "EnergyAligner",
        },
        "module": "benchmarking/candidates/context_aware_contour_scorer.py",
        "module_sha256": _file_hash(Path("benchmarking/candidates/context_aware_contour_scorer.py")),
        "context_routing_rules": {
            "T1_T2_T4": "always routed to Candidate E V1's unchanged formulas",
            "T3_full_third": "routed to Candidate E V1's unchanged _score_t3 (fall-then-rise dip)",
            "T3_half_third": "routed to the new _score_half_third formula (this module)",
            "T3_T3_sandhi": "accepted_surface_tones=(2,) routes entirely through the T2 branch -- no separate sandhi formula",
            "multiple_accepted_tones": "score against every accepted tone, take the max (STEP 3)",
        },
        "scoring_constants": {
            "half_third_fall_offset": HALF_THIRD_FALL_OFFSET,
            "half_third_fall_scale": HALF_THIRD_FALL_SCALE,
            "half_third_rise_reject_slope": HALF_THIRD_RISE_REJECT_SLOPE,
            "half_third_rise_ceiling": HALF_THIRD_RISE_CEILING,
            "t1_t2_t3_full_t4_constants": "unchanged from Candidate E V1 -- see candidate_e_protocol.json",
        },
        "score_scale_audit": scale_audit,
        "known_limitations": known_limitations,
        "constants_source": "canonical reasoning and the EnergyAligner-aligned controlled T3 context dataset ONLY -- no OMPAL labels were read or used anywhere in this candidate's development",
        "ompal_status": "NOT TOUCHED -- development, validation, and final_test were not loaded by any code in this candidate's development",
    }
    PROTOCOL_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROTOCOL_JSON.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")


def run() -> dict[str, Any]:
    from benchmarking.candidates import report_context_aware_contour_scorer as report

    print("STEP 6: T3-context test (all 6 contexts, EnergyAligner)...")
    t3_context_rows = run_t3_context_test()

    print("STEP 7: full 32-case controlled test...")
    case32_rows = run_32case_test()
    report.write_predictions_csv(case32_rows, CONTROLLED_PREDICTIONS_CSV)
    comparison_32 = compare_32case(case32_rows)

    print("STEP 9: score-scale audit...")
    scale_audit = score_scale_audit(t3_context_rows, case32_rows)

    report.write_design_doc(DESIGN_MD)
    report.write_t3_context_report(t3_context_rows, T3_CONTEXT_TEST_MD)
    verdict = report.write_controlled_report(case32_rows, comparison_32, scale_audit, t3_context_rows, CONTROLLED_TEST_MD)

    print("STEP 10: freezing protocol...")
    limitations = report.known_limitations(t3_context_rows)
    write_protocol(scale_audit, limitations)

    print(f"Verdict: {verdict}")
    return {
        "t3_context_rows": t3_context_rows, "case32_rows": case32_rows,
        "comparison_32": comparison_32, "scale_audit": scale_audit, "verdict": verdict,
    }


if __name__ == "__main__":
    run()
