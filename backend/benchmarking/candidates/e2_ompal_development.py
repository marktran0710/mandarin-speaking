"""Candidate E2 — FIRST OMPAL evaluation (DEVELOPMENT split only).

    python -m benchmarking.candidates.e2_ompal_development

**Candidate E2 and Candidate E V1 are frozen** (`context_aware_contour_scorer.py`,
`contour_scorer_v2.py` — imported read-only, never edited here). **`tone_context.py`
is imported read-only.** No threshold is tuned in this module: Baseline A and
Candidate E V1 keep their pre-existing fixed threshold of 58 (the same constant
every prior controlled-test report in this line of candidates already used —
not selected from OMPAL data); Candidate B1/C1 keep their own dev-only,
out-of-fold threshold-selection rule (`praat_logistic._select_threshold`,
already frozen before this task); Candidate E2 gets NO threshold anywhere in
this module — every E2 number is either an AUC (rank-based, threshold-free) or
a raw score distribution, per the task's explicit instruction not to invent one.

**`final_test` is not referenced anywhere in this module.** Row loading is
delegated entirely to `benchmarking.candidates.praat_logistic.load_split_rows`,
which refuses that partition without both of its independent gates — this
module never passes `unlock_final_test=True`. `validation` is also never
loaded here (unlike `label_audit.py`, which evaluates validation) — this task
is DEVELOPMENT only.

## What's new here vs. every prior OMPAL evaluation in this project

Candidate E V1 and Candidate E2 have never been run on real OMPAL audio
before this task — both were developed and frozen using only canonical
reasoning and controlled synthetic speech. This module is the first time
either one sees a real learner recording. For every judged development
character it:

1. Loads the character's parent utterance (`benchmarking.ompal_corpus.
   load_utterances`) for the full transcript text.
2. Computes the WHOLE utterance's `tone_context.ExpectedTone` plan
   (`benchmarking.label_audit._utterance_plan`, reused read-only — the same
   function, and the same (audio_id, syllable_index) keying convention,
   `ompal_label_methodological_audit.md` already established and tested for
   validation; here applied to development for the first time).
3. Re-derives the utterance's real per-syllable alignment spans using the
   SAME aligner function `diagnostics.py` already used to build
   `duration_seconds`/`alignment_start`/`alignment_end` in
   `human_vs_system_diagnostics.csv` (`diagnostics._syllable_spans`, imported
   read-only) — not a new alignment method.
4. Extracts that one syllable's own pitch frames, normalizes and smooths them
   exactly the way the T3-context-audit precedent did for controlled audio
   (`chinese_tones.normalize_pitch_contour` then `_smooth_for_directional_
   scoring`, per-syllable, not per-word) — deliberately the same normalization
   granularity Candidate E V1/E2's own controlled evaluation already used, so
   this is not a new scoring convention invented for OMPAL.
5. Scores that segment with Candidate E V1's frozen `score_segment_v2` (against
   the bare underlying tone, no context) and Candidate E2's frozen
   `score_segment_e2` (against the full `ExpectedTone`).

Candidate B1 and C1 are re-run on the SAME development row set via their own
already-frozen, already-published pipelines (`praat_logistic.run_grouped_cv`,
`wav2vec_frozen_logistic`), reporting their honest out-of-fold estimate — the
same quantity `compare_abc.py`'s "Development" section already reports, not a
new evaluation convention.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

import chinese_tones
from benchmarking.candidates.contour_scorer_v2 import score_segment_v2
from benchmarking.candidates.context_aware_contour_scorer import score_segment_e2
from benchmarking.candidates.praat_logistic import (
    TONES,
    _group_by_tone,
    _labels,
    _select_threshold,
    _usable,
    load_split_rows,
    run_grouped_cv as praat_run_grouped_cv,
)
from benchmarking.candidates.wav2vec_frozen_logistic import (
    _group_rows_and_embeddings_by_tone,
    build_embeddings,
    select_pca_dimension as wav2vec_select_pca_dimension,
)
from benchmarking.error_analysis import NA
from benchmarking.label_audit import _utterance_plan
from benchmarking.ompal_corpus import load_utterances
from benchmarking.stats import binary_agreement, roc_auc
from benchmarking.diagnostics import _frames_in_span, _syllable_spans
from praat_analyzer import _intensity_contour_from_sound, _load_sound, _pitch_contour_from_sound

CORPUS_ROOT = Path("private-data/ompal")

#: Same fixed constant every prior Candidate-E controlled-test report already
#: used for Baseline A / Candidate E V1 pass/fail (`contour_scorer_v2_pipeline.
#: THRESHOLD`). Not selected from any OMPAL number; kept here only so this
#: module does not need to import a `candidates` pipeline module for one
#: float.
FIXED_THRESHOLD = 58.0

PREDICTIONS_CSV = Path("benchmarking/results/candidate_e2_development_predictions.csv")
FALSE_REJECTION_CSV = Path("benchmarking/results/candidate_e2_development_false_rejection.csv")
FALSE_ACCEPTANCE_CSV = Path("benchmarking/results/candidate_e2_development_false_acceptance.csv")
REPORT_MD = Path("benchmarking/results/candidate_e2_ompal_development.md")
COMPARISON_MD = Path("benchmarking/results/candidate_abce2_development_comparison.md")

T3_CATEGORY_LABELS = {
    "A_full_third": "A. full_third",
    "B_half_third": "B. half_third",
    "C_t3_t3_to_t2": "C. T3_T3 -> surface T2",
    "D_chain_multi_accept": "D. third-tone chain / multiple accepted alternatives",
    "E_other_unresolved": "E. other / unresolved",
}


# ---------------------------------------------------------------------------
# STEP 1 -- run Candidate E V1 and Candidate E2 on development, for the
# first time, against real OMPAL audio.
# ---------------------------------------------------------------------------


def _na_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "audio_id": row["audio_id"],
        "syllable_index": row["syllable_index"],
        "speaker_id": row["speaker_id"],
        "character": row["word"],
        "underlying_tone": int(row["expected_tone"]),
        "planner_rule": NA,
        "accepted_surface_tones": NA,
        "realization_category": NA,
        "t3_context_category": NA,
        "e2_score": None,
        "e2_provenance": NA,
        "e2_matched_tone": NA,
        "e1_score": None,
        "e1_provenance": NA,
        "e1_pass": None,
        "e2_exclusion_reason": reason,
        "baseline_a_score": _float_or_none(row.get("system_character_score")),
        "baseline_a_pass": _int_or_none(row.get("system_tone_correct")),
        "human_majority_tone_correct": _int_or_none(row.get("human_majority_tone_correct")),
        "individual_rater_labels": row.get("individual_rater_labels", NA),
        "duration_seconds": _float_or_none(row.get("duration_seconds")),
        "voiced_fraction": _float_or_none(row.get("voiced_fraction")),
        "alignment_start": _float_or_none(row.get("alignment_start")),
        "alignment_end": _float_or_none(row.get("alignment_end")),
        "f0_mean": row.get("f0_mean", NA),
        "f0_range": row.get("f0_range", NA),
        "f0_slope_full": row.get("f0_slope_full", NA),
        "utterance_final": None,
        "boundary_after": None,
    }


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "NA"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", "NA"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _t3_context_category(realization: str, rule: str, accepted_surface_tones: tuple[int, ...]) -> str:
    if realization == "full_third":
        return "A_full_third"
    if realization == "half_third":
        return "B_half_third"
    if realization == "third_tone_sandhi" and accepted_surface_tones == (2,):
        return "C_t3_t3_to_t2"
    if realization == "third_tone_chain" or len(accepted_surface_tones) > 1:
        return "D_chain_multi_accept"
    return "E_other_unresolved"


def run_e1_e2_on_development(dev_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Step 1's core loop. Returns (rows, diagnostics)."""
    utterances = {u.utterance_id: u for u in load_utterances(CORPUS_ROOT)}
    rows_by_audio: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dev_rows:
        rows_by_audio[row["audio_id"]].append(row)

    diag = {
        "utterances_total": len(rows_by_audio),
        "utterances_ok": 0,
        "utterances_not_found": 0,
        "utterances_plan_failed": 0,
        "utterances_audio_load_error": 0,
        "utterances_span_unavailable": 0,
        "rows_scored": 0,
        "rows_excluded": 0,
        "rows_span_duration_mismatch": 0,
    }

    out_rows: list[dict[str, Any]] = []
    for audio_id, rows in rows_by_audio.items():
        utterance = utterances.get(audio_id)
        if utterance is None:
            diag["utterances_not_found"] += 1
            diag["rows_excluded"] += len(rows)
            out_rows.extend(_na_row(row, "utterance_not_found") for row in rows)
            continue

        han_chars, _lexical_lengths, plan = _utterance_plan(utterance.text)
        if plan is None or len(plan) != len(han_chars):
            diag["utterances_plan_failed"] += 1
            diag["rows_excluded"] += len(rows)
            out_rows.extend(_na_row(row, "plan_failed") for row in rows)
            continue

        try:
            sound = _load_sound(str(utterance.wav_path))
            raw_contour = _pitch_contour_from_sound(sound)
            intensity = _intensity_contour_from_sound(sound)
        except Exception:  # noqa: BLE001 - recorded, run continues
            diag["utterances_audio_load_error"] += 1
            diag["rows_excluded"] += len(rows)
            out_rows.extend(_na_row(row, "audio_load_error") for row in rows)
            continue

        spans = _syllable_spans(raw_contour, utterance.text, intensity)
        if spans is None or len(spans) != len(han_chars):
            diag["utterances_span_unavailable"] += 1
            diag["rows_excluded"] += len(rows)
            out_rows.extend(_na_row(row, "span_unavailable") for row in rows)
            continue

        diag["utterances_ok"] += 1
        for row in rows:
            i = int(row["syllable_index"])
            if i >= len(plan) or i >= len(spans):
                diag["rows_excluded"] += 1
                out_rows.append(_na_row(row, "index_out_of_range"))
                continue
            expected = plan[i]
            if han_chars[i] != row["word"] or expected.underlying_tone != int(row["expected_tone"]):
                diag["rows_excluded"] += 1
                out_rows.append(_na_row(row, "char_or_tone_mismatch"))
                continue

            start, end = spans[i]
            cached_duration = _float_or_none(row.get("duration_seconds"))
            if cached_duration is not None and abs((end - start) - cached_duration) > 0.005:
                diag["rows_span_duration_mismatch"] += 1

            frames = _frames_in_span(raw_contour, start, end)
            normalized = chinese_tones.normalize_pitch_contour(frames)
            seg = chinese_tones._smooth_for_directional_scoring(normalized)

            e1_score, e1_prov = score_segment_v2(seg, expected.underlying_tone)
            e2_score, e2_prov, e2_matched = score_segment_e2(seg, expected)

            out_rows.append({
                "audio_id": row["audio_id"],
                "syllable_index": row["syllable_index"],
                "speaker_id": row["speaker_id"],
                "character": row["word"],
                "underlying_tone": int(row["expected_tone"]),
                "planner_rule": expected.rule or "none",
                "accepted_surface_tones": str(expected.accepted_surface_tones),
                "realization_category": expected.realization,
                "t3_context_category": (
                    _t3_context_category(expected.realization, expected.rule or "none", expected.accepted_surface_tones)
                    if int(row["expected_tone"]) == 3 else NA
                ),
                "e2_score": round(float(e2_score), 3),
                "e2_provenance": e2_prov,
                "e2_matched_tone": e2_matched,
                "e1_score": round(float(e1_score), 3),
                "e1_provenance": e1_prov,
                "e1_pass": int(e1_score >= FIXED_THRESHOLD),
                "e2_exclusion_reason": "",
                "baseline_a_score": _float_or_none(row.get("system_character_score")),
                "baseline_a_pass": _int_or_none(row.get("system_tone_correct")),
                "human_majority_tone_correct": _int_or_none(row.get("human_majority_tone_correct")),
                "individual_rater_labels": row.get("individual_rater_labels", NA),
                "duration_seconds": _float_or_none(row.get("duration_seconds")),
                "voiced_fraction": _float_or_none(row.get("voiced_fraction")),
                "alignment_start": round(start, 4),
                "alignment_end": round(end, 4),
                "f0_mean": row.get("f0_mean", NA),
                "f0_range": row.get("f0_range", NA),
                "f0_slope_full": row.get("f0_slope_full", NA),
                "utterance_final": bool(i == len(han_chars) - 1),
                "boundary_after": bool(expected.boundary_after),
            })
            diag["rows_scored"] += 1
    return out_rows, diag


# ---------------------------------------------------------------------------
# Candidate B1 / C1 on the SAME development rows, out-of-fold (no leakage)
# ---------------------------------------------------------------------------


def run_b1_oof(dev_rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], float], dict[str, float]]:
    dev_by_tone = _group_by_tone(dev_rows)
    cv = praat_run_grouped_cv(dev_by_tone)
    thresholds = {
        tone: _select_threshold(cv["oof"][tone]["probabilities"], cv["oof"][tone]["labels"])
        for tone in TONES
    }
    oof_by_key: dict[tuple[str, str], float] = {}
    for tone in TONES:
        for row, prob in zip(dev_by_tone[tone], cv["oof"][tone]["probabilities"]):
            if not np.isnan(prob):
                oof_by_key[(row["audio_id"], row["syllable_index"])] = float(prob)
    return oof_by_key, thresholds


def run_c1_oof(dev_rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], float], dict[str, float], int]:
    matrix, valid_mask, missing, _encoder = build_embeddings(dev_rows, "development")
    usable_rows = [row for row, ok in zip(dev_rows, valid_mask) if ok]
    usable_matrix = matrix[valid_mask]
    dev_by_tone, dev_embeddings_by_tone = _group_rows_and_embeddings_by_tone(usable_rows, usable_matrix)
    _pca_dim, _grid, cv = wav2vec_select_pca_dimension(dev_by_tone, dev_embeddings_by_tone)
    thresholds = {
        tone: _select_threshold(cv["oof"][tone]["probabilities"], cv["oof"][tone]["labels"])
        for tone in TONES
    }
    oof_by_key: dict[tuple[str, str], float] = {}
    for tone in TONES:
        for row, prob in zip(dev_by_tone[tone], cv["oof"][tone]["probabilities"]):
            if not np.isnan(prob):
                oof_by_key[(row["audio_id"], row["syllable_index"])] = float(prob)
    return oof_by_key, thresholds, missing


# ---------------------------------------------------------------------------
# Merge everything onto one master development row set, keyed by
# (audio_id, syllable_index) -- unique per row, avoids the positional-
# alignment fragility `label_audit.build_master_rows` had to guard against.
# ---------------------------------------------------------------------------


def build_master_rows(
    e_rows: list[dict[str, Any]],
    b1_oof: dict[tuple[str, str], float],
    b1_thresholds: dict[str, float],
    c1_oof: dict[tuple[str, str], float],
    c1_thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    """Attach Candidate B1/C1's out-of-fold probability (and dev-selected
    threshold's pass/fail) onto each Step-1 row, keyed by the same
    (audio_id, syllable_index) pair `run_e1_e2_on_development` already
    carries -- unique per row, so this is a plain dict lookup rather than a
    positional zip that could silently misalign (see `label_audit.
    build_master_rows`'s docstring for why that matters, and why this module
    avoids the problem entirely by keeping a real key throughout instead)."""
    master = []
    for row in e_rows:
        key = (row["audio_id"], row["syllable_index"])
        tone = str(row["underlying_tone"])
        b1_prob = b1_oof.get(key)
        c1_prob = c1_oof.get(key)
        merged = dict(row)
        merged["b1_probability"] = b1_prob
        merged["b1_pass"] = int(b1_prob >= b1_thresholds[tone]) if b1_prob is not None and tone in b1_thresholds else None
        merged["c1_probability"] = c1_prob
        merged["c1_pass"] = int(c1_prob >= c1_thresholds[tone]) if c1_prob is not None and tone in c1_thresholds else None
        master.append(merged)
    return master


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _auc_for(scores: list[float], labels: list[int]) -> float | None:
    pairs = [(s, bool(l)) for s, l in zip(scores, labels) if s is not None and l is not None]
    if not pairs:
        return None
    return roc_auc([p[0] for p in pairs], [p[1] for p in pairs])


def _binary_for(preds: list[int | None], labels: list[int]) -> dict[str, Any]:
    pairs = [(bool(p), bool(l)) for p, l in zip(preds, labels) if p is not None and l is not None]
    if not pairs:
        return {"n": 0}
    metrics = binary_agreement([p[0] for p in pairs], [p[1] for p in pairs])
    return metrics


def score_distribution(scores: list[float]) -> dict[str, Any]:
    scores = [s for s in scores if s is not None]
    if not scores:
        return {"n": 0, "min": None, "median": None, "max": None}
    arr = np.array(scores, dtype=float)
    return {
        "n": len(arr),
        "min": round(float(arr.min()), 2),
        "median": round(float(np.median(arr)), 2),
        "max": round(float(arr.max()), 2),
    }


def _human_correct_rate(rows: list[dict[str, Any]]) -> float | None:
    labels = [row["human_majority_tone_correct"] for row in rows if row["human_majority_tone_correct"] is not None]
    return (sum(labels) / len(labels)) if labels else None


# ---------------------------------------------------------------------------
# STEP 8 -- HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET (reuses the pre-existing,
# already-frozen definition from `label_audit.meets_high_confidence_criteria`
# -- defined before any of this task's E2 numbers existed, for validation;
# applied here to development for the first time. Not redefined here.)
# ---------------------------------------------------------------------------


def high_confidence_keys(dev_rows_raw: list[dict[str, Any]]) -> set[tuple[str, str]]:
    from benchmarking.label_audit import attach_lexical_and_sandhi, meets_high_confidence_criteria

    rows = [dict(row) for row in dev_rows_raw]
    attach_lexical_and_sandhi(rows)
    return {
        (row["audio_id"], row["syllable_index"])
        for row in rows
        if meets_high_confidence_criteria(row)
    }


# ---------------------------------------------------------------------------
# STEP 9 -- error export
# ---------------------------------------------------------------------------

ERROR_EXPORT_FIELDS = [
    "audio_id", "speaker_id", "character", "underlying_tone", "planner_rule",
    "accepted_surface_tones", "realization_category", "e2_score",
    "human_majority_tone_correct", "individual_rater_labels",
    "duration_seconds", "voiced_fraction", "alignment_start", "alignment_end",
    "f0_mean", "f0_range", "f0_slope_full",
]


def write_error_csv(rows: list[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ERROR_EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


#: E2 has no frozen threshold (see module docstring), so "false rejection" /
#: "false acceptance" for the E2-specific error export uses the SAME fixed
#: 58 constant every other candidate in this line already uses for exactly
#: this kind of descriptive triage — never adopted as E2's deployment
#: threshold, only as a fixed, pre-existing cut point to decide which rows
#: are interesting enough to export for manual review.
def false_rejection_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row["e2_score"] is not None
        and row["human_majority_tone_correct"] == 1
        and row["e2_score"] < FIXED_THRESHOLD
    ]


def false_acceptance_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row["e2_score"] is not None
        and row["human_majority_tone_correct"] == 0
        and row["e2_score"] >= FIXED_THRESHOLD
    ]


# ---------------------------------------------------------------------------
# Predictions CSV (Step 1 deliverable)
# ---------------------------------------------------------------------------

PREDICTIONS_FIELDS = [
    "audio_id", "speaker_id", "character", "underlying_tone",
    "planner_rule", "accepted_surface_tones", "realization_category",
    "t3_context_category", "utterance_final", "boundary_after",
    "e2_score", "e2_provenance", "e2_matched_tone",
    "e1_score", "e1_provenance", "e1_pass",
    "baseline_a_score", "baseline_a_pass",
    "b1_probability", "b1_pass", "c1_probability", "c1_pass",
    "human_majority_tone_correct", "individual_rater_labels",
    "e2_exclusion_reason",
]


def write_predictions_csv(rows: list[dict[str, Any]], path: Path = PREDICTIONS_CSV) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTIONS_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    print("Loading development split rows...")
    dev_rows_raw = load_split_rows("development")
    dev_rows, _excluded = _usable(dev_rows_raw)
    print(f"  {len(dev_rows)} usable development rows across "
          f"{len({r['audio_id'] for r in dev_rows})} utterances")

    print("STEP 1: running Candidate E V1 + Candidate E2 on real OMPAL audio (development)...")
    e_rows, e_diag = run_e1_e2_on_development(dev_rows)
    print(f"  scored {e_diag['rows_scored']} rows, excluded {e_diag['rows_excluded']} "
          f"({e_diag['utterances_ok']}/{e_diag['utterances_total']} utterances usable)")

    print("STEP 2: Candidate B1 out-of-fold on development...")
    b1_oof, b1_thresholds = run_b1_oof(dev_rows)
    print("STEP 2: Candidate C1 out-of-fold on development (cached embeddings)...")
    c1_oof, c1_thresholds, c1_missing_embeddings = run_c1_oof(dev_rows)

    master = build_master_rows(e_rows, b1_oof, b1_thresholds, c1_oof, c1_thresholds)

    print("STEP 8: high-confidence subset...")
    hc_keys = high_confidence_keys(dev_rows_raw)
    for row in master:
        row["high_confidence_subset"] = (row["audio_id"], row["syllable_index"]) in hc_keys

    n_written = write_predictions_csv(master)

    fr_rows = false_rejection_rows(master)
    fa_rows = false_acceptance_rows(master)
    n_fr = write_error_csv(fr_rows, FALSE_REJECTION_CSV)
    n_fa = write_error_csv(fa_rows, FALSE_ACCEPTANCE_CSV)

    return {
        "dev_n": len(dev_rows),
        "e_diag": e_diag,
        "c1_missing_embeddings": c1_missing_embeddings,
        "master": master,
        "n_predictions_written": n_written,
        "n_false_rejection_written": n_fr,
        "n_false_acceptance_written": n_fa,
    }


if __name__ == "__main__":
    from benchmarking.candidates import report_e2_ompal_development as report

    result = run()
    report.write_reports(result)
    print(f"Predictions written to {PREDICTIONS_CSV} ({result['n_predictions_written']} rows)")
    print(f"False rejection export: {FALSE_REJECTION_CSV} ({result['n_false_rejection_written']} rows)")
    print(f"False acceptance export: {FALSE_ACCEPTANCE_CSV} ({result['n_false_acceptance_written']} rows)")
    print(f"Reports written to {REPORT_MD} and {COMPARISON_MD}")
