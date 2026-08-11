"""Generate the frozen OMPAL speaker-disjoint split and report its shape.

    python -m benchmarking.build_speaker_split

Writes `benchmarking/splits/ompal_speaker_split.json` and
`benchmarking/results/speaker_split_report.md`. Refuses to overwrite an
existing split silently — `final_test` only means something if it cannot be
regenerated on a whim once results depend on it staying fixed.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

from benchmarking.ompal_corpus import load_utterances
from benchmarking.splits import (
    DEFAULT_RATIOS,
    DEFAULT_SEED,
    DEFAULT_SPLIT_PATH,
    SPLIT_NAMES,
    create_speaker_split,
    write_split,
)
from benchmarking.stats import safe_divide

CORPUS = Path("private-data/ompal")
DIAGNOSTICS_CSV = Path("benchmarking/results/human_vs_system_diagnostics.csv")
REPORT_PATH = Path("benchmarking/results/speaker_split_report.md")


def _distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    correct = sum(1 for row in rows if row["confusion_group"] in ("TP", "FN"))
    incorrect = len(rows) - correct
    tone_counts = Counter(row["expected_tone"] for row in rows if row["expected_tone"] != "NA")
    return {
        "word_items": len(rows),
        "human_correct": correct,
        "human_incorrect": incorrect,
        "human_correct_rate": safe_divide(correct, len(rows)),
        "by_tone": {str(tone): tone_counts.get(str(tone), 0) for tone in (1, 2, 3, 4)},
    }


def _render(split, per_split_stats: dict[str, Any], overall_rate: float | None) -> str:
    def pct(value):
        return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "NA"

    lines = [
        "# OMPAL speaker-disjoint split — shape report",
        "",
        f"Seed `{split.seed}`, ratios {split.ratios}. Deterministic: re-running",
        "`python -m benchmarking.build_speaker_split` with the same speaker list",
        "reproduces this split exactly (see `tests/test_splits.py`).",
        "",
        "| Split | Speakers | Utterances | Word items | Human correct | Human incorrect | Correct rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in SPLIT_NAMES:
        stats = per_split_stats[name]
        lines.append(
            f"| {name}{' 🔒' if name == 'final_test' else ''} | "
            f"{stats['speakers']} | {stats['utterances']} | {stats['word_items']} | "
            f"{stats['human_correct']} | {stats['human_incorrect']} | "
            f"{pct(stats['human_correct_rate'])} |"
        )

    lines += [
        "",
        f"Overall human-correct rate across all three splits: {pct(overall_rate)}.",
        "",
        "## Tone distribution per split",
        "",
        "| Split | T1 | T2 | T3 | T4 |",
        "|---|---|---|---|---|",
    ]
    for name in SPLIT_NAMES:
        by_tone = per_split_stats[name]["by_tone"]
        lines.append(f"| {name} | {by_tone['1']} | {by_tone['2']} | {by_tone['3']} | {by_tone['4']} |")

    # Comparability check: how far each split's correct-rate and each tone's
    # share drift from the pooled rate — large drift would mean the split
    # accidentally concentrated an unusual population in one partition.
    lines += ["", "## Comparability check", ""]
    max_rate_drift = 0.0
    for name in SPLIT_NAMES:
        rate = per_split_stats[name]["human_correct_rate"]
        if rate is not None and overall_rate is not None:
            max_rate_drift = max(max_rate_drift, abs(rate - overall_rate))
    total_items = sum(per_split_stats[name]["word_items"] for name in SPLIT_NAMES)
    max_tone_drift = 0.0
    for tone in ("1", "2", "3", "4"):
        pooled_share = sum(per_split_stats[n]["by_tone"][tone] for n in SPLIT_NAMES) / total_items
        for name in SPLIT_NAMES:
            n = per_split_stats[name]["word_items"]
            if n == 0:
                continue
            share = per_split_stats[name]["by_tone"][tone] / n
            max_tone_drift = max(max_tone_drift, abs(share - pooled_share))

    verdict = (
        "comparable — largest correct-rate drift "
        f"{max_rate_drift * 100:.1f} pts, largest per-tone share drift "
        f"{max_tone_drift * 100:.1f} pts"
        if max_rate_drift < 0.05 and max_tone_drift < 0.05
        else "notably uneven — see the numbers above before trusting "
        "final_test as representative"
    )
    lines.append(f"Distributions across splits are **{verdict}**.")
    return "\n".join(lines) + "\n"


def main() -> int:
    if DEFAULT_SPLIT_PATH.exists():
        print(
            f"{DEFAULT_SPLIT_PATH} already exists. Delete it explicitly first if "
            "you intend to regenerate it — a split that can be silently "
            "overwritten cannot be relied on as a locked final_test.",
            file=sys.stderr,
        )
        return 1
    if not DIAGNOSTICS_CSV.is_file():
        print(f"{DIAGNOSTICS_CSV} not found; run benchmarking.run_diagnostics first.", file=sys.stderr)
        return 1

    utterances = load_utterances(CORPUS)
    non_native_speakers = sorted({u.speaker_id for u in utterances if not u.is_native})
    split = create_speaker_split(non_native_speakers, seed=DEFAULT_SEED, ratios=DEFAULT_RATIOS)
    write_split(split, DEFAULT_SPLIT_PATH)

    import csv

    with DIAGNOSTICS_CSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    per_split_stats: dict[str, Any] = {}
    for name in SPLIT_NAMES:
        speakers = set(getattr(split, name))
        # Utterance count comes from the corpus directly, not from the
        # diagnostics export — the split describes speakers/recordings, and
        # must not shrink just because a particular scoring run judged fewer
        # of a speaker's words (e.g. an all-neutral-tone utterance).
        split_utterances = [u for u in utterances if u.speaker_id in speakers]
        split_rows = [row for row in rows if row["speaker_id"] in speakers]
        stats = _distribution(split_rows)
        stats["speakers"] = len(speakers)
        stats["utterances"] = len(split_utterances)
        per_split_stats[name] = stats

    overall_correct = sum(per_split_stats[n]["human_correct"] for n in SPLIT_NAMES)
    overall_total = sum(per_split_stats[n]["word_items"] for n in SPLIT_NAMES)
    overall_rate = safe_divide(overall_correct, overall_total)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render(split, per_split_stats, overall_rate), encoding="utf-8")

    print(f"Split written to {DEFAULT_SPLIT_PATH}")
    print(f"Report written to {REPORT_PATH}")
    for name in SPLIT_NAMES:
        print(f"  {name}: {per_split_stats[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
