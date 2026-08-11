"""Candidate E's evaluation pipeline: STEP 4 (onset-skip ablation) through
STEP 8 (freeze). No OMPAL data anywhere in this module -- everything comes
from canonical contours and the existing controlled synthetic audio set.

    python -m benchmarking.candidates.contour_scorer_v2_pipeline
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

import chinese_tones
from benchmarking.candidates.contour_scorer_v2 import (
    T1_RANGE_REF,
    T1_SLOPE_REF,
    T3_DEPTH_OFFSET,
    T3_DEPTH_SCALE,
    T3_INVALID_SHAPE_CEILING,
    T3_SHAPE_SLOPE_EPS,
    _half_split,
    _linear_slope,
    apply_onset_skip,
    score_segment_v2,
)
from praat_analyzer import analyze_all, extract_pitch

THRESHOLD = 58.0

AUDIO_DIR = Path("benchmarking/external/controlled_tone_test/audio")
FAMILIES = {"ma": ("媽", "麻", "馬", "罵"), "shi": ("詩", "時", "史", "是")}

CANONICAL_CONTOURS = {
    1: [1.0, 1.0, 1.0, 1.0, 1.0],
    2: [0.2, 0.3, 0.5, 0.7, 0.9],
    3: [0.6, 0.35, 0.2, 0.35, 0.65],
    4: [0.9, 0.75, 0.55, 0.3, 0.1],
}

ONSET_ABLATION_CSV = Path("benchmarking/results/candidate_e_onset_ablation.csv")
CANONICAL_MATRIX_CSV = Path("benchmarking/results/candidate_e_canonical_matrix.csv")
CONTROLLED_MD = Path("benchmarking/results/candidate_e_controlled_test.md")
CONTROLLED_PREDICTIONS_CSV = Path("benchmarking/results/candidate_e_controlled_predictions.csv")
FORMULA_MD = Path("benchmarking/results/candidate_e_formula.md")
PROTOCOL_JSON = Path("benchmarking/results/candidate_e_protocol.json")

ONSET_ABLATION_FRACTIONS = (0.0, 0.03, 0.05, 0.08, 0.12)


# ---------------------------------------------------------------------------
# STEP 4 -- onset-skip ablation on the controlled synthetic audio
# ---------------------------------------------------------------------------


def run_onset_ablation() -> list[dict[str, Any]]:
    rows = []
    for family, characters in FAMILIES.items():
        for tone, character in enumerate(characters, start=1):
            audio_path = AUDIO_DIR / f"{family}{tone}.wav"
            raw_contour = extract_pitch(str(audio_path))
            for fraction in ONSET_ABLATION_FRACTIONS:
                trimmed = apply_onset_skip(raw_contour, fraction)
                normalized = chinese_tones.normalize_pitch_contour(trimmed)
                if len(normalized) < 4:
                    rows.append({
                        "family": family, "produced_tone": tone, "audio_file": str(audio_path),
                        "onset_skip_pct": round(fraction * 100), "n_frames_after_trim": len(trimmed),
                        "full_slope": None, "first_half_slope": None, "second_half_slope": None,
                        "note": "too few frames after trim",
                    })
                    continue
                smoothed = chinese_tones._smooth_for_directional_scoring(normalized)
                first_half, second_half = _half_split(smoothed)
                rows.append({
                    "family": family,
                    "produced_tone": tone,
                    "audio_file": str(audio_path),
                    "onset_skip_pct": round(fraction * 100),
                    "n_frames_after_trim": len(trimmed),
                    "full_slope": round(_linear_slope(smoothed), 4),
                    "first_half_slope": round(_linear_slope(first_half), 4),
                    "second_half_slope": round(_linear_slope(second_half), 4),
                    "note": "",
                })
    return rows


def _direction_ranking_correct(rows_at_fraction: list[dict[str, Any]]) -> dict[str, Any]:
    """Pre-specified ranking checks, one per tone, from slope alone --
    independent of the final scoring formulas, purely about whether the
    RAW slope measurement still points the right way and ranks correctly
    after this much trimming.

    T1: |full_slope| should be the smallest among the 4 produced tones
        (within each family).
    T2: full_slope should be the largest (most positive) among the 4.
    T3: first_half_slope < 0 AND second_half_slope > 0 (the dip signature).
    T4: full_slope should be the smallest (most negative) among the 4.
    """
    by_family: dict[str, dict[int, dict[str, Any]]] = {}
    for row in rows_at_fraction:
        by_family.setdefault(row["family"], {})[row["produced_tone"]] = row

    results = {"t1_ranked_flattest": [], "t2_ranked_most_positive": [],
               "t3_dip_signature_present": [], "t4_ranked_most_negative": []}
    for family, by_tone in by_family.items():
        if any(by_tone[t]["full_slope"] is None for t in (1, 2, 3, 4)):
            continue
        slopes = {t: by_tone[t]["full_slope"] for t in (1, 2, 3, 4)}
        flattest = min(slopes, key=lambda t: abs(slopes[t]))
        most_positive = max(slopes, key=lambda t: slopes[t])
        most_negative = min(slopes, key=lambda t: slopes[t])
        results["t1_ranked_flattest"].append(flattest == 1)
        results["t2_ranked_most_positive"].append(most_positive == 2)
        results["t4_ranked_most_negative"].append(most_negative == 4)
        t3 = by_tone[3]
        results["t3_dip_signature_present"].append(
            t3["first_half_slope"] is not None and t3["first_half_slope"] < 0 and t3["second_half_slope"] > 0
        )
    return {key: (sum(values), len(values)) for key, values in results.items()}


def summarize_ablation_rankings(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    summary = {}
    for pct in (0, 3, 5, 8, 12):
        rows_at = [r for r in rows if r["onset_skip_pct"] == pct]
        summary[pct] = _direction_ranking_correct(rows_at)
    return summary


def select_onset_fraction(ranking_summary: dict[int, dict[str, Any]]) -> tuple[int, str]:
    """Pick the smallest onset-skip percentage that maximizes the total
    number of correct rankings across all four checks -- ties broken toward
    LESS trimming, since the diagnosis already found that MORE trimming
    (production's 12%) actively reverses direction for short syllables, so
    there's no a priori reason to prefer a larger skip when scores tie."""
    totals = {}
    for pct, checks in ranking_summary.items():
        totals[pct] = sum(correct for correct, _ in checks.values())
    best_total = max(totals.values())
    best_pct = min(pct for pct, total in totals.items() if total == best_total)
    reason = (
        f"{best_pct}% onset skip achieves the most correct tone rankings "
        f"({best_total} of {sum(len(v) for v in ranking_summary[best_pct].values())} "
        "family x check combinations) among the tested settings "
        f"{list(ranking_summary)}; smallest such setting chosen on ties, "
        "since the diagnosis found larger skips actively harmful for short "
        "isolated syllables, not merely unhelpful."
    )
    return best_pct, reason


# ---------------------------------------------------------------------------
# STEP 5 -- canonical contour ranking requirement (diagonal beats every
# off-diagonal cell in its column). STOP if this fails.
# ---------------------------------------------------------------------------


def build_canonical_matrix_v2() -> list[dict[str, Any]]:
    rows = []
    for produced_tone, contour in CANONICAL_CONTOURS.items():
        seg = np.array(contour)
        for expected_tone in (1, 2, 3, 4):
            score, source = score_segment_v2(seg, expected_tone)
            rows.append({
                "produced_tone": produced_tone,
                "expected_tone": expected_tone,
                "produced_contour": str(contour),
                "score": round(score, 2),
                "provenance": source,
                "is_diagonal": int(produced_tone == expected_tone),
            })
    return rows


def check_canonical_ranking(rows: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    by_expected: dict[int, dict[int, float]] = {}
    for row in rows:
        by_expected.setdefault(row["expected_tone"], {})[row["produced_tone"]] = row["score"]
    failures = []
    for expected_tone, by_produced in by_expected.items():
        diagonal = by_produced[expected_tone]
        for produced_tone, score in by_produced.items():
            if produced_tone != expected_tone and score >= diagonal:
                failures.append(
                    f"T{produced_tone} contour ({score}) >= T{expected_tone}'s own "
                    f"matched score ({diagonal}) against T{expected_tone} target"
                )
    return (len(failures) == 0), failures


# ---------------------------------------------------------------------------
# STEP 6 -- controlled audio: Baseline A vs Candidate E
# ---------------------------------------------------------------------------


def _baseline_a_score(audio_path: str, reference_character: str) -> tuple[float | None, bool]:
    (
        _pc, _f, _sr, _fl, _ps, word_prosody, _dt, _ta, _fb, _pa,
    ) = analyze_all(audio_path, reference_character)
    from benchmarking.ompal_runner import flatten_characters

    characters = flatten_characters(word_prosody)
    if not characters:
        return None, False
    return characters[0]["score"], characters[0]["judged"]


def _candidate_e_score(audio_path: str, reference_tone: int) -> float | None:
    raw_contour = extract_pitch(audio_path)
    trimmed = apply_onset_skip(raw_contour)
    normalized = chinese_tones.normalize_pitch_contour(trimmed)
    if len(normalized) < 4:
        return None
    smoothed = chinese_tones._smooth_for_directional_scoring(normalized)
    score, _source = score_segment_v2(smoothed, reference_tone)
    return score


def build_test_cases() -> list[dict[str, Any]]:
    cases = []
    for family, characters in FAMILIES.items():
        for produced_tone, produced_char in enumerate(characters, start=1):
            audio_path = str(AUDIO_DIR / f"{family}{produced_tone}.wav")
            for reference_tone, reference_char in enumerate(characters, start=1):
                cases.append({
                    "case_id": f"{family}_p{produced_tone}_r{reference_tone}",
                    "family": family,
                    "audio_file": audio_path,
                    "audio_character": produced_char,
                    "audio_tone": produced_tone,
                    "reference_character": reference_char,
                    "reference_tone": reference_tone,
                    "expected_tone_correct": int(produced_tone == reference_tone),
                })
    return cases


def run_controlled_comparison(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        baseline_score, baseline_judged = _baseline_a_score(case["audio_file"], case["reference_character"])
        candidate_e_score = _candidate_e_score(case["audio_file"], case["reference_tone"])
        rows.append({
            **case,
            "baseline_a_score": round(baseline_score, 2) if baseline_score is not None else None,
            "baseline_a_judged": baseline_judged,
            "baseline_a_pass": int(baseline_score >= THRESHOLD) if baseline_judged and baseline_score is not None else None,
            "candidate_e_score": round(candidate_e_score, 2) if candidate_e_score is not None else None,
            "candidate_e_pass": int(candidate_e_score >= THRESHOLD) if candidate_e_score is not None else None,
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


def compare_baseline_and_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = [row["expected_tone_correct"] for row in rows]
    overall = {
        "baseline_a": _confusion(expected, [row["baseline_a_pass"] for row in rows]),
        "candidate_e": _confusion(expected, [row["candidate_e_pass"] for row in rows]),
    }
    by_tone = {}
    for tone in (1, 2, 3, 4):
        tone_rows = [row for row in rows if row["reference_tone"] == tone]
        tone_expected = [row["expected_tone_correct"] for row in tone_rows]
        by_tone[tone] = {
            "baseline_a": _confusion(tone_expected, [row["baseline_a_pass"] for row in tone_rows]),
            "candidate_e": _confusion(tone_expected, [row["candidate_e_pass"] for row in tone_rows]),
        }
    return {"overall": overall, "by_tone": by_tone}


# ---------------------------------------------------------------------------
# STEP 7 -- score-scale audit
# ---------------------------------------------------------------------------


def score_scale_audit(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result = {}
    for tone in (1, 2, 3, 4):
        matched = [row["candidate_e_score"] for row in rows if row["reference_tone"] == tone and row["expected_tone_correct"] == 1 and row["candidate_e_score"] is not None]
        result[tone] = {
            "matched_min": min(matched) if matched else None,
            "matched_max": max(matched) if matched else None,
            "matched_median": float(np.median(matched)) if matched else None,
        }
    return result


# ---------------------------------------------------------------------------
# STEP 8 -- freeze
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_protocol(
    onset_fraction_pct: int,
    canonical_ranking_passed: bool,
    known_limitations: list[str] | None = None,
) -> None:
    protocol = {
        "candidate": "E",
        "version": "v1",
        "baseline_reference": "BASELINE_A_FROZEN (chinese_tones.directional_tone_scores, unmodified)",
        "module": "benchmarking/candidates/contour_scorer_v2.py",
        "module_sha256": _file_hash(Path("benchmarking/candidates/contour_scorer_v2.py")),
        "formulas": {
            "T1": {
                "type": "shape-specific flatness (slope AND range gates)",
                "constants": {"T1_SLOPE_REF": T1_SLOPE_REF, "T1_RANGE_REF": T1_RANGE_REF},
            },
            "T2": {"type": "unchanged from chinese_tones._score_segment (rise-based)"},
            "T3": {
                "type": "shape-validity gate (fall-then-rise) then depth-calibrated score",
                "constants": {
                    "T3_SHAPE_SLOPE_EPS": T3_SHAPE_SLOPE_EPS,
                    "T3_DEPTH_OFFSET": T3_DEPTH_OFFSET,
                    "T3_DEPTH_SCALE": T3_DEPTH_SCALE,
                    "T3_INVALID_SHAPE_CEILING": T3_INVALID_SHAPE_CEILING,
                },
            },
            "T4": {"type": "unchanged from chinese_tones._score_segment (fall-based)"},
        },
        "preprocessing": {
            "onset_skip_fraction_pct": onset_fraction_pct,
            "selected_from": "STEP 4 ablation over {0,3,5,8,12}% on controlled synthetic audio only",
            "differs_from_production": (
                "does not reuse estimate_word_prosody's alignment-based word-span "
                "windowing; operates on the syllable's own full extracted pitch "
                "contour with this configurable leading trim"
            ),
        },
        "canonical_ranking_check_passed": canonical_ranking_passed,
        "known_limitations": known_limitations or [],
        "constants_source": "canonical contours and controlled synthetic audio ONLY -- no OMPAL labels were read or used anywhere in this candidate's development",
        "ompal_status": "NOT TOUCHED -- development, validation, and final_test were not loaded by any code in this candidate's development",
    }
    PROTOCOL_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROTOCOL_JSON.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")


def run() -> None:
    from benchmarking.candidates import report_contour_scorer_v2

    print("STEP 4: onset-skip ablation...")
    ablation_rows = run_onset_ablation()
    report_contour_scorer_v2.write_ablation_csv(ablation_rows, ONSET_ABLATION_CSV)
    ranking_summary = summarize_ablation_rankings(ablation_rows)
    onset_pct, onset_reason = select_onset_fraction(ranking_summary)
    print(f"  selected onset skip: {onset_pct}% ({onset_reason})")

    # Apply the selected fraction to the live module for the rest of this run.
    import benchmarking.candidates.contour_scorer_v2 as v2
    v2.ONSET_SKIP_FRACTION = onset_pct / 100.0

    print("STEP 5: canonical contour ranking requirement...")
    canonical_rows = build_canonical_matrix_v2()
    report_contour_scorer_v2.write_canonical_csv(canonical_rows, CANONICAL_MATRIX_CSV)
    passed, failures = check_canonical_ranking(canonical_rows)
    print(f"  canonical ranking passed: {passed}" + (f" -- {len(failures)} failures" if failures else ""))

    if not passed:
        report_contour_scorer_v2.write_stop_report(canonical_rows, failures, onset_pct, onset_reason, ranking_summary)
        write_protocol(onset_pct, canonical_ranking_passed=False)
        print("STOPPING: canonical ranking requirement failed. See candidate_e_controlled_test.md.")
        return

    print("STEP 6: controlled audio comparison...")
    cases = build_test_cases()
    comparison_rows = run_controlled_comparison(cases)
    report_contour_scorer_v2.write_predictions_csv(comparison_rows, CONTROLLED_PREDICTIONS_CSV)
    comparison = compare_baseline_and_candidate(comparison_rows)

    print("STEP 7: score-scale audit...")
    scale_audit = score_scale_audit(comparison_rows)

    report_contour_scorer_v2.write_controlled_report(
        comparison_rows, comparison, scale_audit, onset_pct, onset_reason,
        ranking_summary, canonical_rows, CONTROLLED_MD,
    )
    report_contour_scorer_v2.write_formula_doc(FORMULA_MD)

    print("STEP 8: freezing protocol...")
    t3_matched_scores = [
        row["candidate_e_score"] for row in comparison_rows
        if row["reference_tone"] == 3 and row["expected_tone_correct"] == 1 and row["candidate_e_score"] is not None
    ]
    t3_limitation = (
        "T3 shape-validity gate: real single-syllable controlled-audio T3 productions do not "
        "reliably show the fall-then-rise shape this gate requires (STEP 4 ablation: dip signature "
        "present in 0/2 families at every tested onset-skip level); matched T3 controlled-audio "
        "cases score near zero (observed: " + ", ".join(f"{s:.2f}" for s in t3_matched_scores) + "), "
        "and at least one genuinely-wrong-tone case outscored every genuinely-correct T3 case. "
        "T3 needs further work before this candidate is ready for further development -- see "
        "candidate_e_controlled_test.md's STEP 6 limitation section for the full analysis."
    )
    write_protocol(onset_pct, canonical_ranking_passed=True, known_limitations=[t3_limitation])
    print(f"Done. See {CONTROLLED_MD}, {FORMULA_MD}, {PROTOCOL_JSON}.")


if __name__ == "__main__":
    run()
