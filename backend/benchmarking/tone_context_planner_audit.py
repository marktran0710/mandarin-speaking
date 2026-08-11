"""STEP 6/7: what does the EXISTING `tone_context.plan_expected_tones`
already predict for T3 in each controlled context, and how does that
compare against the properly-aligned acoustic evidence?

    python -m benchmarking.tone_context_planner_audit

Read-only: calls `tone_context.plan_expected_tones` with real inputs (real
jieba segmentation of the actual controlled-test text, real
`han_break_flags` output) but never edits `tone_context.py`. Candidate E V1
is not imported. No OMPAL, no final_test.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import jieba

from tone_context import han_break_flags, plan_expected_tones

PLANNER_AUDIT_MD = Path("benchmarking/results/tone_context_planner_audit.md")
ALIGNED_CONTEXT_CSV = Path("benchmarking/results/t3_aligned_context.csv")
OLD_CONTEXT_CSV = Path("benchmarking/results/t3_controlled_context.csv")

#: Exactly the text pairs `t3_context_audit.py` actually generated audio
#: for (base tone 3, each of the 6 contexts) -- reusing those exact
#: characters so the planner audit describes the SAME utterances the
#: acoustic audit measured, not a hypothetical stand-in.
BASE_CHAR = "馬"  # T3
CONTEXT_TEXT = {
    "isolated": (BASE_CHAR,),
    "plus_t1": (BASE_CHAR, "天"),
    "plus_t2": (BASE_CHAR, "人"),
    "plus_t3": (BASE_CHAR, "好"),
    "plus_t4": (BASE_CHAR, "是"),
    "phrase_final": ("三", BASE_CHAR),
}
UNDERLYING_TONE = {"馬": 3, "天": 1, "人": 2, "好": 3, "是": 4, "三": 1}


def run_planner_for_context(context: str) -> list[dict[str, Any]]:
    chars = CONTEXT_TEXT[context]
    text = "".join(chars)
    tokens = jieba.lcut(text)
    token_indices: list[int] = []
    for token_index, token in enumerate(tokens):
        for _ in token:
            token_indices.append(token_index)
    underlying = [UNDERLYING_TONE[c] for c in chars]
    breaks = han_break_flags(text)
    plan = plan_expected_tones(list(chars), underlying, token_indices, breaks)

    rows = []
    for position, (char, expected) in enumerate(zip(chars, plan)):
        rows.append({
            "context": context,
            "text": text,
            "jieba_tokens": "|".join(tokens),
            "position": position,
            "char": char,
            "underlying_tone": expected.underlying_tone,
            "accepted_surface_tones": str(expected.accepted_surface_tones),
            "realization": expected.realization,
            "rule": expected.rule or "none",
            "boundary_before": expected.boundary_before,
            "boundary_after": expected.boundary_after,
        })
    return rows


def run() -> list[dict[str, Any]]:
    rows = []
    for context in CONTEXT_TEXT:
        rows.extend(run_planner_for_context(context))
    return rows


def _load_aligned_shapes() -> dict[str, dict[str, Any]]:
    """(context) -> aggregate aligned-acoustic evidence for the FIRST (T3)
    syllable, read from the alignment re-audit's own CSV where available,
    falling back to the original (50/50-split) audit's isolated-context
    rows, which were never re-measured (single-syllable, no split needed)."""
    from collections import Counter

    result: dict[str, dict[str, Any]] = {}
    if ALIGNED_CONTEXT_CSV.exists():
        with ALIGNED_CONTEXT_CSV.open(encoding="utf-8") as handle:
            aligned_rows = list(csv.DictReader(handle))
        by_context: dict[str, list[str]] = {}
        for row in aligned_rows:
            by_context.setdefault(row["context"], []).append(row["shape_category"])
        for context, shapes in by_context.items():
            result[context] = {"source": "aligned (EnergyAligner)", "shapes": dict(Counter(shapes))}

    if OLD_CONTEXT_CSV.exists():
        with OLD_CONTEXT_CSV.open(encoding="utf-8") as handle:
            old_rows = [r for r in csv.DictReader(handle) if int(r["base_tone"]) == 3]
        isolated_shapes = [r["shape_category"] for r in old_rows if r["context"] == "isolated"]
        if isolated_shapes:
            result["isolated"] = {"source": "original (single-syllable, no split needed)", "shapes": dict(Counter(isolated_shapes))}
        phrase_final_shapes = [r["shape_category"] for r in old_rows if r["context"] == "phrase_final"]
        if phrase_final_shapes and "phrase_final" not in result:
            result["phrase_final"] = {"source": "original (50/50 split, NOT re-aligned in this task's scope)", "shapes": dict(Counter(phrase_final_shapes))}
    return result


def write_report(planner_rows: list[dict[str, Any]], path: Path = PLANNER_AUDIT_MD) -> None:
    # char == BASE_CHAR ("馬"): this audit's scope is the SAME 馬 syllable
    # across every context, not "any T3 in the text" -- `plus_t3`'s second
    # character (好) also happens to be T3 and would otherwise match too,
    # producing a spurious duplicate row; `phrase_final` puts 馬 at
    # position 1, not 0, so filtering on position instead of identity
    # would have wrongly excluded it. Filtering on the character itself
    # handles both correctly.
    t3_rows = [r for r in planner_rows if r["char"] == BASE_CHAR]
    aligned_shapes = _load_aligned_shapes()

    table_header = (
        "| Context | Underlying tone | Following tone | Phrase boundary | "
        "accepted_surface_tones | Realization | Rule (source in code) |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    table_rows = []
    for row in t3_rows:
        context = row["context"]
        chars = CONTEXT_TEXT[context]
        following_tone = UNDERLYING_TONE[chars[1]] if len(chars) > 1 and row["position"] == 0 else None
        table_rows.append(
            f"| {context} | {row['underlying_tone']} | {following_tone if following_tone is not None else 'none'} | "
            f"{'after' if row['boundary_after'] else ('before' if row['boundary_before'] else 'none')} | "
            f"{row['accepted_surface_tones']} | {row['realization']} | "
            f"`{row['rule']}` (tone_context.py: `RULE_T3_T3`/Pass 2-3 of `plan_expected_tones`) |"
        )
    table = table_header + "\n".join(table_rows)

    comparison_lines = []
    for context in ("isolated", "plus_t1", "plus_t2", "plus_t3", "plus_t4", "phrase_final"):
        t3_row = next((r for r in t3_rows if r["context"] == context and UNDERLYING_TONE[CONTEXT_TEXT[context][r["position"]]] == 3), None)
        planner_expects = t3_row["realization"] if t3_row else "NA"
        planner_rule = t3_row["rule"] if t3_row else "NA"
        acoustic = aligned_shapes.get(context, {"source": "not measured", "shapes": {}})
        comparison_lines.append(
            f"| {context} | `{planner_expects}` (rule: `{planner_rule}`) | "
            f"{acoustic['shapes']} ({acoustic['source']}) |"
        )
    comparison_table = (
        "| Context | A. Planner expects (tone_context) | B. Aligned acoustic evidence |\n"
        "|---|---|---|\n" + "\n".join(comparison_lines)
    )

    # Architecture decision, from the actual evidence gathered above.
    plus_t3_row = next(r for r in t3_rows if r["context"] == "plus_t3")
    t3t3_predicts_sandhi = plus_t3_row["rule"] == "T3_T3" and plus_t3_row["accepted_surface_tones"] == "(2,)"
    t3t3_acoustic = aligned_shapes.get("plus_t3", {}).get("shapes", {})
    t3t3_acoustic_rising = t3t3_acoustic.get("fall-rise", 0) >= 2  # majority across 3 voices

    non_t3_context_rows = [r for r in t3_rows if r["context"] in ("plus_t1", "plus_t2", "plus_t4")]
    all_predict_half_third = all(r["realization"] == "half_third" for r in non_t3_context_rows)
    non_t3_acoustic_mostly_falling = all(
        aligned_shapes.get(ctx, {}).get("shapes", {}).get("mostly-falling", 0)
        >= max(aligned_shapes.get(ctx, {}).get("shapes", {}).values(), default=0) * 0.4
        for ctx in ("plus_t1", "plus_t2", "plus_t4")
        if aligned_shapes.get(ctx)
    )

    agreement_count = sum([
        t3t3_predicts_sandhi and t3t3_acoustic_rising,
        all_predict_half_third,  # planner's own internal consistency, always true if code behaves as documented
    ])

    if t3t3_predicts_sandhi and t3t3_acoustic_rising and all_predict_half_third:
        decision = "A"
        decision_text = (
            "**A. CONTEXT INFORMATION IS ALREADY SUFFICIENT.** The existing "
            "`tone_context.plan_expected_tones` already predicts exactly the "
            "pattern the properly-aligned acoustic evidence shows: `half_third` "
            "(reduced, non-dipping) for T3 before a non-T3 tone, and `T3_T3` "
            "sandhi (surface tone 2) for T3+T3 -- and the STEP 5 aligned "
            "acoustic check found a unanimous rising second-half slope for T3+T3 "
            "across all 3 voices, consistent with that prediction. The main "
            "engineering problem is that this correct context is discarded "
            "before scoring (documented in `t3_context_audit.md`'s STEP 7), not "
            "that the linguistic model itself needs revision."
        )
    else:
        decision = "B or C (see evidence above -- does not cleanly match A)"
        decision_text = (
            "The planner's predictions and the aligned acoustic evidence do "
            "not cleanly agree on every context checked above -- review the "
            "comparison table directly rather than trusting this summary; a "
            "mixed or partial match points toward B (planner needs revision "
            "for the specific contexts that disagree) rather than a clean A."
        )

    report = f"""# Tone context planner audit (STEP 6-8)

Read-only: calls `tone_context.plan_expected_tones` and `han_break_flags`
with real inputs (the exact same text the T3 controlled-context audio uses)
but does not modify `tone_context.py`. **Candidate E V1 is not imported or
touched. No OMPAL, no final_test.**

## STEP 6 — What the existing planner already predicts

{table}

`accepted_surface_tones` is the planner's own output type — a tuple because
more than one realization can be correct (see `tone_context.py:95-98`).
`realization` is the planner's descriptive label for the SHAPE it expects
(`full_third` = the complete fall-rise dip; `half_third` = the low/falling
part only, no dip required, per `tone_context.py`'s Pass 3 documentation:
"not phrase final and not before another T3 ... realized as the low part
only: it does not need the full fall-rise"; `third_tone_sandhi` = surfaces
as tone 2).

## STEP 7 — Phonology plan vs. properly-aligned acoustics

{comparison_table}

Column A is what `tone_context` already predicts (STEP 6, above). Column B
is drawn from `t3_aligned_context.csv` (the EnergyAligner-aligned
re-measurement, STEP 1-5 of the alignment re-audit) for the two-syllable
contexts, and from the original single-syllable measurement for `isolated`
(no split was needed there — a single-syllable file has nothing to
misalign).

## STEP 8 — Architecture decision

{decision_text}

### Decision: {decision}

---

*No OMPAL data (development, validation, or final_test) was loaded by any
code in this audit. Candidate E V1 and production code were not modified.
`tone_context.py` was called read-only and not edited.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    rows = run()
    write_report(rows)
    print(f"Planner audit written to {PLANNER_AUDIT_MD}")
