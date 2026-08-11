"""Report writers for Candidate E2's pipeline."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

THRESHOLD = 58.0


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


# ---------------------------------------------------------------------------
# STEP 1-5 design doc
# ---------------------------------------------------------------------------


def write_design_doc(path: Path) -> None:
    from benchmarking.candidates.context_aware_contour_scorer import (
        HALF_THIRD_FALL_OFFSET,
        HALF_THIRD_FALL_SCALE,
        HALF_THIRD_RISE_CEILING,
        HALF_THIRD_RISE_REJECT_SLOPE,
    )

    report = f"""# Candidate E2 — design (STEP 1-5)

**Candidate E V1 remains frozen** — imported read-only for its T1/T2/T3-full/
T4 formulas (`_score_t1`, `_score_t2`, `_score_t3`, `_score_t4`), never
edited. **`tone_context.py` is imported read-only and never edited** — no
planner rule was changed. **No OMPAL data anywhere in this candidate's
development.**

## STEP 1 — New harness, built on `ExpectedTone`

`benchmarking/candidates/context_aware_contour_scorer.py`'s entry point,
`score_segment_e2(seg, expected: tone_context.ExpectedTone)`, consumes the
SAME `ExpectedTone` object `tone_context.plan_expected_tones` already
produces — `underlying_tone`, `accepted_surface_tones`, `realization`,
`rule`, `token_index`, `boundary_before`/`boundary_after` are all read
directly from it, none reconstructed. Candidate E2 never calls
`plan_expected_tones` itself with different logic — every context decision
(what tone is acceptable, what shape it should take) still comes from
`tone_context.py`, unmodified. Candidate E2's only job is turning an
already-decided acceptable tone into a score.

## STEP 2 — Surface-realization routing

| `expected.realization` | Route |
|---|---|
| `canonical` (T1/T2/T4) | Candidate E V1's own unchanged `_score_t1`/`_score_t2`/`_score_t4` |
| `full_third` | Candidate E V1's own unchanged `_score_t3` (fall-then-rise dip) |
| `half_third` | NEW `_score_half_third` (STEP 4, below) |
| `third_tone_sandhi` / `third_tone_chain` | not routed directly — the accepted surface tone itself (2, or 2-and-3) determines the branch, per STEP 3/5 below |
| `neutral` | not scored (`75.0`, `"neutral_not_measured"` — same convention Candidate E V1 and production both already use) |

## STEP 3 — Multiple accepted realizations: max, not average

When `expected.accepted_surface_tones` names more than one tone (e.g. a
third-tone chain's `(2, 3)`), Candidate E2 scores the observed contour
against EVERY accepted tone and takes the **maximum**:

```
score = max(score_against_tone_a, score_against_tone_b, ...)
```

This is the only rule consistent with `ExpectedTone`'s own stated design —
`accepted_surface_tones` is a tuple specifically because "more than one
realization can be accepted" (tone_context.py:95-98: "A learner matching
*any* of them has not made a tone error"). Averaging would penalize a
learner for not ALSO matching an alternative they had no reason to
produce; only max is faithful to "any of them is correct."

## STEP 4 — Half-third scorer

T3 before a non-T3 tone (not phrase-final) is not scored against the full
fall-then-rise template — Candidate E V1's own dip formula would wrongly
penalize a genuinely correct reduced/half-third production (this is
exactly the failure the T3 context audit found: matched T3-before-non-T3
controlled audio scored near zero under Candidate E V1).

```
fall = s_mean - e_mean          # same quarter-region primitive E V1 already uses
base_score = clip((fall + {HALF_THIRD_FALL_OFFSET}) / {HALF_THIRD_FALL_SCALE}, 0, 1) * 100
if second_half_slope > {HALF_THIRD_RISE_REJECT_SLOPE}:
    score = min(base_score, {HALF_THIRD_RISE_CEILING})
else:
    score = base_score
```

- `HALF_THIRD_FALL_OFFSET = {HALF_THIRD_FALL_OFFSET}` (vs. Candidate E V1's T4
  offset of 0.5): a genuinely flat contour (`fall = 0`) scores 70 —
  comfortably accepted, since the task's own instruction is explicit that
  half-third has "no requirement for late rise" and is "predominantly low
  / falling" (flat included, not just falling). A clearly falling contour
  (`fall >= 0.3`, well within the aligned controlled evidence's observed
  range) reaches 100.
- `HALF_THIRD_RISE_REJECT_SLOPE = {HALF_THIRD_RISE_REJECT_SLOPE}`: from
  `t3_aligned_context.csv` (EnergyAligner-aligned, no OMPAL): every
  half-third context's (`plus_t1`/`plus_t2`/`plus_t4`) second-half slope
  measured at most +0.057 across all 3 voices, while every T3+T3 sandhi
  case's (which never reaches this function — see STEP 5) second-half
  slope measured at least +0.467. {HALF_THIRD_RISE_REJECT_SLOPE} sits with
  more than 2x margin above the half-third noise ceiling and more than 3x
  margin below the sandhi group's floor — a clean, evidenced separation,
  not an arbitrary round number.
- `HALF_THIRD_RISE_CEILING = {HALF_THIRD_RISE_CEILING}`: same value and
  rationale as Candidate E V1's `T3_INVALID_SHAPE_CEILING` — well below
  threshold territory, so a clear rise cannot pass as a reduced T3
  regardless of how the base fall/flat component alone would have scored.

## STEP 5 — T3+T3 sandhi: no separate formula

The planner already resolves the first T3 in a T3+T3 pair to
`accepted_surface_tones = (2,)` with `rule = "T3_T3"`. Candidate E2 does
not special-case this anywhere — `score_segment_e2`'s generic routing (STEP
2/3) sends tone 2 straight to Candidate E V1's own unchanged `_score_t2`
(the rise formula), because that is what "the accepted surface tone is 2"
already means. No new "sandhi T3 shape formula" was written, per the task's
explicit instruction: "Do not create a separate arbitrary sandhi T3 shape
formula unless the planner requires one" — it doesn't; the planner already
names tone 2, and tone 2 already has a scorer.

## Underlying tone != scored surface realization

This is the single governing principle behind every routing decision above:
`expected.underlying_tone` (what the character's citation-form dictionary
tone is) and what Candidate E2 actually scores the audio against
(`accepted_surface_tones`, informed by `realization`) are allowed to
differ, and for T3 specifically usually do. Candidate E V1 (and production)
have no such distinction — they always score against the underlying tone
directly, which is exactly the architecture gap the prior audits
identified.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# STEP 6 -- T3-context test report
# ---------------------------------------------------------------------------


def write_t3_context_report(rows: list[dict[str, Any]], path: Path) -> None:
    contexts = ("isolated", "plus_t1", "plus_t2", "plus_t3", "plus_t4", "phrase_final")
    sections = []
    for context in contexts:
        context_rows = [r for r in rows if r["context"] == context]
        header = (
            "| Voice | Realization | Rule | Accepted tones | E V1 score | E V1 pass | "
            "E2 score | E2 pass | E2 matched tone |\n|---|---|---|---|---|---|---|---|---|\n"
        )
        body = []
        for r in context_rows:
            if r["error"]:
                body.append(f"| {r['voice']} | | | | | | | | ERROR: {r['error']} |")
                continue
            body.append(
                f"| {r['voice']} | `{r['realization']}` | `{r['rule']}` | {r['accepted_surface_tones']} | "
                f"{_fmt(r['e_v1_score'])} | {r['e_v1_pass']} | "
                f"{_fmt(r['e2_score'])} | {r['e2_pass']} | {r['e2_matched_tone']} |"
            )
        n = len(context_rows)
        e_v1_pass_count = sum(1 for r in context_rows if r.get("e_v1_pass") == 1)
        e2_pass_count = sum(1 for r in context_rows if r.get("e2_pass") == 1)
        sections.append(f"""
### {context}

Acceptance rate: Candidate E V1 = {e_v1_pass_count}/{n}, Candidate E2 = {e2_pass_count}/{n}

{header}{chr(10).join(body)}
""")

    total_n = len(rows)
    e_v1_total_pass = sum(1 for r in rows if r.get("e_v1_pass") == 1)
    e2_total_pass = sum(1 for r in rows if r.get("e2_pass") == 1)

    # T1/T2/T4 are not part of this test (T3-context only, per STEP 6's
    # scope), so "does not make unrelated tones universally pass" is
    # checked in STEP 7's 32-case test instead -- noted here for clarity.

    report = f"""# Candidate E2 — T3 context test (STEP 6)

**Candidate E V1 remains frozen.** All {total_n} tokens (6 contexts x 3
voices) use the SAME `EnergyAligner` alignment for every context, including
`isolated` (trivially the whole file, `syllable_count=1`) and
`phrase_final` (now properly aligned too, extending the previous task's
4-context scope) — no crude 50/50 split anywhere in this report.

## Overall: known-correct T3-context tokens

Of {total_n} known-correct T3 productions (every token here IS the correct
tone for its context, by construction — these are reference recordings,
not mismatch cases):

- Candidate E V1 accepts {e_v1_total_pass} of {total_n} ({_fmt(e_v1_total_pass / total_n, 2)})
- Candidate E2 accepts {e2_total_pass} of {total_n} ({_fmt(e2_total_pass / total_n, 2)})

## Per-context detail
{"".join(sections)}

---

*No OMPAL data (development, validation, or final_test) was loaded by any
code in this test. Candidate E V1 and `tone_context.py` were not modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# STEP 7 -- 32-case controlled test report + predictions CSV
# ---------------------------------------------------------------------------


_PREDICTIONS_FIELDS = [
    "case_id", "family", "audio_file", "audio_character", "audio_tone",
    "reference_character", "reference_tone", "expected_tone_correct",
    "baseline_a_score", "baseline_a_judged", "baseline_a_pass",
    "e_v1_score", "e_v1_pass", "e2_score", "e2_pass", "e2_matched_tone",
]


def write_predictions_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_PREDICTIONS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in _PREDICTIONS_FIELDS})


def _confusion_table_3way(overall: dict[str, dict[str, Any]]) -> str:
    header = "| Metric | Baseline A | Candidate E V1 | Candidate E2 |\n|---|---|---|---|\n"
    rows = [
        ("N (scored)", "n", 0), ("Accuracy", "accuracy", 3), ("Balanced accuracy", "balanced_accuracy", 3),
        ("Sensitivity", "sensitivity", 3), ("Specificity", "specificity", 3),
        ("False rejection rate", "false_rejection_rate", 3), ("False acceptance rate", "false_acceptance_rate", 3),
    ]
    body = [
        f"| {label} | {_fmt(overall['baseline_a'].get(key), digits)} | "
        f"{_fmt(overall['e_v1'].get(key), digits)} | {_fmt(overall['e2'].get(key), digits)} |"
        for label, key, digits in rows
    ]
    return header + "\n".join(body)


def _by_tone_table_3way(by_tone: dict[int, dict[str, Any]]) -> str:
    header = (
        "| Tone | N | Baseline A acc. | E V1 acc. | E2 acc. | E V1 bal. acc. | E2 bal. acc. |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for tone in (1, 2, 3, 4):
        entry = by_tone[tone]
        rows.append(
            f"| T{tone} | {entry['e2'].get('n', 0)} | {_fmt(entry['baseline_a'].get('accuracy'))} | "
            f"{_fmt(entry['e_v1'].get('accuracy'))} | {_fmt(entry['e2'].get('accuracy'))} | "
            f"{_fmt(entry['e_v1'].get('balanced_accuracy'))} | {_fmt(entry['e2'].get('balanced_accuracy'))} |"
        )
    return header + "\n".join(rows)


def _scale_table(scale_audit: dict[str, dict[str, Any]]) -> str:
    header = "| Category | N | Min | Median | Max |\n|---|---|---|---|---|\n"
    rows = [
        f"| {name} | {entry['n']} | {_fmt(entry['min'])} | {_fmt(entry['median'])} | {_fmt(entry['max'])} |"
        for name, entry in scale_audit.items()
    ]
    return header + "\n".join(rows)


def known_limitations(t3_context_rows: list[dict[str, Any]]) -> list[str]:
    limitations = []
    isolated = [r for r in t3_context_rows if r["context"] == "isolated" and r.get("e2_score") is not None]
    if isolated:
        low = [r for r in isolated if r["e2_score"] < THRESHOLD]
        if low:
            limitations.append(
                f"Isolated T3 (full_third realization) still uses Candidate E V1's unchanged "
                f"fall-rise formula, which does not accept every voice's isolated T3 rendering "
                f"({len(low)} of {len(isolated)} isolated tokens score below {THRESHOLD}) -- "
                f"this is an inherited Candidate E V1 property, not something Candidate E2's "
                f"context routing addresses (isolated T3 has no context to route on)."
            )
    phrase_final = [r for r in t3_context_rows if r["context"] == "phrase_final" and r.get("e2_score") is not None]
    if phrase_final:
        low = [r for r in phrase_final if r["e2_score"] < THRESHOLD]
        if low:
            limitations.append(
                f"Phrase-final T3 ({len(low)} of {len(phrase_final)} tokens below {THRESHOLD}) shows "
                f"the same inherited full-dip-formula limitation as isolated T3."
            )
    limitations.append(
        "Candidate E2 has not been evaluated on OMPAL data of any kind -- every number in this "
        "candidate's results comes from canonical reasoning and the controlled synthetic T3 "
        "context dataset only."
    )
    limitations.append(
        "Third-tone-chain (3+ consecutive T3s, accepted_surface_tones=(2,3)) routing is "
        "implemented (STEP 3's max-over-accepted-tones logic covers it generically) but was not "
        "exercised by any controlled test case in this task -- the controlled dataset has no "
        "T3+T3+T3 sequence."
    )
    return limitations


def write_controlled_report(
    rows: list[dict[str, Any]], comparison: dict[str, Any], scale_audit: dict[str, Any],
    t3_context_rows: list[dict[str, Any]], path: Path,
) -> str:
    # Materially regress check for STEP 7's explicit requirement.
    regressions = []
    for tone in (1, 2, 4):
        e1_acc = comparison["by_tone"][tone]["e_v1"].get("accuracy")
        e2_acc = comparison["by_tone"][tone]["e2"].get("accuracy")
        if e1_acc is not None and e2_acc is not None and e2_acc < e1_acc - 0.01:
            regressions.append(f"T{tone}: E V1={_fmt(e1_acc)} -> E2={_fmt(e2_acc)}")

    t3_context_pass_rate = None
    t3_context_total = len(t3_context_rows)
    if t3_context_total:
        t3_context_pass_rate = sum(1 for r in t3_context_rows if r.get("e2_pass") == 1) / t3_context_total
    e_v1_t3_context_pass_rate = (
        sum(1 for r in t3_context_rows if r.get("e_v1_pass") == 1) / t3_context_total if t3_context_total else None
    )

    substantially_larger = (
        t3_context_pass_rate is not None and e_v1_t3_context_pass_rate is not None
        and t3_context_pass_rate >= e_v1_t3_context_pass_rate + 0.15
    )

    non_t3_unrelated_pass_check = all(
        comparison["by_tone"][tone]["e2"].get("accuracy") is not None
        and abs(comparison["by_tone"][tone]["e2"].get("accuracy") - comparison["by_tone"][tone]["e_v1"].get("accuracy", 0)) < 0.02
        for tone in (1, 2, 4)
    )

    if not regressions and substantially_larger:
        verdict = "A"
        verdict_text = (
            "**A. Candidate E2 fixes the context-loss architecture problem on controlled data.** "
            f"T3-context acceptance rose from {_fmt(e_v1_t3_context_pass_rate)} (Candidate E V1) to "
            f"{_fmt(t3_context_pass_rate)} (Candidate E2) on known-correct controlled tokens, "
            "without materially regressing T1/T2/T4 (see the per-tone table above) and without "
            "the unrelated-tone formulas changing at all (T1/T2/T4 routing is byte-identical to "
            "Candidate E V1)."
        )
    elif not regressions and t3_context_pass_rate is not None and e_v1_t3_context_pass_rate is not None and t3_context_pass_rate > e_v1_t3_context_pass_rate:
        verdict = "B"
        verdict_text = (
            f"**B. Candidate E2 improves context handling but remains insufficient.** "
            f"T3-context acceptance improved from {_fmt(e_v1_t3_context_pass_rate)} to "
            f"{_fmt(t3_context_pass_rate)} but not substantially (below the +0.15 bar fixed before "
            "this comparison was run), and/or the per-context detail in "
            "`candidate_e2_t3_context_test.md` shows the improvement is uneven across contexts."
        )
    else:
        verdict = "C"
        verdict_text = (
            "**C. Context-aware routing does not solve the controlled failure.** "
            + (f"T1/T2/T4 regressed: {'; '.join(regressions)}. " if regressions else "")
            + "See the per-tone and per-context tables above for the specific failure."
        )

    report = f"""# Candidate E2 — controlled test (STEP 7, 9)

**Candidate E V1 remains frozen** (imported read-only). **No OMPAL data,
no final_test.**

## STEP 7 — 32-case controlled test: Baseline A vs Candidate E V1 vs Candidate E2

Every case here is a SINGLE isolated syllable (the same 32-case design
Candidate E V1 was evaluated on) — there is no multi-syllable context for
Candidate E2 to route on, so Candidate E2's T1/T2/T4 formulas and its
FULL_THIRD-realization T3 formula are exactly Candidate E V1's own
(byte-identical routing, per STEP 2). This test's purpose is to confirm
Candidate E2 does not regress the case Candidate E V1 already covers, not
to show new improvement — the new improvement is STEP 6's multi-syllable
T3-context test, above/below.

{_confusion_table_3way(comparison['overall'])}

### Per target tone

{_by_tone_table_3way(comparison['by_tone'])}

{"**No T1/T2/T4 regression detected.**" if not regressions else "**Regression(s) detected:** " + "; ".join(regressions)}

Full per-case predictions in `candidate_e2_controlled_predictions.csv`.

## STEP 9 — Score-scale audit

{_scale_table(scale_audit)}

{"Ranges are close enough that one global threshold remains plausible." if all(
    scale_audit[k]['median'] is not None for k in scale_audit
) and (max(v['median'] for v in scale_audit.values() if v['median'] is not None) - min(v['median'] for v in scale_audit.values() if v['median'] is not None)) < 25 else
"Medians span more than 25 points across categories — tone/context-specific calibration would likely be required for a single global threshold to treat every category comparably; this report does not choose one, per the task's explicit instruction."}

## Verdict

{verdict_text}

### {verdict}

---

*No OMPAL data (development, validation, or final_test) was loaded by any
code in this test. Candidate E V1, `tone_context.py`, and production code
were not modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return verdict
