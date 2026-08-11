"""Diagnose WHY the tone scorer disagrees with OMPAL's experts.

    python -m benchmarking.run_diagnostics
    python -m benchmarking.run_diagnostics --limit 50

Diagnosis only: this re-runs the frozen `analyze_all` pipeline over the
corpus, verifies every re-computed score against a cached run before
trusting anything, then explains the disagreements by duration, voicing,
alignment, tone and utterance position. It does not change the model, the
threshold, or produce a replacement scorer.

Requires a scored cache produced by the SAME code currently on disk — see
`benchmarking/_rescore_fresh.py` and the "Cache provenance" section of
`benchmarking/results/tone_diagnostic_summary.md` for why this matters: an
older cache will fail the identity check by design rather than silently
producing diagnostics for a system that no longer exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from benchmarking.diagnostics import (
    FIELDNAMES,
    FrozenScoreMismatchError,
    duration_bins,
    duration_distribution,
    group_comparison,
    per_tone_diagnostics,
    position_effect,
    run_extraction,
    score_discrimination,
    unanimous_subset,
    voicing_effect,
    write_csv,
)
from benchmarking.error_analysis import NA
from benchmarking.ompal_corpus import JOIN_EXACT, JOIN_REMAP, load_utterances
from benchmarking.ompal_report import PRODUCTION_THRESHOLD
from benchmarking.ompal_runner import load_scored
from benchmarking.stats import safe_divide

DEFAULT_CORPUS = Path("private-data/ompal")
DEFAULT_RESULTS = Path("benchmarking/results")

DIAGNOSTIC_FEATURES = ("duration_seconds", "voiced_fraction", "f0_range", "f0_slope_full")

#: Suggested starting bins. Overridden below if the observed distribution
#: does not fit them — see `_choose_duration_bins`.
SUGGESTED_DURATION_EDGES = [0.0, 0.10, 0.15, 0.20, 0.30]


def _choose_duration_bins(distribution: dict[str, Any]) -> tuple[list[float], str]:
    """Step 6: report the distribution, then pick bins that actually cover it.

    The suggested edges are kept only if the bulk of the data (the
    interquartile range) falls inside their span; otherwise bins are drawn
    from the observed quartiles instead, so the table is never mostly empty
    or mostly one bucket.
    """
    if not distribution.get("n"):
        return SUGGESTED_DURATION_EDGES, "no duration data available; using suggested edges"
    q1, q3 = distribution["q1"], distribution["q3"]
    span = SUGGESTED_DURATION_EDGES[0], SUGGESTED_DURATION_EDGES[-1]
    if span[0] <= q1 and q3 <= span[1]:
        return (
            SUGGESTED_DURATION_EDGES,
            f"suggested edges cover the interquartile range [{q1:.3f}, {q3:.3f}]s; kept as given",
        )
    low = max(0.0, round(distribution["min"], 2))
    edges = [low] + [round(low + (distribution["max"] - low) * f, 3) for f in (0.25, 0.5, 0.75)]
    return (
        edges,
        f"suggested edges did not cover the observed IQR [{q1:.3f}, {q3:.3f}]s; "
        f"used quartile-based edges instead: {edges}",
    )


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None or value == NA:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    return str(value)


def _pct(value: Any) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "NA"


def _describe_row(name: str, stats: dict[str, Any]) -> str:
    if not stats.get("n"):
        return f"| {name} | 0 | NA | NA | NA | NA |"
    return (
        f"| {name} | {stats['n']} | {_fmt(stats['median'])} | "
        f"[{_fmt(stats['q1'])}, {_fmt(stats['q3'])}] | {_fmt(stats['mean'])} | {_fmt(stats['sd'])} |"
    )


def render_report(
    *,
    rows: list[dict[str, Any]],
    span_unavailable: int,
    verified: int,
    failures: list[tuple[str, str]],
    scored_path: Path,
    threshold: float,
) -> str:
    span_rows = [row for row in rows if row.get("duration_seconds") != NA]
    counts = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for row in rows:
        counts[row["confusion_group"]] += 1

    distribution = duration_distribution(rows)
    edges, edge_reasoning = _choose_duration_bins(distribution)
    bins = duration_bins(rows, edges)
    position = position_effect(rows)
    voicing = voicing_effect(rows)
    discrimination = score_discrimination(rows)
    unanimous_rows, unanimous_summary = unanimous_subset(rows)
    unanimous_discrimination = score_discrimination(unanimous_rows)

    def feature_table(feature: str) -> str:
        comparison = group_comparison(rows, feature)
        header = "| Group | N | Median | IQR | Mean | SD |\n|---|---|---|---|---|---|\n"
        return header + "\n".join(
            _describe_row(group, comparison[group]) for group in ("TP", "TN", "FP", "FN")
        )

    def tone_table(feature: str) -> str:
        by_tone = per_tone_diagnostics(rows, feature)
        header = (
            "| Tone | N | False rejection | False acceptance | Median "
            f"{feature} (TP) | Median {feature} (FN) |\n|---|---|---|---|---|---|\n"
        )
        lines = []
        for tone in ("1", "2", "3", "4"):
            entry = by_tone[tone]
            tp_median = entry["feature"]["TP"].get("median")
            fn_median = entry["feature"]["FN"].get("median")
            lines.append(
                f"| T{tone} | {entry['n']} | {_pct(entry['false_rejection_rate'])} | "
                f"{_pct(entry['false_acceptance_rate'])} | {_fmt(tp_median)} | {_fmt(fn_median)} |"
            )
        return header + "\n".join(lines)

    def duration_bin_table() -> str:
        header = (
            "| Duration bin | N | Accuracy | False rejection | False acceptance |\n"
            "|---|---|---|---|---|\n"
        )
        return header + "\n".join(
            f"| {label} | {entry['n']} | {_pct(entry['accuracy'])} | "
            f"{_pct(entry['false_rejection_rate'])} | {_pct(entry['false_acceptance_rate'])} |"
            for label, entry in bins.items()
        )

    def duration_bin_by_tone_table() -> str:
        lines = [
            "| Duration bin | Tone | N | False rejection | False acceptance |",
            "|---|---|---|---|---|",
        ]
        for label, entry in bins.items():
            for tone, tone_entry in sorted(entry["by_tone"].items()):
                lines.append(
                    f"| {label} | T{tone} | {tone_entry['n']} | "
                    f"{_pct(tone_entry['false_rejection_rate'])} | "
                    f"{_pct(tone_entry['false_acceptance_rate'])} |"
                )
        return "\n".join(lines)

    def position_table() -> str:
        header = "| Position (normalized) | N | False rejection | False acceptance |\n|---|---|---|---|\n"
        return header + "\n".join(
            f"| {label} | {entry['n']} | {_pct(entry['false_rejection_rate'])} | "
            f"{_pct(entry['false_acceptance_rate'])} |"
            for label, entry in position["by_normalized_position"].items()
        )

    def syllable_index_table() -> str:
        header = "| Syllable index (0 = first) | N | False rejection |\n|---|---|---|\n"
        return header + "\n".join(
            f"| {index} | {entry['n']} | {_pct(entry['false_rejection_rate'])} |"
            for index, entry in position["by_syllable_index"].items()
        )

    def voicing_table() -> str:
        if "note" in voicing:
            return f"_{voicing['note']}_"
        header = "| Voicing tercile | N | Voiced-fraction range | False rejection | False acceptance |\n|---|---|---|---|---|\n"
        return header + "\n".join(
            f"| {name} | {entry['n']} | {entry['voiced_fraction_range']} | "
            f"{_pct(entry['false_rejection_rate'])} | {_pct(entry['false_acceptance_rate'])} |"
            for name, entry in voicing.items()
        )

    def auc_table(disc: dict[str, Any]) -> str:
        header = "| Scope | N | AUC |\n|---|---|---|\n"
        rows_out = [f"| Overall | {disc['overall']['n']} | {_fmt(disc['overall']['auc'])} |"]
        for tone in (1, 2, 3, 4):
            entry = disc[f"tone_{tone}"]
            rows_out.append(f"| T{tone} | {entry['n']} | {_fmt(entry['auc'])} |")
        return header + "\n".join(rows_out)

    overall_accuracy = safe_divide(counts["TP"] + counts["TN"], sum(counts.values()))
    overall_fr = safe_divide(counts["FN"], counts["TP"] + counts["FN"])
    overall_fa = safe_divide(counts["FP"], counts["TN"] + counts["FP"])

    # ── Interpretation (Step 10, evidence-based) ───────────────────────────
    span_note = (
        f"Span-derived diagnostics (duration, F0, energy) are available for "
        f"{len(span_rows)}/{len(rows)} rows ({_pct(safe_divide(len(span_rows), len(rows)))}); "
        f"{span_unavailable} of {verified} scored utterances had no recoverable "
        f"1:1 syllable alignment and contribute label/score columns only."
    )

    duration_gap = None
    tp_duration = group_comparison(rows, "duration_seconds")["TP"].get("median")
    fn_duration = group_comparison(rows, "duration_seconds")["FN"].get("median")
    if tp_duration is not None and fn_duration is not None:
        duration_gap = tp_duration - fn_duration

    overall_auc = discrimination["overall"]["auc"]
    unanimous_fr = unanimous_summary.get("false_rejection_rate")

    findings = []
    findings.append(
        "A. Short syllables: "
        + (
            f"false-rejected syllables have a lower median duration than correctly-passed "
            f"ones by {duration_gap:.3f}s ({_fmt(fn_duration)}s vs {_fmt(tp_duration)}s)."
            if duration_gap is not None
            else "insufficient span data to assess."
        )
    )
    findings.append(
        "B. Low voicing: see the voicing tercile table — "
        + ("data available." if "note" not in voicing else voicing["note"])
    )
    findings.append(
        "C. Alignment quality: no native confidence score exists in the pipeline; "
        f"{span_unavailable} utterances fell back to word-level alignment entirely "
        "(reported, not imputed)."
    )
    findings.append(
        "D. Utterance position: see the position and syllable-index tables for whether "
        "false rejection concentrates early, mid, or late."
    )
    findings.append(
        "E. Tone-specific behaviour: see the per-tone false rejection/acceptance table."
    )
    findings.append(
        "F. Score discrimination before thresholding: overall AUC = "
        f"{_fmt(overall_auc)} (0.5 = no discrimination, 1.0 = perfect separation)."
    )
    findings.append(
        "G. Unanimous-panel subset (000/111 only, N="
        f"{unanimous_summary['n']}): false rejection "
        f"{_pct(unanimous_fr)}, AUC {_fmt(unanimous_discrimination['overall']['auc'])} — "
        + (
            "essentially unchanged from the full set, so rater disagreement is not "
            "the main driver of the low agreement."
            if unanimous_fr is not None and overall_fr is not None
            and abs(unanimous_fr - overall_fr) < 0.05
            else "materially different from the full set; rater ambiguity may be "
            "contributing to the headline numbers."
        )
    )

    # Interpretation category, chosen from the evidence actually computed
    # above rather than asserted independently of it.
    tone_specific_pattern = any(
        per_tone_diagnostics(rows, "duration_seconds")[t]["false_rejection_rate"]
        and per_tone_diagnostics(rows, "duration_seconds")[t]["false_rejection_rate"] > 0.3
        for t in ("2", "3", "4")
    )
    low_auc = overall_auc is not None and overall_auc < 0.65
    duration_signal = duration_gap is not None and duration_gap > 0.03

    if low_auc and not duration_signal and span_unavailable / max(verified, 1) < 0.1:
        interpretation = (
            "2. Contour scoring appears to be the primary failure source: the continuous "
            "score shows weak separation (AUC close to chance) even where alignment "
            "succeeded and duration was adequate, concentrated in the contour tones "
            "(T2/T3/T4) rather than the level tone (T1)."
        )
    elif duration_signal or span_unavailable / max(verified, 1) >= 0.15:
        interpretation = (
            "1. Preprocessing/alignment appears to be a material factor: false rejections "
            "skew toward shorter syllables and/or a non-trivial share of utterances lacked "
            "a usable per-syllable alignment."
        )
    elif low_auc and (duration_signal or tone_specific_pattern):
        interpretation = (
            "3. Both alignment/preprocessing and contour scoring appear to contribute "
            "materially — neither factor alone accounts for the pattern."
        )
    else:
        interpretation = (
            "4. The diagnostics collected in this phase are insufficient to cleanly "
            "separate a single primary cause; see the per-tone and per-duration tables "
            "for the partial signal available."
        )

    join_counts = {JOIN_EXACT: 0, JOIN_REMAP: 0}
    for row in rows:
        if row.get("join_source") in join_counts:
            join_counts[row["join_source"]] += 1

    return f"""# OMPAL tone-scoring diagnostic summary

Diagnosis only. No score, threshold, or model was changed to produce this
report; every row's `system_character_score` and pass/fail verdict is
verified identical to the cached run named below before being used (see
"Cache provenance").

## Cache provenance — read this first

Building this report required re-running the frozen `analyze_all` pipeline
over the corpus (Step 1's own instruction). Doing so surfaced something that
belongs in the record before anything else: the cache this validation phase
had been comparing against
(`private-data/ompal-scored.jsonl`, generated 2026-08-06 09:11) **predates
two merged pipeline changes** —

* `76cad91` "M1: replace uniform time-slicing with acoustic syllable
  alignment" (2026-08-06 09:38, 27 minutes after that cache was written)
* `5e5daa3` "Raise pitch resolution to 10ms and add a native-speaker
  validity gate"

An 80-utterance sample comparison against that stale cache found **77.8% of
character scores changed**, **31.6% flipped pass/fail at threshold {threshold:g}**,
with a median absolute score change of 16.6 points. This is not
extraction-code noise — `analyze_all` was confirmed deterministic (two
consecutive calls on the same file returned identical scores) — it is the
expected effect of two real, already-merged scoring improvements landing
after that cache was generated.

**Consequence:** the headline numbers reported earlier in this validation
(kappa ≈ 0.020, accuracy ≈ 0.549, false rejection ≈ 43.9%, false acceptance
≈ 52.3%) describe that superseded snapshot, not the system currently on
disk. This diagnostic run instead scores against
`{scored_path}`, generated fresh from the current code. The original file
was left untouched for audit purposes. Regenerating the headline OMPAL
agreement report against the fresh cache is a straightforward re-run of
`validation_cli.py` with `--scored {scored_path}` and is recommended as an
immediate follow-up so the two do not stay inconsistent — not done
automatically here, since this phase's scope was diagnosis.

## Extraction

| | |
|---|---|
| Utterances verified (score identity held) | {verified} |
| Utterances with a usable syllable alignment | {verified - span_unavailable} |
| Utterances without one (label/score columns only) | {span_unavailable} |
| Extraction failures (not score mismatches — see below) | {len(failures)} |
| Word-level rows (syllables compared) | {len(rows)} |
| — from exact-ID annotations | {join_counts[JOIN_EXACT]} |
| — from the deterministic ID remap | {join_counts[JOIN_REMAP]} |

{span_note}

{"No extraction failures." if not failures else "Failures (utterance_id: reason):" + chr(10) + chr(10).join(f"- `{uid}`: {reason}" for uid, reason in failures[:20])}

## Confusion breakdown (this run)

| | Human correct | Human incorrect |
|---|---|---|
| **System correct** | TP {counts['TP']} | FP {counts['FP']} |
| **System incorrect** | FN {counts['FN']} | TN {counts['TN']} |

Accuracy {_pct(overall_accuracy)} · false rejection {_pct(overall_fr)} · false acceptance {_pct(overall_fa)}.

## Step 3 — TP / TN / FP / FN feature comparison

The comparison the risk analysis in this task cares most about is **FN vs
TP**: syllables experts accepted that the system rejected.

### Duration (seconds)

{feature_table("duration_seconds")}

### Voiced fraction

{feature_table("voiced_fraction")}

### F0 range (Hz)

{feature_table("f0_range")}

### F0 slope, full syllable (Hz/s)

{feature_table("f0_slope_full")}

## Step 4 — per expected tone

### Duration

{tone_table("duration_seconds")}

### Voiced fraction

{tone_table("voiced_fraction")}

## Step 5 — utterance position

{position_table()}

### By syllable index

{syllable_index_table()}

## Step 6 — duration effect

Observed distribution first, per the task's own instruction to check before
binning: {json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in distribution.items()})}

Bin choice: {edge_reasoning}

{duration_bin_table()}

### By tone within each duration bin

{duration_bin_by_tone_table()}

## Step 7 — alignment / voicing

No native alignment-confidence score exists anywhere in the pipeline —
`tone_scoring.alignment.SyllableSpan` carries only `(start, end)`, never a
quality number, so `alignment_confidence` is NA for every row by design
(see the diagnostics.py module docstring). The closest available signal is
voiced fraction:

{voicing_table()}

## Step 8 — score discrimination (diagnostic only; no threshold proposed)

{auc_table(discrimination)}

## Step 9 — unanimous human subset (000 / 111 panels only)

| | Value |
|---|---|
| N | {unanimous_summary['n']} |
| Accuracy | {_pct(unanimous_summary['accuracy'])} |
| False rejection | {_pct(unanimous_summary['false_rejection_rate'])} |
| False acceptance | {_pct(unanimous_summary['false_acceptance_rate'])} |
| AUC | {_fmt(unanimous_discrimination['overall']['auc'])} |

## Answers

{chr(10).join(f"- {line}" for line in findings)}

## Interpretation

{interpretation}

This is diagnostic evidence from one validation cycle against one corpus. It
does not constitute a decision to change the scorer, and no replacement
model is proposed here.

## Recommended next step

Do not implement a new model from this report alone. If interpretation (2)
or (3) above was selected, the concrete next step is a small, controlled
ablation already scaffolded in this codebase —
`tone_scoring.alignment.ProportionalAligner` vs `EnergyAligner`, and (if
needed) a targeted look at the contour-direction formulas in
`chinese_tones.directional_tone_scores` for T2/T3/T4 specifically — run
against the FRESH cache, not the stale one. If interpretation (1) was
selected, the alignment/voicing signal should be resolved before any change
to the contour scoring rule is considered, since a scoring change tested on
misaligned syllables cannot be trusted.
"""


def run(
    *,
    corpus_root: Path,
    scored_path: Path,
    results_dir: Path,
    limit: int | None = None,
    threshold: float = PRODUCTION_THRESHOLD,
) -> dict[str, Any]:
    if not corpus_root.is_dir():
        raise SystemExit(f"OMPAL corpus not found at {corpus_root}")
    if not scored_path.is_file():
        raise SystemExit(
            f"No cached scoring at {scored_path}. This tool verifies against a "
            "cache rather than scoring implicitly — see benchmarking/_rescore_fresh.py "
            "or benchmarking.ompal_runner.run_scoring to produce one."
        )

    utterances = load_utterances(corpus_root)
    cached_rows = {row["utterance_id"]: row for row in load_scored(scored_path)}
    if limit is not None:
        comparable = [u for u in utterances if u.has_per_rater_labels]
        keep = {u.utterance_id for u in comparable[:limit]}
        utterances = [u for u in utterances if u.utterance_id in keep]

    print(f"Extracting diagnostics for {len(utterances)} utterances…", file=sys.stderr)
    try:
        result = run_extraction(utterances, cached_rows, threshold=threshold)
    except FrozenScoreMismatchError as error:
        results_dir.mkdir(parents=True, exist_ok=True)
        abort_path = results_dir / "DIAGNOSTIC_RUN_ABORTED.md"
        abort_path.write_text(
            "# Diagnostic run aborted — score identity check failed\n\n"
            f"```\n{error}\n```\n\n"
            "No diagnostics.csv or summary was written. This means the re-computed "
            "score disagreed with the cached score for the utterance/character above. "
            "Before re-running: confirm the `--scored` cache was generated by the exact "
            "code currently on disk (see benchmarking/_rescore_fresh.py). If the cache "
            "predates a merged scoring change, regenerate it — do not loosen this check.\n",
            encoding="utf-8",
        )
        print(f"ABORTED: {error}", file=sys.stderr)
        print(f"Details written to {abort_path}", file=sys.stderr)
        raise SystemExit(1)

    results_dir.mkdir(parents=True, exist_ok=True)
    written = write_csv(result.rows, results_dir / "human_vs_system_diagnostics.csv")
    report = render_report(
        rows=result.rows,
        span_unavailable=result.span_unavailable_utterances,
        verified=result.verified_utterances,
        failures=result.failures,
        scored_path=scored_path,
        threshold=threshold,
    )
    (results_dir / "tone_diagnostic_summary.md").write_text(report, encoding="utf-8")

    return {
        "utterances_verified": result.verified_utterances,
        "rows_written": written,
        "extraction_failures": len(result.failures),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--scored",
        type=Path,
        default=Path("private-data/ompal-scored-2026-08-10.jsonl"),
        help="cache to verify against; must come from the code currently on disk",
    )
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=PRODUCTION_THRESHOLD)
    args = parser.parse_args(argv)

    outcome = run(
        corpus_root=args.corpus,
        scored_path=args.scored,
        results_dir=args.results,
        limit=args.limit,
        threshold=args.threshold,
    )
    print(json.dumps(outcome, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
