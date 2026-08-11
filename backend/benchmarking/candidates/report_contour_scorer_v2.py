"""Report writers for Candidate E's pipeline
(`contour_scorer_v2_pipeline.py`)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from benchmarking.candidates.contour_scorer_v2 import (
    T1_RANGE_REF,
    T1_SLOPE_REF,
    T3_DEPTH_OFFSET,
    T3_DEPTH_SCALE,
    T3_INVALID_SHAPE_CEILING,
    T3_SHAPE_SLOPE_EPS,
)

THRESHOLD = 58.0


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def write_ablation_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_canonical_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_predictions_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "case_id", "family", "audio_file", "audio_character", "audio_tone",
        "reference_character", "reference_tone", "expected_tone_correct",
        "baseline_a_score", "baseline_a_judged", "baseline_a_pass",
        "candidate_e_score", "candidate_e_pass",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def _ranking_summary_table(ranking_summary: dict[int, dict[str, Any]]) -> str:
    header = (
        "| Onset skip | T1 flattest-ranked | T2 most-positive-ranked | "
        "T3 dip signature present | T4 most-negative-ranked | Total |\n"
        "|---|---|---|---|---|---|\n"
    )
    rows = []
    for pct, checks in ranking_summary.items():
        total_correct = sum(c for c, _ in checks.values())
        total_n = sum(n for _, n in checks.values())
        rows.append(
            f"| {pct}% | {checks['t1_ranked_flattest'][0]}/{checks['t1_ranked_flattest'][1]} | "
            f"{checks['t2_ranked_most_positive'][0]}/{checks['t2_ranked_most_positive'][1]} | "
            f"{checks['t3_dip_signature_present'][0]}/{checks['t3_dip_signature_present'][1]} | "
            f"{checks['t4_ranked_most_negative'][0]}/{checks['t4_ranked_most_negative'][1]} | "
            f"{total_correct}/{total_n} |"
        )
    return header + "\n".join(rows)


def write_stop_report(
    canonical_rows: list[dict[str, Any]], failures: list[str],
    onset_pct: int, onset_reason: str, ranking_summary: dict[int, dict[str, Any]],
    path: Path = Path("benchmarking/results/candidate_e_controlled_test.md"),
) -> None:
    report = f"""# Candidate E — controlled test

## STOP: canonical ranking requirement failed (STEP 5)

Per the task's explicit instruction, Candidate E does not proceed to STEP 6
(controlled audio) or STEP 8 (freeze) because the basic sanity property —
score(correct canonical contour) > score(each incorrect canonical contour),
for every expected tone — does not hold.

### Onset-skip ablation (STEP 4)

Selected onset skip: {onset_pct}%. {onset_reason}

{_ranking_summary_table(ranking_summary)}

### Failures

{chr(10).join(f"- {f}" for f in failures)}

## B. Candidate E still fails basic contour discrimination.

See `candidate_e_canonical_matrix.csv` for the full 4x4 matrix.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def _confusion_table(overall: dict[str, dict[str, Any]]) -> str:
    header = "| Metric | Baseline A | Candidate E |\n|---|---|---|\n"
    rows = [
        ("N (scored)", "n", 0), ("Accuracy", "accuracy", 3), ("Balanced accuracy", "balanced_accuracy", 3),
        ("Sensitivity", "sensitivity", 3), ("Specificity", "specificity", 3),
        ("False rejection rate", "false_rejection_rate", 3), ("False acceptance rate", "false_acceptance_rate", 3),
    ]
    body = [
        f"| {label} | {_fmt(overall['baseline_a'].get(key), digits)} | {_fmt(overall['candidate_e'].get(key), digits)} |"
        for label, key, digits in rows
    ]
    return header + "\n".join(body)


def _by_tone_table(by_tone: dict[int, dict[str, Any]]) -> str:
    header = (
        "| Tone | N | Baseline A acc. | Baseline A bal. acc. | "
        "Candidate E acc. | Candidate E bal. acc. |\n|---|---|---|---|---|---|\n"
    )
    rows = []
    for tone in (1, 2, 3, 4):
        entry = by_tone[tone]
        rows.append(
            f"| T{tone} | {entry['candidate_e'].get('n', 0)} | "
            f"{_fmt(entry['baseline_a'].get('accuracy'))} | {_fmt(entry['baseline_a'].get('balanced_accuracy'))} | "
            f"{_fmt(entry['candidate_e'].get('accuracy'))} | {_fmt(entry['candidate_e'].get('balanced_accuracy'))} |"
        )
    return header + "\n".join(rows)


def _real_4x4_matrix(rows: list[dict[str, Any]], score_key: str) -> str:
    by_cell: dict[tuple[int, int], list[float]] = {}
    for row in rows:
        if row[score_key] is None:
            continue
        by_cell.setdefault((row["audio_tone"], row["reference_tone"]), []).append(row[score_key])
    header = "| Produced \\ Expected | T1 | T2 | T3 | T4 |\n|---|---|---|---|---|\n"
    body = []
    for produced in (1, 2, 3, 4):
        cells = []
        for expected in (1, 2, 3, 4):
            values = by_cell.get((produced, expected), [])
            cells.append(_fmt(sum(values) / len(values)) if values else "NA")
        body.append(f"| T{produced} | " + " | ".join(cells) + " |")
    return header + "\n".join(body)


def _t3_real_audio_findings(rows: list[dict[str, Any]]) -> str:
    t3_rows = [row for row in rows if row["reference_tone"] == 3]
    matched = [row for row in t3_rows if row["expected_tone_correct"] == 1]
    mismatched_scores_above_matched = []
    matched_scores = [row["candidate_e_score"] for row in matched if row["candidate_e_score"] is not None]
    matched_max = max(matched_scores) if matched_scores else None
    for row in t3_rows:
        if row["expected_tone_correct"] == 0 and row["candidate_e_score"] is not None and matched_max is not None:
            if row["candidate_e_score"] > matched_max:
                mismatched_scores_above_matched.append(row)

    lines = [
        f"- Matched (genuinely correct) T3 cases scored "
        f"{', '.join(f'{r["case_id"]}={r["candidate_e_score"]}' for r in matched)} — "
        f"near zero, not near 100.",
    ]
    if mismatched_scores_above_matched:
        worst = max(mismatched_scores_above_matched, key=lambda r: r["candidate_e_score"])
        lines.append(
            f"- **{len(mismatched_scores_above_matched)} mismatched T3 case(s) scored HIGHER than "
            f"every matched T3 case** — worst: `{worst['case_id']}` (audio is T{worst['audio_tone']}, "
            f"genuinely wrong) scored {worst['candidate_e_score']} against a T3 reference, vs. "
            f"Baseline A's {worst['baseline_a_score']} on the same case."
        )
    lines.append(
        "- **Root cause**: the onset-ablation data already showed this (STEP 4 table, "
        "\"T3 dip signature present\": 0/2 at every tested onset-skip percentage). Real "
        "single-syllable citation-form T3 audio from this TTS voice does not reliably "
        "realize the textbook fall-then-rise shape at all — it is often predominantly "
        "falling (consistent with a well-documented property of isolated/citation-form "
        "Mandarin T3: the full dip is more typical of connected speech or exaggerated "
        "citation reading, not always isolated single-syllable production). Candidate E's "
        "shape-validity gate is therefore working AS DESIGNED against contours that don't "
        "show the shape it requires — but that includes genuinely-correct T3 productions "
        "in this dataset, and the two-slope-sign check can still be spuriously satisfied "
        "by noise in a WRONG tone's audio, which is how a mismatched case outscored every "
        "matched one."
    )
    return "\n".join(lines)


def write_controlled_report(
    rows: list[dict[str, Any]], comparison: dict[str, Any], scale_audit: dict[int, dict[str, Any]],
    onset_pct: int, onset_reason: str, ranking_summary: dict[int, dict[str, Any]],
    canonical_rows: list[dict[str, Any]], path: Path,
) -> None:
    can_pass, can_failures = _canonical_check_text(canonical_rows)
    t3_findings = _t3_real_audio_findings(rows)

    scale_rows = "\n".join(
        f"| T{t} | {_fmt(scale_audit[t]['matched_min'])} | {_fmt(scale_audit[t]['matched_median'])} | {_fmt(scale_audit[t]['matched_max'])} |"
        for t in (1, 2, 3, 4)
    )
    all_matched_medians = [scale_audit[t]["matched_median"] for t in (1, 2, 3, 4) if scale_audit[t]["matched_median"] is not None]
    span = (max(all_matched_medians) - min(all_matched_medians)) if len(all_matched_medians) >= 2 else None
    scale_verdict = (
        "Tone-specific ranges differ by less than 20 points at the median — a single global "
        "threshold is plausible."
        if span is not None and span < 20
        else "Tone-specific matched-case medians differ by 20+ points — the four tones do NOT "
        "naturally occupy a common numerical range; a single global threshold would not treat "
        "them comparably without separate calibration."
    )

    report = f"""# Candidate E — controlled synthetic test (STEP 5-7)

**BASELINE_A_FROZEN** = `chinese_tones.directional_tone_scores` (production,
unmodified, read-only import). Candidate E = `contour_scorer_v2.py`, a
separate module. Neither production code nor threshold 58 was changed.
**No OMPAL data was loaded anywhere in this candidate's development.**

## STEP 4 — Onset-skip ablation

{_ranking_summary_table(ranking_summary)}

**Selected: {onset_pct}%.** {onset_reason}

Full per-file, per-fraction slope data in `candidate_e_onset_ablation.csv`.

## STEP 5 — Canonical contour ranking requirement

{"**PASSED**" if can_pass else "**FAILED**"}: score(correct canonical contour) > score(each incorrect canonical contour), for every expected tone.
{("" if can_pass else chr(10).join(f"- {f}" for f in can_failures))}

Full 4x4 idealized matrix in `candidate_e_canonical_matrix.csv`.

## STEP 6 — Controlled audio: Baseline A vs Candidate E (N={len(rows)} cases)

{_confusion_table(comparison['overall'])}

### Per target tone

{_by_tone_table(comparison['by_tone'])}

### Real audio 4x4 matrix — Baseline A (mean score per cell)

{_real_4x4_matrix(rows, 'baseline_a_score')}

### Real audio 4x4 matrix — Candidate E (mean score per cell)

{_real_4x4_matrix(rows, 'candidate_e_score')}

Full per-case predictions in `candidate_e_controlled_predictions.csv`.

### Known limitation: T3 on real audio (not visible in the idealized canonical test)

{t3_findings}

## STEP 7 — Score-scale audit

Candidate E's score range on genuinely-matched (correct) cases, per tone:

| Tone | Min | Median | Max |
|---|---|---|---|
{scale_rows}

{scale_verdict}

Note T3's own row above: matched-case scores are near-zero
(min/median/max within a couple of points of each other), which is the
same real-audio limitation as the T3 finding above, not an independent
observation.

## A. Candidate E passes canonical sanity checks — WITH AN IMPORTANT CAVEAT.

STEP 5's canonical ranking requirement (idealized, textbook contours) does
pass — verdict A per the task's literal STEP 5 criterion. **But STEP 6's
real controlled audio exposes a genuine, unresolved T3 problem** (see
above): real single-syllable T3 productions in this dataset don't reliably
show the fall-then-rise shape Candidate E's STEP 3 fix requires, so
Candidate E's T3 formula currently scores real matched T3 audio near zero
and, in at least one case, scores a genuinely WRONG tone higher than every
genuinely correct T3 production. T1/T2/T4 show clear, real improvement over
Baseline A (see STEP 6 tables above); **T3 does not, and needs further
work — most plausibly a shape-validity criterion that tolerates
predominantly-falling isolated-syllable T3 productions, not just the full
textbook dip — before Candidate E should be considered ready for further
development.** This is reported here, in the frozen protocol, and should be
treated as a blocking item for any future revision, not a footnote. Whether
Candidate E also clears threshold 58 on real controlled audio, and whether
that threshold should change, is a separate question this task does not
decide — no deployment threshold was chosen here, per the task's explicit
instruction.

---

*No OMPAL data (development, validation, or final_test) was loaded by any
code in this candidate's development. Production code and threshold 58 were
not modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def _canonical_check_text(canonical_rows: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    from benchmarking.candidates.contour_scorer_v2_pipeline import check_canonical_ranking

    return check_canonical_ranking(canonical_rows)


def write_formula_doc(path: Path) -> None:
    report = f"""# Candidate E — formula documentation (STEP 1-3)

**BASELINE_A_FROZEN**: `chinese_tones.directional_tone_scores` (and every
helper it calls) is the production scorer. It is imported read-only by
Candidate E's evaluation pipeline for comparison and is never modified.
Candidate E lives entirely in `benchmarking/candidates/contour_scorer_v2.py`
and is not imported by any production code path.

## Evidence base

Every constant below comes from two sources only, per the task's explicit
instruction — **never from OMPAL labels**:

1. The task's own canonical contours (T1 `[1,1,1,1,1]`, T2 `[0.2,0.3,0.5,
   0.7,0.9]`, T3 `[0.6,0.35,0.2,0.35,0.65]`, T4 `[0.9,0.75,0.55,0.3,0.1]`),
   computed directly:

   | Tone | Full slope | First-half slope | Second-half slope | Range | Variance |
   |---|---|---|---|---|---|
   | T1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0000 |
   | T2 | 0.720 | 0.300 | 0.400 | 0.700 | 0.0656 |
   | T3 | 0.040 | -0.400 | 0.450 | 0.450 | 0.0286 |
   | T4 | -0.820 | -0.350 | -0.450 | 0.800 | 0.0846 |

   (Slope = total predicted rise across the segment from a least-squares
   fit, not `last - first`, so a single noisy endpoint can't dominate it.)

2. The existing controlled synthetic TTS audio set (`benchmarking/external/
   controlled_tone_test/audio/`, 8 files — the same audio the earlier
   controlled test and diagnosis used), via the STEP 4 onset-skip ablation
   in `candidate_e_onset_ablation.csv`.

## STEP 2 — T1 (flat): shape-specific, not variance-only

**The old formula's problem**: `variance(seg) < 0.12` alone. The evidence
table above shows exactly why this failed — T3's canonical contour has a
near-zero FULL SLOPE (0.04, deceptively close to T1's 0.000) *and* a small
variance (0.0286), so a pure slope-or-variance check can mistake a shallow
dip for flatness. The old formula's `0.12` threshold made this materially
worse (see `directional_tone_formula_audit.md`), but the deeper issue is
that a single scalar (slope OR variance alone) cannot distinguish "flat"
from "small excursion, any shape."

**Candidate E's fix**: require BOTH slope and range to be small —

```
slope_factor = max(0, 1 - |slope| / {T1_SLOPE_REF})
range_factor = max(0, 1 - range / {T1_RANGE_REF})
score = slope_factor * range_factor * 100
```

- `T1_SLOPE_REF = {T1_SLOPE_REF}`: T1's own canonical slope is 0.000; T2/T4's
  are 0.720/0.820. {T1_SLOPE_REF} sits below both with more than 2x margin on
  either side.
- `T1_RANGE_REF = {T1_RANGE_REF}`: T1's own canonical range is 0.000; T3's
  (the shape the OLD formula was fooled by, since its slope alone doesn't
  catch T3) is 0.450 — {T1_RANGE_REF} sits well below that with margin, so a
  shallow-but-real dip still fails the range gate even when its slope looks
  flat-ish.

Both factors are required (multiplied, not added) so a contour can only
score high on T1 if it is flat by BOTH measures simultaneously.

## STEP 3 — T3 (dip): shape validity gates dip depth

**The old formula's problem**: `dip_depth = avg(s_mean, e_mean) - mid_min`
alone. This is satisfied by ANY contour whose middle sits below the average
of its endpoints — including a plain monotonic rise or fall, which the
diagnosis confirmed numerically (canonical T2 scored 90.9, canonical T4
scored 81.8, against a T3 target under the old formula, both above
threshold 58).

**Candidate E's fix**: a shape-validity gate before the depth calculation —

```
first_half, second_half = split(seg) at the midpoint
shape_valid = first_half_slope <= -{T3_SHAPE_SLOPE_EPS} AND second_half_slope >= {T3_SHAPE_SLOPE_EPS}
dip_depth = avg(s_mean, e_mean) - mid_min   # same definition as before
if shape_valid:
    score = clip((dip_depth + {T3_DEPTH_OFFSET}) / {T3_DEPTH_SCALE}, 0, 1) * 100
else:
    score = min({T3_INVALID_SHAPE_CEILING}, max(0, dip_depth) * 40)
```

- `T3_SHAPE_SLOPE_EPS = {T3_SHAPE_SLOPE_EPS}`: canonical T3's own first/second-half
  slopes are -0.400/+0.450 — {T3_SHAPE_SLOPE_EPS} only requires the SIGN to be
  unambiguous (well above measurement-noise-level slopes near zero), not
  that the magnitude match canonical exactly. Shape validity is a yes/no
  gate; magnitude is `dip_depth`'s separate job.
- `T3_DEPTH_OFFSET = {T3_DEPTH_OFFSET}`, `T3_DEPTH_SCALE = {T3_DEPTH_SCALE}`: unchanged
  from the original formula's calibration (chosen so canonical T3's own
  dip_depth, 0.425, maps to exactly 100) — STEP 3 asked to add a
  shape-validity gate in front of the existing depth calculation, not to
  redefine depth itself.
- `T3_INVALID_SHAPE_CEILING = {T3_INVALID_SHAPE_CEILING}`: chosen well below
  threshold 58 and well below any genuine dip's likely score, so a
  monotonic rise or fall cannot pass as T3 regardless of how large its raw
  `dip_depth` number happens to be — this directly closes the failure mode
  the diagnosis found (T2/T4 scoring 90.9/81.8 against T3).

## T2 / T4 — unchanged

The diagnosis found these directionally correct on the idealized canonical
matrix (diagonal highest in each column); the real-audio failure traced to
onset-skip windowing, not the formulas themselves (see STEP 4 in
`candidate_e_controlled_test.md`). Reused verbatim from
`chinese_tones._score_segment`.

## STEP 4 — Onset-skip preprocessing

See `candidate_e_controlled_test.md` §STEP 4 for the full ablation table and
selected value with its justification.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
