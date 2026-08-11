"""OMPAL label / methodological audit (Q1-Q8) — existing predictions only.

    python -m benchmarking.label_audit

No model is trained or tuned here. No production code is touched. final_test
is never loaded (this module never imports anything from `praat_logistic`
with `unlock_final_test=True`, and never references the string
"final_test" as a value passed to `load_split_rows`). Every AUC/accuracy
number below is computed from three already-frozen sources:

- Baseline A: `system_tone_correct` / `system_character_score` columns
  already present in `human_vs_system_diagnostics.csv` (frozen threshold 58,
  never touched here).
- Candidate B1: `benchmarking/results/candidate_b_validation_predictions.csv`
  (frozen thresholds baked into `candidate_b_predicted_correct`).
- Candidate C1: `benchmarking/results/candidate_c_validation_predictions.csv`
  (frozen thresholds baked into `candidate_c_predicted_correct`).

This module reads those three files and slices them into subsets; it never
re-fits, re-thresholds, or re-scores anything.

Answers Q1 (label unit) and Q5 (sandhi flagging) by calling the SAME
production sandhi logic already used for live scoring diagnostics
(`tone_context.plan_expected_tones`, `chinese_tones.word_tones`) rather than
inventing a new heuristic -- read-only reuse, no production file is edited.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

import jieba

from benchmarking.baseline_a import evaluate as evaluate_baseline_a
from benchmarking.candidates.praat_logistic import TONES, _group_by_tone, _usable, load_split_rows
from benchmarking.ompal_corpus import load_utterances
from benchmarking.stats import binary_agreement, roc_auc
from chinese_tones import word_tones
from tone_context import (
    RULE_BU,
    RULE_NEUTRAL_LEXICAL,
    RULE_NEUTRAL_OPTIONAL,
    RULE_T3_CHAIN,
    RULE_T3_T3,
    RULE_YI,
    _is_han,
    han_break_flags,
    plan_expected_tones,
)

CORPUS_ROOT = Path("private-data/ompal")
B_PREDICTIONS_CSV = Path("benchmarking/results/candidate_b_validation_predictions.csv")
C_PREDICTIONS_CSV = Path("benchmarking/results/candidate_c_validation_predictions.csv")

REPORT_PATH = Path("benchmarking/results/ompal_label_methodological_audit.md")
HIGH_CONFIDENCE_CSV = Path("benchmarking/results/ompal_high_confidence_subset.csv")
SANDHI_CSV = Path("benchmarking/results/ompal_sandhi_audit.csv")

#: Q5's requested taxonomy, mapped from `tone_context`'s rule identifiers.
SANDHI_STATUS_MAP = {
    RULE_T3_T3: "T3_sandhi_candidate",
    RULE_T3_CHAIN: "T3_sandhi_candidate",
    RULE_YI: "yi_sandhi_candidate",
    RULE_BU: "bu_sandhi_candidate",
    RULE_NEUTRAL_LEXICAL: "neutral_or_other",
    RULE_NEUTRAL_OPTIONAL: "neutral_or_other",
    None: "stable",
}


# ---------------------------------------------------------------------------
# Reconstruct the exact validation row set + order Candidate B1/C1 evaluated
# ---------------------------------------------------------------------------


def build_master_rows() -> list[dict[str, Any]]:
    """Merge Baseline A (already in the diagnostics rows), Candidate B1, and
    Candidate C1 predictions onto one row per validation syllable.

    Candidate B1 and C1's prediction CSVs don't carry `syllable_index`, so
    they can't be value-joined unambiguously (the same character can recur
    in one sentence). Instead this replays the exact same deterministic
    construction `praat_logistic.evaluate_validation_once` /
    `wav2vec_frozen_logistic.evaluate_validation_once` used --
    `load_split_rows("validation")` -> `_usable` -> `_group_by_tone` ->
    flatten by tone -- which is provably the same order the two prediction
    CSVs were written in, then verifies that alignment row-by-row rather
    than assuming it.
    """
    val_rows_raw = load_split_rows("validation")
    val_rows, _ = _usable(val_rows_raw)
    val_by_tone = _group_by_tone(val_rows)
    ordered: list[dict[str, Any]] = []
    for tone in TONES:
        ordered.extend(val_by_tone[tone])

    with B_PREDICTIONS_CSV.open(encoding="utf-8") as handle:
        b_preds = list(csv.DictReader(handle))
    with C_PREDICTIONS_CSV.open(encoding="utf-8") as handle:
        c_preds = list(csv.DictReader(handle))

    if not (len(ordered) == len(b_preds) == len(c_preds)):
        raise RuntimeError(
            f"Row count mismatch: diagnostics={len(ordered)} B1={len(b_preds)} "
            f"C1={len(c_preds)} -- cannot safely align predictions positionally."
        )

    master: list[dict[str, Any]] = []
    for i, (row, bp, cp) in enumerate(zip(ordered, b_preds, c_preds)):
        if not (
            row["audio_id"] == bp["audio_id"] == cp["audio_id"]
            and row["expected_tone"] == bp["expected_tone"] == cp["expected_tone"]
        ):
            raise RuntimeError(
                f"Row {i} misaligned: diagnostics={row['audio_id']}/{row['expected_tone']} "
                f"B1={bp['audio_id']}/{bp['expected_tone']} "
                f"C1={cp['audio_id']}/{cp['expected_tone']}"
            )
        merged = dict(row)
        merged["candidate_b_probability"] = bp["candidate_b_probability"]
        merged["candidate_b_predicted_correct"] = bp["candidate_b_predicted_correct"]
        merged["candidate_c_probability"] = cp["candidate_c_probability"]
        merged["candidate_c_predicted_correct"] = cp["candidate_c_predicted_correct"]
        master.append(merged)
    return master


# ---------------------------------------------------------------------------
# Q1 / Q5: per-utterance sandhi plan + lexical (jieba) word length
# ---------------------------------------------------------------------------


def _utterance_plan(text: str) -> tuple[list[str], list[int], list | None]:
    """One utterance's Han-character sequence, each character's jieba-token
    length (the "lexical word" length Q2/Q3 need), and `tone_context`'s
    sandhi plan for that sequence -- the exact function the live scorer's
    diagnostic path already uses, called read-only here."""
    han_chars = [c for c in text if _is_han(c)]
    tokens = jieba.lcut(text)

    token_indices: list[int] = []
    lexical_lengths: list[int] = []
    for token_index, token in enumerate(tokens):
        token_han_chars = [c for c in token if _is_han(c)]
        for _ in token_han_chars:
            token_indices.append(token_index)
            lexical_lengths.append(len(token_han_chars))

    underlying_tones = [word_tones(c)[0] for c in han_chars]
    breaks = han_break_flags(text)
    try:
        plan = plan_expected_tones(han_chars, underlying_tones, token_indices, breaks)
    except Exception:
        plan = None
    return han_chars, lexical_lengths, plan


def build_sandhi_and_lexical_tables(
    audio_ids: set[str],
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], int], list[str]]:
    """For every utterance touched by `audio_ids`, compute a per-character
    sandhi status and lexical-word length, keyed by (audio_id, syllable_index)
    so it can be attached back onto `human_vs_system_diagnostics.csv` rows,
    which may be missing some syllable_index positions (syllables the
    analyzer declined to judge) -- this function still computes the full
    utterance's plan so the positions that DO survive get the right
    utterance-level context, not a context reconstructed from gaps."""
    utterances = {u.utterance_id: u for u in load_utterances(CORPUS_ROOT)}

    sandhi_by_key: dict[tuple[str, str], str] = {}
    lexical_len_by_key: dict[tuple[str, str], int] = {}
    unresolved: list[str] = []

    for audio_id in sorted(audio_ids):
        utterance = utterances.get(audio_id)
        if utterance is None:
            unresolved.append(audio_id)
            continue
        han_chars, lexical_lengths, plan = _utterance_plan(utterance.text)
        for i in range(len(han_chars)):
            key = (audio_id, str(i))
            lexical_len_by_key[key] = lexical_lengths[i]
            if plan is not None and len(plan) == len(han_chars):
                sandhi_by_key[key] = SANDHI_STATUS_MAP.get(plan[i].rule, "unknown")
            else:
                sandhi_by_key[key] = "unknown"

    return sandhi_by_key, lexical_len_by_key, unresolved


def attach_lexical_and_sandhi(rows: list[dict[str, Any]]) -> list[str]:
    audio_ids = {row["audio_id"] for row in rows}
    sandhi_by_key, lexical_len_by_key, unresolved = build_sandhi_and_lexical_tables(audio_ids)
    for row in rows:
        key = (row["audio_id"], row["syllable_index"])
        row["sandhi_status"] = sandhi_by_key.get(key, "unknown")
        row["lexical_word_length"] = lexical_len_by_key.get(key)
    return unresolved


# ---------------------------------------------------------------------------
# Evaluation helpers (existing predictions only -- no fitting happens here)
# ---------------------------------------------------------------------------


def _labels(rows: list[dict[str, Any]]) -> list[bool]:
    return [row["human_majority_tone_correct"] == "1" for row in rows]


def _human_correct_rate(rows: list[dict[str, Any]]) -> float | None:
    labels = _labels(rows)
    return (sum(labels) / len(labels)) if labels else None


def evaluate_candidate(rows: list[dict[str, Any]], probability_key: str, predicted_key: str) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    probabilities = [float(row[probability_key]) for row in rows]
    predicted = [bool(int(row[predicted_key])) for row in rows]
    labels = _labels(rows)
    metrics = binary_agreement(predicted, labels)
    metrics["auc"] = roc_auc(probabilities, labels)
    metrics["n"] = len(rows)
    return metrics


def evaluate_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = evaluate_baseline_a(rows)
    metrics["n"] = len(rows)
    return metrics


def evaluate_all_three(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "baseline_a": evaluate_baseline(rows),
        "candidate_b1": evaluate_candidate(rows, "candidate_b_probability", "candidate_b_predicted_correct"),
        "candidate_c1": evaluate_candidate(rows, "candidate_c_probability", "candidate_c_predicted_correct"),
    }


def evaluate_c1_by_tone(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_tone = {tone: [row for row in rows if row["expected_tone"] == tone] for tone in TONES}
    return {tone: evaluate_candidate(by_tone[tone], "candidate_c_probability", "candidate_c_predicted_correct")
            for tone in TONES}


def is_unanimous(row: dict[str, Any]) -> bool:
    labels = row["individual_rater_labels"]
    return len(labels) > 0 and len(set(labels)) == 1


def meets_high_confidence_criteria(row: dict[str, Any]) -> bool:
    """HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET (Q8), revised: unanimous rating +
    valid single-character OMPAL annotation + context-stable tone +
    non-neutral tone. Deliberately does NOT check `lexical_word_length` --
    per Q1's conclusion, label duplication is not plausible in this
    validation set, so jieba-derived lexical word length stays a separate,
    auxiliary analysis (Q2/Q3), not a criterion for the primary clean
    subset. Usable alignment is not checked here either: every row this is
    ever called on already comes from B1/C1's own usable row set."""
    return (
        is_unanimous(row)
        and row["word_character_count"] == "1"
        and row["sandhi_status"] == "stable"
        and row["expected_tone"] != "5"
    )


# ---------------------------------------------------------------------------
# Output: the two CSV deliverables
# ---------------------------------------------------------------------------


def write_sandhi_csv(rows: list[dict[str, Any]], path: Path = SANDHI_CSV) -> int:
    fieldnames = [
        "audio_id", "speaker_id", "word", "syllable_index", "syllable_count",
        "expected_tone", "lexical_word_length", "sandhi_status",
        "human_majority_tone_correct", "individual_rater_labels",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})
    return len(rows)


def write_high_confidence_csv(rows: list[dict[str, Any]], path: Path = HIGH_CONFIDENCE_CSV) -> int:
    fieldnames = [
        "audio_id", "speaker_id", "word", "expected_tone", "syllable_index",
        "word_character_count", "lexical_word_length", "sandhi_status",
        "individual_rater_labels", "human_majority_tone_correct",
        "system_tone_correct", "system_character_score",
        "candidate_b_probability", "candidate_b_predicted_correct",
        "candidate_c_probability", "candidate_c_predicted_correct",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})
    return len(rows)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    master = build_master_rows()
    unresolved = attach_lexical_and_sandhi(master)

    # Q1 counts (Q1a-1e already established from source in the report text;
    # these are the pipeline-level counts over the validation rows this
    # audit actually evaluates).
    n_rows = len(master)
    word_character_count_values = Counter(row["word_character_count"] for row in master)
    lexical_length_values = Counter(row["lexical_word_length"] for row in master)

    # Q2: monosyllabic-only (lexical_word_length == 1)
    mono_rows = [row for row in master if row["lexical_word_length"] == 1]
    q2 = {
        "all": {"n": n_rows, "human_correct_rate": _human_correct_rate(master), **evaluate_all_three(master)},
        "monosyllabic": {
            "n": len(mono_rows),
            "human_correct_rate": _human_correct_rate(mono_rows),
            **evaluate_all_three(mono_rows),
        },
        "monosyllabic_c1_by_tone": evaluate_c1_by_tone(mono_rows),
    }

    # Q3: monosyllabic / 2-syllable / 3+-syllable breakdown
    two_syll_rows = [row for row in master if row["lexical_word_length"] == 2]
    three_plus_rows = [row for row in master if (row["lexical_word_length"] or 0) >= 3]
    q3 = {
        "monosyllabic": {"n": len(mono_rows), "human_correct_rate": _human_correct_rate(mono_rows), **evaluate_all_three(mono_rows)},
        "two_syllable": {"n": len(two_syll_rows), "human_correct_rate": _human_correct_rate(two_syll_rows), **evaluate_all_three(two_syll_rows)},
        "three_plus_syllable": {"n": len(three_plus_rows), "human_correct_rate": _human_correct_rate(three_plus_rows), **evaluate_all_three(three_plus_rows)},
    }

    # Q5/Q6: sandhi status breakdown
    sandhi_counts = Counter(row["sandhi_status"] for row in master)
    stable_rows = [row for row in master if row["sandhi_status"] == "stable"]
    sandhi_candidate_rows = [
        row for row in master
        if row["sandhi_status"] in ("T3_sandhi_candidate", "yi_sandhi_candidate", "bu_sandhi_candidate")
    ]
    q6 = {
        "all": evaluate_all_three(master),
        "context_stable": {"n": len(stable_rows), **evaluate_all_three(stable_rows)},
        "potential_sandhi": {"n": len(sandhi_candidate_rows), **evaluate_all_three(sandhi_candidate_rows)},
        "context_stable_c1_by_tone": evaluate_c1_by_tone(stable_rows),
    }

    # Q7: human agreement -- all vs unanimous
    unanimous_rows = [row for row in master if is_unanimous(row)]
    q7 = {
        "all": {
            "b1": evaluate_candidate(master, "candidate_b_probability", "candidate_b_predicted_correct"),
            "c1": evaluate_candidate(master, "candidate_c_probability", "candidate_c_predicted_correct"),
        },
        "unanimous": {
            "n": len(unanimous_rows),
            "b1": evaluate_candidate(unanimous_rows, "candidate_b_probability", "candidate_b_predicted_correct"),
            "c1": evaluate_candidate(unanimous_rows, "candidate_c_probability", "candidate_c_predicted_correct"),
        },
    }

    # Q8: HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET -- revised per follow-up
    # instruction after Q1 was resolved (label duplication is not a
    # plausible explanation in this validation set, so jieba-derived lexical
    # word length is no longer a criterion for the PRIMARY clean subset --
    # see the Q2/Q3 section, now reported separately as auxiliary
    # lexical-context analysis). Defined before looking at its performance:
    # unanimous human rating + valid single-character OMPAL annotation
    # (word_character_count == 1 -- see Q1; currently true for every row in
    # this validation set, kept as an explicit, self-contained criterion
    # rather than assumed) + context-stable tone + usable alignment (already
    # guaranteed -- every row here is already in B1/C1's usable row set) +
    # non-neutral tone (expected_tone != "5"; already guaranteed by the
    # corpus's existing exclusion rules, kept explicit for the same reason).
    high_confidence_rows = [row for row in master if meets_high_confidence_criteria(row)]
    q8 = {
        "n": len(high_confidence_rows),
        "label_distribution": Counter(row["human_majority_tone_correct"] for row in high_confidence_rows),
        **evaluate_all_three(high_confidence_rows),
        "c1_by_tone": evaluate_c1_by_tone(high_confidence_rows),
    }

    n_sandhi_written = write_sandhi_csv(master)
    n_high_confidence_written = write_high_confidence_csv(high_confidence_rows)

    return {
        "n_rows": n_rows,
        "unresolved_audio_ids": unresolved,
        "word_character_count_values": word_character_count_values,
        "lexical_length_values": lexical_length_values,
        "q2": q2,
        "q3": q3,
        "sandhi_counts": sandhi_counts,
        "q6": q6,
        "q7": q7,
        "q8": q8,
        "high_confidence_rows_sample": high_confidence_rows[:5],
        "n_sandhi_written": n_sandhi_written,
        "n_high_confidence_written": n_high_confidence_written,
    }


if __name__ == "__main__":
    from benchmarking import report_label_audit

    result = run()
    report_label_audit.write_report(result)
    print(f"Sandhi audit written to {SANDHI_CSV} ({result['n_sandhi_written']} rows)")
    print(f"High-confidence subset written to {HIGH_CONFIDENCE_CSV} ({result['n_high_confidence_written']} rows)")
    print(f"Report written to {REPORT_PATH}")
