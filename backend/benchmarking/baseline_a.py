"""Baseline A: the current frozen scorer, measured on the locked split.

    python -m benchmarking.baseline_a

BASELINE A is exactly what is already running in production — Praat +
EnergyAligner + `directional_tone_scores` + threshold 58 — recorded here,
unmodified, as the number every future candidate model must beat under the
same speaker-disjoint protocol (see `model_comparison_protocol.md`).

This module computes nothing new: it reads
`benchmarking/results/human_vs_system_diagnostics.csv` (already produced by
the frozen pipeline and already verified against the cached score — see
`diagnostics.py`) and `benchmarking/splits/ompal_speaker_split.json`, and
partitions the former by the latter. No audio is re-analysed and no score is
recomputed.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

from benchmarking.splits import DEFAULT_SPLIT_PATH, SPLIT_NAMES, load_split
from benchmarking.stats import binary_agreement, error_rates, roc_auc

DIAGNOSTICS_CSV = Path("benchmarking/results/human_vs_system_diagnostics.csv")
REPORT_PATH = Path("benchmarking/results/baseline_a_report.md")

METRIC_ROWS = [
    ("N", "n", 0),
    ("Accuracy", "accuracy", 3),
    ("Balanced accuracy", "balanced_accuracy", 3),
    ("Precision", "precision", 3),
    ("Recall (sensitivity)", "recall", 3),
    ("Specificity", "specificity", 3),
    ("F1", "f1", 3),
    ("Cohen's kappa", "cohen_kappa", 4),
    ("Matthews correlation (MCC)", "matthews_correlation", 4),
    ("ROC AUC", "auc", 3),
    ("False acceptance rate", "false_acceptance_rate", 3),
    ("False rejection rate", "false_rejection_rate", 3),
]


def _fmt(value: Any, digits: int) -> str:
    if value is None:
        return "NA"
    if digits == 0:
        return str(value)
    return f"{value:.{digits}f}"


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Baseline A's metric set for one set of rows — one split, or one
    (split, tone) pair. Every number here comes from `stats.py`'s already-
    tested primitives; nothing is computed ad hoc."""
    if not rows:
        return {"n": 0}
    # Read the literal boolean columns rather than re-deriving them from
    # `confusion_group` — one fewer indirection between this report and the
    # verified export.
    predicted = [row["system_tone_correct"] == "1" for row in rows]
    actual = [row["human_majority_tone_correct"] == "1" for row in rows]
    metrics = binary_agreement(predicted, actual)
    scored = [
        row for row in rows
        if row.get("system_character_score") not in (None, "", "NA")
    ]
    metrics["auc"] = (
        roc_auc(
            [float(row["system_character_score"]) for row in scored],
            [row["human_majority_tone_correct"] == "1" for row in scored],
        )
        if scored
        else None
    )
    return metrics


def render_split_table(name: str, overall: dict[str, Any], by_tone: dict[str, dict]) -> str:
    lines = [f"### {name}", "", "| Metric | Overall | T1 | T2 | T3 | T4 |", "|---|---|---|---|---|---|"]
    for label, key, digits in METRIC_ROWS:
        row = [label, _fmt(overall.get(key), digits)]
        for tone in ("1", "2", "3", "4"):
            row.append(_fmt(by_tone.get(tone, {}).get(key), digits))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main() -> int:
    if not DIAGNOSTICS_CSV.is_file():
        print(f"{DIAGNOSTICS_CSV} not found; run benchmarking.run_diagnostics first.", file=sys.stderr)
        return 1
    if not DEFAULT_SPLIT_PATH.is_file():
        print(f"{DEFAULT_SPLIT_PATH} not found; run benchmarking.build_speaker_split first.", file=sys.stderr)
        return 1

    split = load_split(DEFAULT_SPLIT_PATH)
    with DIAGNOSTICS_CSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    sections = []
    summary_rows = []
    for name in SPLIT_NAMES:
        speakers = set(getattr(split, name))
        split_rows = [row for row in rows if row["speaker_id"] in speakers]
        overall = evaluate(split_rows)
        by_tone = {
            tone: evaluate([row for row in split_rows if row["expected_tone"] == tone])
            for tone in ("1", "2", "3", "4")
        }
        sections.append(render_split_table(name, overall, by_tone))
        summary_rows.append(
            f"| {name}{' 🔒' if name == 'final_test' else ''} | {overall.get('n')} | "
            f"{_fmt(overall.get('accuracy'), 3)} | {_fmt(overall.get('balanced_accuracy'), 3)} | "
            f"{_fmt(overall.get('cohen_kappa'), 4)} | {_fmt(overall.get('matthews_correlation'), 4)} | "
            f"{_fmt(overall.get('auc'), 3)} |"
        )

    report = f"""# Baseline A — current frozen scorer, per speaker-disjoint split

BASELINE A = Praat + EnergyAligner + `chinese_tones.directional_tone_scores`
+ threshold 58, exactly as shipped. **Not modified to produce this report.**
Rows come from `human_vs_system_diagnostics.csv`, itself verified
byte-identical to the cached score before use (see `diagnostics.py`); this
report only partitions those rows by the speaker split in
`benchmarking/splits/ompal_speaker_split.json` (seed {split.seed}).

## Summary

| Split | N | Accuracy | Balanced accuracy | Kappa | MCC | AUC |
|---|---|---|---|---|---|---|
{chr(10).join(summary_rows)}

## Full metrics, overall and per tone

{chr(10).join(chr(10) + section for section in sections)}

## Reading this table

- `development` is for any future candidate model's own iteration — inspect
  it freely.
- `validation` is for comparing candidates against Baseline A and each other
  before committing to one — inspect freely, but do not use it to pick a
  final threshold or hyperparameter that is then reported as if untuned.
- `final_test` 🔒 is reported here **once**, now, as Baseline A's locked
  number. No future candidate model may consult these labels for any
  purpose before its own final_test number is reported — see
  `model_comparison_protocol.md`.
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
