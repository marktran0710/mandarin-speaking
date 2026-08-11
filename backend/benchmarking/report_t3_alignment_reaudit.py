"""Renders `t3_alignment_reaudit.run()`'s results into
`benchmarking/results/t3_alignment_reaudit.md` (STEP 2, 4, 5)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "NA"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _step2_boundary_table(rows: list[dict[str, Any]]) -> str:
    header = (
        "| Voice | Context | Old 50/50 (s) | Aligned (s) | Diff (ms) | "
        "1st syll dur (s) | 2nd syll dur (s) |\n|---|---|---|---|---|---|---|\n"
    )
    body = [
        f"| {r['voice']} | {r['context']} | {_fmt(r['old_50pct_boundary_s'], 3)} | "
        f"{_fmt(r['aligned_boundary_s'], 3)} | {_fmt(r['difference_ms'], 1)} | "
        f"{_fmt(r['first_syllable_duration_s'], 3)} | {_fmt(r['second_syllable_duration_s'], 3)} |"
        for r in rows
    ]
    return header + "\n".join(body)


def _step2_threshold_summary(rows: list[dict[str, Any]]) -> str:
    diffs = [abs(r["difference_ms"]) for r in rows if r.get("difference_ms") is not None]
    n = len(diffs)
    lines = []
    for threshold in (10, 20, 30, 50):
        count = sum(1 for d in diffs if d > threshold)
        lines.append(f"- Differs from 50/50 by > {threshold}ms: {count} of {n} ({_fmt(count / n if n else None, 2)})")
    return "\n".join(lines)


def _step4_confusion_table(rows: list[dict[str, Any]]) -> str:
    categories = ["fall-rise", "rise-fall", "low-flat", "mostly-falling", "mostly-rising", "other", "unmeasured"]
    counts = Counter((r["old_50pct_shape_category"], r["shape_category"]) for r in rows)
    header = "| Old (50/50) \\ Aligned | " + " | ".join(categories) + " |\n"
    header += "|---|" + "|".join(["---"] * len(categories)) + "|\n"
    body = []
    for old_cat in categories:
        row_counts = [str(counts.get((old_cat, new_cat), 0)) for new_cat in categories]
        if any(c != "0" for c in row_counts):
            body.append(f"| {old_cat} | " + " | ".join(row_counts) + " |")
    return header + "\n".join(body)


def _step5_t3_plus_t3_table(rows: list[dict[str, Any]]) -> str:
    t3t3_rows = [r for r in rows if r["context"] == "plus_t3"]
    header = (
        "| Voice | f0_start | f0_quarter | f0_mid | f0_3quarter | f0_end | "
        "1st-half slope | 2nd-half slope | Aligned shape | Old (50/50) shape |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    body = [
        f"| {r['voice']} | {_fmt(r['f0_start'], 3)} | {_fmt(r['f0_quarter'], 3)} | "
        f"{_fmt(r['f0_mid'], 3)} | {_fmt(r['f0_three_quarter'], 3)} | {_fmt(r['f0_end'], 3)} | "
        f"{_fmt(r['first_half_slope'], 3)} | {_fmt(r['second_half_slope'], 3)} | "
        f"`{r['shape_category']}` | `{r['old_50pct_shape_category']}` |"
        for r in t3t3_rows
    ]
    return header + "\n".join(body)


def write_reaudit_report(result: dict[str, Any], path: Path) -> None:
    rows = result["rows"]
    n_changed = sum(1 for r in rows if r["shape_changed"])
    n_total = len(rows)

    t3t3_rows = [r for r in rows if r["context"] == "plus_t3"]
    t3t3_rising_count = sum(
        1 for r in t3t3_rows
        if r["shape_category"] in ("fall-rise", "mostly-rising") and r.get("second_half_slope") is not None and r["second_half_slope"] > 0
    )
    t3t3_shapes = Counter(r["shape_category"] for r in t3t3_rows)

    step5_answer = (
        f"Aligned first-T3-in-T3+T3 shapes across the 3 voices: {dict(t3t3_shapes)}. "
        + (
            "**Proper segmentation DOES reveal rising/T2-like movement in at least "
            "some voices** (see the per-voice table below for the actual slopes — "
            "judge directly from the numbers, not from the category label alone, "
            "since `fall-rise` still requires an initial fall before the rise, "
            "which is not the same claim as pure T2-like rising throughout)."
            if t3t3_rising_count > 0
            else "**Proper segmentation does NOT show a rising/T2-like first T3 in this "
            "data** — the second-half slope stayed non-positive for every voice even "
            "after removing the second-syllable contamination the 50/50 split risked. "
            "This does not match the classical T3-sandhi expectation for this "
            "specific dataset; report it as found, not adjusted to match theory."
        )
    )

    report = f"""# T3 alignment re-audit

**Candidate E V1 remains frozen** — not imported anywhere in this module.
**No OMPAL data, no final_test.** Alignment via `tone_scoring.alignment.
EnergyAligner` (STEP 1's first preference among existing deterministic
aligners — the same aligner `praat_analyzer._aligner()` defaults to in
production via `TONE_ALIGNER=energy`). No new model was added.

Scope: the 4 contexts the task named (T3+T1, T3+T2, T3+T3, T3+T4), the
first (T3) syllable only, across the same 3 zh-TW voices as the earlier
audit — {n_total} tokens total.

## STEP 1-2 — Boundary comparison: old 50/50 split vs. EnergyAligner

{_step2_boundary_table(rows)}

**How often the aligned boundary differs from the old 50/50 split:**

{_step2_threshold_summary(rows)}

## STEP 4 — Shape reclassification: 50/50 vs. aligned

**{n_changed} of {n_total} tokens changed descriptive shape category** after
switching from the 50/50 split to real syllable alignment.

### Confusion table (rows = old 50/50 category, columns = aligned category)

{_step4_confusion_table(rows)}

## STEP 5 — T3+T3 critical check

**Question**: does proper segmentation reveal a rising/T2-like first T3 in
a T3+T3 sequence?

{step5_answer}

### Per-voice detail, first T3 in T3+T3 (aligned)

{_step5_t3_plus_t3_table(rows)}

---

*No OMPAL data (development, validation, or final_test) was loaded by any
code in this re-audit. Candidate E V1 and production code were not
modified. Alignment used the existing `EnergyAligner` only — no new model.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
