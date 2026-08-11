"""Diagnose WHY `directional_tone_scores` produces near-unconditional T1
acceptance and systematic T2/T3/T4 rejection.

    python -m benchmarking.directional_tone_diagnosis

Read-only: imports `chinese_tones` and calls its functions (including two
private helpers, `_score_segment` and `_smooth_for_directional_scoring`,
exactly as the module's own public entry points already call them) but
never edits `chinese_tones.py`, never changes threshold 58, never trains
anything, never touches OMPAL or final_test. Reuses
`benchmarking/results/controlled_tone_predictions.csv` (already generated,
synthetic TTS audio only) for STEP 4/5 -- does not re-run TTS or the API.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from chinese_tones import _score_segment, _smooth_for_directional_scoring

THRESHOLD = 58.0

CANONICAL_CONTOURS = {
    1: [1.0, 1.0, 1.0, 1.0, 1.0],
    2: [0.2, 0.3, 0.5, 0.7, 0.9],
    3: [0.6, 0.35, 0.2, 0.35, 0.65],
    4: [0.9, 0.75, 0.55, 0.3, 0.1],
}

MATRIX_CSV = Path("benchmarking/results/canonical_contour_matrix.csv")
PERTURBATION_CSV = Path("benchmarking/results/tone_perturbation_test.csv")
TRACE_MD = Path("benchmarking/results/controlled_score_trace.md")
FORMULA_AUDIT_MD = Path("benchmarking/results/directional_tone_formula_audit.md")
PREDICTIONS_CSV = Path("benchmarking/results/controlled_tone_predictions.csv")


def _components(seg: np.ndarray) -> dict[str, float]:
    """The raw intermediate features every `_score_segment` branch reads
    from, computed once so STEP 2/3 can report them regardless of which
    tone-specific formula consumes them."""
    q = max(1, len(seg) // 4)
    s_mean = float(np.mean(seg[:q]))
    e_mean = float(np.mean(seg[-q:]))
    mid_seg = seg[q: len(seg) - q]
    mid_min = float(np.min(mid_seg)) if len(mid_seg) else float(np.min(seg))
    variance = float(np.var(seg))
    return {
        "s_mean": s_mean, "e_mean": e_mean, "mid_min": mid_min, "variance": variance,
        "rise": e_mean - s_mean, "fall": s_mean - e_mean,
        "dip_depth": (s_mean + e_mean) / 2.0 - mid_min,
    }


# ---------------------------------------------------------------------------
# STEP 2 -- canonical 4x4 matrix
# ---------------------------------------------------------------------------


def build_canonical_matrix() -> list[dict[str, Any]]:
    rows = []
    for produced_tone, contour in CANONICAL_CONTOURS.items():
        seg = np.array(contour)
        comps = _components(seg)
        smoothed = _smooth_for_directional_scoring(seg)
        smoothed_comps = _components(smoothed)
        for expected_tone in (1, 2, 3, 4):
            score, source = _score_segment(seg, expected_tone)
            smoothed_score, _ = _score_segment(smoothed, expected_tone)
            rows.append({
                "produced_tone": produced_tone,
                "expected_tone": expected_tone,
                "produced_contour": str(contour),
                "s_mean": round(comps["s_mean"], 4),
                "e_mean": round(comps["e_mean"], 4),
                "mid_min": round(comps["mid_min"], 4),
                "variance": round(comps["variance"], 4),
                "rise": round(comps["rise"], 4),
                "fall": round(comps["fall"], 4),
                "dip_depth": round(comps["dip_depth"], 4),
                "raw_score_unsmoothed": round(score, 2),
                "raw_score_after_5tap_median_smoothing": round(smoothed_score, 2),
                "provenance": source,
                "pass_at_58_unsmoothed": int(score >= THRESHOLD),
                "is_diagonal_matched_case": int(produced_tone == expected_tone),
            })
    return rows


def write_canonical_matrix(rows: list[dict[str, Any]], path: Path = MATRIX_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# STEP 3 -- perturbation sweeps, one property at a time
# ---------------------------------------------------------------------------


def _ramp(start: float, end: float, n: int = 5) -> list[float]:
    return list(np.linspace(start, end, n))


PERTURBATIONS: dict[int, list[tuple[str, list[float]]]] = {
    1: [
        ("flat_high", [1.0, 1.0, 1.0, 1.0, 1.0]),
        ("flat_mid", [0.5, 0.5, 0.5, 0.5, 0.5]),
        ("slightly_rising", _ramp(0.4, 0.6)),
        ("slightly_falling", _ramp(0.6, 0.4)),
        ("strongly_rising", _ramp(0.1, 0.9)),
        ("strongly_falling", _ramp(0.9, 0.1)),
    ],
    2: [
        ("flat", [0.5, 0.5, 0.5, 0.5, 0.5]),
        ("weak_rise", _ramp(0.4, 0.6)),
        ("moderate_rise", _ramp(0.3, 0.7)),
        ("strong_rise", _ramp(0.1, 0.9)),
        ("falling", _ramp(0.9, 0.1)),
    ],
    3: [
        ("low_flat", [0.2, 0.2, 0.2, 0.2, 0.2]),
        ("shallow_dip", [0.55, 0.45, 0.4, 0.45, 0.55]),
        ("deep_dip", [0.9, 0.3, 0.1, 0.3, 0.9]),
        ("rise_only", _ramp(0.1, 0.9)),
        ("fall_only", _ramp(0.9, 0.1)),
    ],
    4: [
        ("flat", [0.5, 0.5, 0.5, 0.5, 0.5]),
        ("weak_fall", _ramp(0.6, 0.4)),
        ("moderate_fall", _ramp(0.7, 0.3)),
        ("strong_fall", _ramp(0.9, 0.1)),
        ("rising", _ramp(0.1, 0.9)),
    ],
}

#: For each tone, the perturbation labels in the order they are EXPECTED to
#: monotonically increase score, if the formula behaves as intended for a
#: real, valid production of that tone. Declared before computing scores so
#: "does it behave monotonically" is a pre-specified check, not a post-hoc
#: story fit to whatever came out.
EXPECTED_MONOTONIC_ORDER: dict[int, list[str]] = {
    1: ["strongly_falling", "strongly_rising", "slightly_falling", "slightly_rising", "flat_mid", "flat_high"],
    2: ["falling", "flat", "weak_rise", "moderate_rise", "strong_rise"],
    3: ["rise_only", "fall_only", "low_flat", "shallow_dip", "deep_dip"],
    4: ["rising", "flat", "weak_fall", "moderate_fall", "strong_fall"],
}


def build_perturbation_table() -> list[dict[str, Any]]:
    rows = []
    for tone, variants in PERTURBATIONS.items():
        for label, contour in variants:
            seg = np.array(contour)
            comps = _components(seg)
            score, source = _score_segment(seg, tone)
            rows.append({
                "expected_tone": tone,
                "perturbation_label": label,
                "contour": str([round(v, 3) for v in contour]),
                "s_mean": round(comps["s_mean"], 4),
                "e_mean": round(comps["e_mean"], 4),
                "mid_min": round(comps["mid_min"], 4),
                "variance": round(comps["variance"], 4),
                "score": round(score, 2),
                "pass_at_58": int(score >= THRESHOLD),
                "provenance": source,
            })
    return rows


def write_perturbation_table(rows: list[dict[str, Any]], path: Path = PERTURBATION_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def check_monotonicity(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_tone: dict[int, dict[str, float]] = {}
    for row in rows:
        by_tone.setdefault(row["expected_tone"], {})[row["perturbation_label"]] = row["score"]
    results = {}
    for tone, order in EXPECTED_MONOTONIC_ORDER.items():
        scores = [by_tone[tone][label] for label in order]
        is_monotonic = all(scores[i] <= scores[i + 1] for i in range(len(scores) - 1))
        violations = [
            (order[i], order[i + 1], scores[i], scores[i + 1])
            for i in range(len(scores) - 1) if scores[i] > scores[i + 1]
        ]
        results[tone] = {"order": order, "scores": scores, "is_monotonic": is_monotonic, "violations": violations}
    return results


# ---------------------------------------------------------------------------
# STEP 4 -- score distribution / threshold audit on the REAL controlled test
# ---------------------------------------------------------------------------


def load_controlled_predictions(path: Path = PREDICTIONS_CSV) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def distribution_audit(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result = {}
    for tone in (1, 2, 3, 4):
        tone_rows = [r for r in rows if int(r["reference_tone"]) == tone]
        matched = [float(r["current_score"]) for r in tone_rows if r["expected_tone_correct"] == "1"]
        mismatched = [float(r["current_score"]) for r in tone_rows if r["expected_tone_correct"] == "0"]
        all_scores = matched + mismatched
        result[tone] = {
            "n": len(tone_rows),
            "min": min(all_scores) if all_scores else None,
            "median": float(np.median(all_scores)) if all_scores else None,
            "max": max(all_scores) if all_scores else None,
            "matched_scores": sorted(matched),
            "mismatched_scores": sorted(mismatched),
            "matched_all_below_58": all(s < THRESHOLD for s in matched) if matched else None,
            "matched_min": min(matched) if matched else None,
            "matched_max": max(matched) if matched else None,
            "mismatched_min": min(mismatched) if mismatched else None,
            "mismatched_max": max(mismatched) if mismatched else None,
            "ranges_overlap": (
                max(matched) >= min(mismatched) if matched and mismatched else None
            ),
        }
    return result


# ---------------------------------------------------------------------------
# STEP 5 -- trace two real examples per tone
# ---------------------------------------------------------------------------


def _trace_one_case(row: dict[str, Any]) -> dict[str, Any]:
    """Traces the ACTUAL production call chain via interception, not a
    reimplementation of it.

    An earlier version of this function reconstructed the pipeline by hand
    (`extract_pitch` on the whole file -> `normalize_pitch_contour` ->
    `_smooth_for_directional_scoring` -> `_score_segment`), and its scores
    disagreed with `controlled_tone_predictions.csv`'s recorded
    `current_score` by 20-50 points in several cases. Root cause:
    `estimate_word_prosody` (praat_analyzer.py) does not normalize the
    *whole* pitch contour -- it slices out this word's own aligned time
    span, then additionally skips the first 12% of that span
    ("coarticulation onset skip", praat_analyzer.py's `_ONSET_SKIP`)
    *before* ever calling `normalize_pitch_contour`. Reimplementing that
    windowing by hand risks exactly this kind of silent mismatch, so this
    version instead monkeypatches `chinese_tones.normalize_pitch_contour`
    and `chinese_tones._score_segment` to record their real arguments and
    return values while `analyze_all` runs for real, then reports the
    LAST captured call (there is exactly one Chinese character/token in
    each controlled-test file, so exactly one call is expected) --
    guaranteeing this trace shows what production actually computed, not
    an approximation of it.
    """
    import chinese_tones
    from benchmarking.ompal_runner import flatten_characters
    from praat_analyzer import analyze_all as _analyze_all

    audio_path = row["audio_file"]
    reference_character = row["reference_character"]

    normalize_calls: list[tuple[list, np.ndarray]] = []
    score_calls: list[tuple[np.ndarray, int, float, str]] = []

    real_normalize = chinese_tones.normalize_pitch_contour
    real_score_segment = chinese_tones._score_segment

    def _spy_normalize(pitch_contour, *args, **kwargs):
        result = real_normalize(pitch_contour, *args, **kwargs)
        normalize_calls.append((list(pitch_contour), np.array(result)))
        return result

    def _spy_score_segment(seg, tone):
        score, source = real_score_segment(seg, tone)
        score_calls.append((np.array(seg), tone, score, source))
        return score, source

    chinese_tones.normalize_pitch_contour = _spy_normalize
    chinese_tones._score_segment = _spy_score_segment
    try:
        (
            _pitch_contour, _formants, _speech_rate, _fluency, _pitch_stats,
            word_prosody, _detected_tone, _tone_accuracy, _feedback, _pause,
        ) = _analyze_all(audio_path, reference_character)
    finally:
        chinese_tones.normalize_pitch_contour = real_normalize
        chinese_tones._score_segment = real_score_segment

    characters = flatten_characters(word_prosody)
    recorded_score = characters[0]["score"] if characters else None

    if not score_calls:
        return {
            "case_id": row["case_id"], "audio_character": row["audio_character"],
            "audio_tone": row["audio_tone"], "reference_character": reference_character,
            "reference_tone": int(row["reference_tone"]), "expected_tone_correct": row["expected_tone_correct"],
            "n_raw_pitch_frames": 0, "f0_hz_first5": [], "f0_hz_last5": [],
            "normalized_first5": [], "normalized_last5": [], "smoothed_first5": [], "smoothed_last5": [],
            "s_mean": None, "e_mean": None, "mid_min": None, "variance": None,
            "rise": None, "fall": None, "dip_depth": None,
            "final_score": None, "provenance": "not_judged_no_scoring_call",
            "verdict": "FAIL", "recorded_current_score": recorded_score,
        }

    # The captured `seg` in the LAST score call is already normalized AND
    # smoothed (that's what `_score_segment` receives in the real pipeline),
    # so recompute components directly from it -- no separate smoothing step
    # needed here since it already happened inside the real call.
    scoring_input_raw, normalized_full = normalize_calls[-1]
    seg, applied_tone, score, source = score_calls[-1]
    comps = _components(seg)

    return {
        "case_id": row["case_id"],
        "audio_character": row["audio_character"],
        "audio_tone": row["audio_tone"],
        "reference_character": reference_character,
        "reference_tone": int(row["reference_tone"]),
        "expected_tone_correct": row["expected_tone_correct"],
        "scored_against_tone": applied_tone,
        "n_scoring_frames": len(scoring_input_raw),
        # `scoring_input_raw` is what `estimate_word_prosody` actually fed to
        # `normalize_pitch_contour` -- this word's own aligned time span,
        # with the first 12% (coarticulation onset) already skipped. NOT the
        # same as the raw whole-file contour.
        "f0_hz_first5": [round(f, 1) for _, f in scoring_input_raw[:5]],
        "f0_hz_last5": [round(f, 1) for _, f in scoring_input_raw[-5:]],
        "normalized_first5": [round(float(v), 3) for v in normalized_full[:5]] if len(normalized_full) else [],
        "normalized_last5": [round(float(v), 3) for v in normalized_full[-5:]] if len(normalized_full) else [],
        "smoothed_first5": [round(float(v), 3) for v in seg[:5]] if len(seg) else [],
        "smoothed_last5": [round(float(v), 3) for v in seg[-5:]] if len(seg) else [],
        "s_mean": round(comps.get("s_mean", 0), 4),
        "e_mean": round(comps.get("e_mean", 0), 4),
        "mid_min": round(comps.get("mid_min", 0), 4),
        "variance": round(comps.get("variance", 0), 4),
        "rise": round(comps.get("rise", 0), 4),
        "fall": round(comps.get("fall", 0), 4),
        "dip_depth": round(comps.get("dip_depth", 0), 4),
        "final_score": round(score, 2),
        "provenance": source,
        "verdict": "PASS" if score >= THRESHOLD else "FAIL",
        "recorded_current_score": row["current_score"],
        # The recorded CSV value is itself rounded to 1 decimal place inside
        # praat_analyzer.py's own per-syllable score storage, so compare at
        # that same precision rather than full float precision.
        "matches_recorded_score": abs(round(score, 1) - round(float(row["current_score"]), 1)) < 0.15,
    }


def select_trace_examples(rows: list[dict[str, Any]]) -> dict[int, dict[str, dict[str, Any]]]:
    """One matched + one mismatched case per tone -- the first one found for
    each, so the selection is deterministic and not cherry-picked for
    effect."""
    selected: dict[int, dict[str, dict[str, Any]]] = {}
    for tone in (1, 2, 3, 4):
        tone_rows = [r for r in rows if int(r["reference_tone"]) == tone]
        matched = next((r for r in tone_rows if r["expected_tone_correct"] == "1"), None)
        mismatched = next((r for r in tone_rows if r["expected_tone_correct"] == "0"), None)
        selected[tone] = {
            "matched": _trace_one_case(matched) if matched else None,
            "mismatched": _trace_one_case(mismatched) if mismatched else None,
        }
    return selected


if __name__ == "__main__":
    from benchmarking import report_directional_tone_diagnosis

    matrix_rows = build_canonical_matrix()
    write_canonical_matrix(matrix_rows)

    perturbation_rows = build_perturbation_table()
    write_perturbation_table(perturbation_rows)
    monotonicity = check_monotonicity(perturbation_rows)

    predictions = load_controlled_predictions()
    distribution = distribution_audit(predictions)
    traces = select_trace_examples(predictions)

    report_directional_tone_diagnosis.write_trace_report(traces, TRACE_MD)
    report_directional_tone_diagnosis.append_classification_section(
        FORMULA_AUDIT_MD, matrix_rows, monotonicity, distribution,
    )
    print(f"Canonical matrix written to {MATRIX_CSV}")
    print(f"Perturbation table written to {PERTURBATION_CSV}")
    print(f"Trace report written to {TRACE_MD}")
    print(f"Classification appended to {FORMULA_AUDIT_MD}")
