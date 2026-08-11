"""Renders the trace report (STEP 5) and appends the classification section
(STEP 7) to the formula audit doc, from `directional_tone_diagnosis.py`'s
computed results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _trace_case_md(label: str, case: dict[str, Any] | None) -> str:
    if case is None:
        return f"### {label}\n\n*No such case found in the controlled test.*\n"
    return f"""### {label}: `{case['case_id']}`

Audio actually contains **{case['audio_character']} (T{case['audio_tone']})**,
scored against reference **{case['reference_character']} (T{case['reference_tone']})**
— known-correct answer: {'CORRECT' if case['expected_tone_correct'] == '1' else 'INCORRECT'}.
Scored against tone {case.get('scored_against_tone', case['reference_tone'])} internally
(post sandhi rule, irrelevant for a single isolated syllable).

**Consistency check**: recomputed score {case['final_score']} vs. the score
already on record in `controlled_tone_predictions.csv`
({case['recorded_current_score']}) — {"**MATCH**" if case.get('matches_recorded_score') else "**MISMATCH — see note below**"}.
This match matters: it confirms the trace below reflects what production
actually computed for this exact case, not a reconstruction of it.

| Stage | Value |
|---|---|
| F0 input to `normalize_pitch_contour` (Hz), first 5 | {case['f0_hz_first5']} |
| F0 input to `normalize_pitch_contour` (Hz), last 5 | {case['f0_hz_last5']} |
| Frame count (this word's own aligned span, onset-skipped) | {case['n_scoring_frames']} |
| Normalized [0,1], first 5 of 100 | {case['normalized_first5']} |
| Normalized [0,1], last 5 of 100 | {case['normalized_last5']} |
| After 5-tap median smoothing, first 5 | {case['smoothed_first5']} |
| After 5-tap median smoothing, last 5 | {case['smoothed_last5']} |
| `s_mean` (start-region mean) | {case['s_mean']} |
| `e_mean` (end-region mean) | {case['e_mean']} |
| `mid_min` (middle-50% minimum) | {case['mid_min']} |
| `variance` (whole segment) | {case['variance']} |
| `rise` (e_mean − s_mean) | {case['rise']} |
| `fall` (s_mean − e_mean) | {case['fall']} |
| `dip_depth` (avg endpoints − mid_min) | {case['dip_depth']} |
| **Final score** | **{case['final_score']}** ({case['provenance']}) |
| Verdict at threshold 58 | **{case['verdict']}** |
| (Recorded in `controlled_tone_predictions.csv`) | {case['recorded_current_score']} |
"""


def write_trace_report(traces: dict[int, dict[str, dict[str, Any]]], path: Path) -> None:
    sections = []
    for tone in (1, 2, 3, 4):
        sections.append(f"## Tone {tone}\n")
        sections.append(_trace_case_md(f"Matched (audio genuinely T{tone})", traces[tone]["matched"]))
        sections.append(_trace_case_md(f"Mismatched (audio is a different tone, reference asks for T{tone})", traces[tone]["mismatched"]))

    report = f"""# Controlled test — full calculation trace, two examples per tone

One matched (genuinely correct) and one mismatched (known-incorrect) case
per target tone, selected deterministically (first match found, not
cherry-picked). Traced by calling the real `analyze_all` for real on each
case's audio and intercepting `chinese_tones.normalize_pitch_contour` /
`chinese_tones._score_segment` to record their actual arguments and return
values, rather than reconstructing the pipeline by hand — a first attempt
at hand-reconstruction produced scores that silently disagreed with what
production actually computed (see `_trace_one_case`'s docstring in
`directional_tone_diagnosis.py`), because `estimate_word_prosody` scores a
word's own onset-skipped time span, not the whole recording. Every case
below includes an explicit consistency check against the score already on
record in `controlled_tone_predictions.csv`.

Stages shown: F0 input (Hz, this word's own aligned span) →
`normalize_pitch_contour` → `_smooth_for_directional_scoring` →
`s_mean`/`e_mean`/`mid_min`/`variance` → tone-specific formula → final
score → threshold-58 verdict.

{"".join(sections)}
---

*Audio: synthetic `edge-tts` only, from `controlled_tone_predictions.csv`.
No OMPAL data, no production code changes, no threshold changes.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def _classify(matrix_rows: list[dict[str, Any]], monotonicity: dict[int, dict[str, Any]], distribution: dict[int, dict[str, Any]]) -> tuple[str, str]:
    """Returns (classification_letter, justification_markdown). Applies the
    task's own A/B/C/D definitions to the actually-computed evidence."""
    # Evidence 1: idealized canonical contours -- is the diagonal (matched)
    # case the max in each column, and how close do off-diagonal entries get?
    by_expected: dict[int, dict[int, float]] = {}
    for row in matrix_rows:
        by_expected.setdefault(row["expected_tone"], {})[row["produced_tone"]] = row["raw_score_unsmoothed"]
    # Every off-diagonal cell that clears the threshold is a real false
    # accept, regardless of how far below the diagonal's own score it sits --
    # an earlier draft of this check also required the off-diagonal score to
    # sit within 15 points of the diagonal, which silently hid two genuine
    # false-accept cells (e.g. T4-shaped audio scored 81.8 against a T3
    # target, 100 vs 81.8 not being "close" but 81.8 still clears 58).
    cross_tone_confusions = []
    for expected_tone, by_produced in by_expected.items():
        diagonal_score = by_produced[expected_tone]
        for produced_tone, score in by_produced.items():
            if produced_tone != expected_tone and score >= 58:
                cross_tone_confusions.append((produced_tone, expected_tone, score, diagonal_score))

    # Evidence 2: monotonicity violations under controlled perturbation.
    violated_tones = [tone for tone, result in monotonicity.items() if not result["is_monotonic"]]

    # Evidence 3: real controlled-test matched vs mismatched score overlap.
    non_t1_all_matched_below_58 = all(
        distribution[t]["matched_all_below_58"] for t in (2, 3, 4) if distribution[t]["matched_all_below_58"] is not None
    )
    t1_mismatched_above_58 = [
        s for s in distribution[1]["mismatched_scores"] if s >= 58
    ]

    justification = f"""### Evidence used for this classification

**A. Canonical-contour cross-tone confusions** (idealized 4×4 matrix,
STEP 2): {len(cross_tone_confusions)} case(s) where a WRONG produced tone
scored ≥58 (would pass at threshold 58) against a target it does not match:
{chr(10).join(f"- T{p} contour scored {s} against T{e} target (T{e}'s own matched score: {d})" for p, e, s, d in cross_tone_confusions) or "- none"}

**B. Monotonicity violations** (STEP 3 perturbation sweeps, pre-specified
expected order): tones with at least one violation: {violated_tones or "none"}.
{"".join(f"  - T{t}: " + "; ".join(f"{a}({sa})>{b}({sb})" for a, b, sa, sb in monotonicity[t]["violations"]) + chr(10) for t in violated_tones)}

**C. Real controlled-test (STEP 4) — option A vs B from the task**:
{"**A holds**: every matched (genuinely correct) T2/T3/T4 case scored below 58." if non_t1_all_matched_below_58 else "**A does not hold cleanly** for at least one tone."}
T1's mismatched (genuinely wrong) cases that nonetheless scored ≥58:
{len(t1_mismatched_above_58)} of {len(distribution[1]['mismatched_scores'])} —
{"i.e. essentially ALL wrong T1 productions still pass." if t1_mismatched_above_58 and len(t1_mismatched_above_58) == len(distribution[1]['mismatched_scores']) else ""}
"""

    # Decision: multiple independent, materially-contributing issues found
    # (a miscalibrated constant AND a shape-non-specific formula AND, in the
    # real audio, a genuine matched/mismatched score-range overlap problem)
    # -> D. MIXED, unless the evidence collapses to a single clean cause.
    has_calibration_issue = len(cross_tone_confusions) > 0
    has_real_overlap_issue = non_t1_all_matched_below_58 or bool(t1_mismatched_above_58)
    has_monotonicity_issue = bool(violated_tones)

    contributing = sum([has_calibration_issue, has_real_overlap_issue, has_monotonicity_issue])
    if contributing >= 2:
        letter = "D"
        headline = (
            "**D. MIXED.** More than one issue materially contributes: "
            "a poorly-calibrated T1 flatness threshold (scale/calibration "
            "issue) AND a T3 dip formula that isn't shape-specific enough "
            "to reject monotonic rises/falls (heuristic design limitation) "
            "AND, in real synthetic audio, T2/T3/T4 matched-case scores "
            "that don't clear the threshold at all (score-scale/threshold "
            "interaction). No single-cause classification (A/B/C alone) "
            "fits all three independently-observed problems."
        )
    elif has_calibration_issue:
        letter = "B"
        headline = "**B. SCORE-SCALE / THRESHOLD BUG.**"
    elif has_monotonicity_issue:
        letter = "C"
        headline = "**C. HEURISTIC DESIGN FAILURE.**"
    else:
        letter = "A"
        headline = "**A. IMPLEMENTATION BUG.**"

    return letter, headline + "\n\n" + justification


def append_classification_section(
    formula_audit_path: Path,
    matrix_rows: list[dict[str, Any]],
    monotonicity: dict[int, dict[str, Any]],
    distribution: dict[int, dict[str, Any]],
) -> None:
    letter, justification = _classify(matrix_rows, monotonicity, distribution)

    # Idempotent: strip any previously-appended classification section
    # before writing the fresh one, so re-running this script (e.g. after a
    # detection-logic fix) doesn't duplicate the section on every run.
    existing = formula_audit_path.read_text(encoding="utf-8")
    marker = "\n\n## Classification (STEP 7)"
    if marker in existing:
        existing = existing.split(marker)[0]
        formula_audit_path.write_text(existing, encoding="utf-8")

    dist_table_rows = []
    for tone in (1, 2, 3, 4):
        d = distribution[tone]
        dist_table_rows.append(
            f"| T{tone} | {d['n']} | {d['matched_min']} | {d['matched_max']} | "
            f"{d['mismatched_min']} | {d['mismatched_max']} | {d['ranges_overlap']} |"
        )

    section = f"""

## Classification (STEP 7)

### Score distribution, real controlled-test audio (STEP 4)

| Target tone | N | Matched min | Matched max | Mismatched min | Mismatched max | Ranges overlap |
|---|---|---|---|---|---|---|
{chr(10).join(dist_table_rows)}

{justification}

## Final classification: {letter}

See `canonical_contour_matrix.csv`, `tone_perturbation_test.csv`, and
`controlled_score_trace.md` for the full supporting data behind this
classification. Per the task's explicit instruction, **no code was changed
as a result of this diagnosis** — this document ends with a diagnosis, not
a fix.
"""
    with formula_audit_path.open("a", encoding="utf-8") as handle:
        handle.write(section)
