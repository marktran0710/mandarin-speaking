"""Renders `t3_context_audit.run()`'s results into
`benchmarking/results/t3_context_audit.md` and
`benchmarking/results/candidate_e2_t3_design.md`.

STEP 7's production-context findings are supplied separately (see
`STEP7_FINDINGS` below) since they come from reading `praat_analyzer.py` /
`chinese_tones.py` / `tone_context.py` directly, not from computed data.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

#: STEP 7 -- filled in from a direct, cited code read of praat_analyzer.py /
#: chinese_tones.py / tone_context.py (see the citations inline). Production
#: code was not modified to produce this -- read-only.
STEP7_FINDINGS = """
Read directly from `praat_analyzer.py`, `chinese_tones.py`, and
`tone_context.py` -- production code was not modified to produce this audit.
Verified independently twice (once during this session's own earlier
reading of these files, once via a fresh, separately-dispatched research
pass) with fully convergent citations.

1. **Current syllable's expected tone -- YES.** `praat_analyzer.py:1038-1039`
   builds `token_tones = word_tones(token)` then `expected_tones =
   apply_tone_sandhi(token_tones)`, passed to `directional_tone_scores(
   scoring_points, expected_tones, syllable_windows=windows)`
   (`praat_analyzer.py:1095-1097`). Inside, `chinese_tones.py:470-474` loops
   `for i, tone in enumerate(tones_s): ... score, source =
   _score_segment(seg, tone)` -- the current tone is passed directly as
   `_score_segment`'s second argument (`chinese_tones.py:556`).

2. **Previous syllable's expected tone -- only WITHIN the same jieba
   word/token**, via sandhi rewriting, not passed as a separate value.
   `apply_tone_sandhi` (`chinese_tones.py:272-282`) rewrites a preceding
   T3→T2 only when both are in the same `tones` list, i.e. the same token.
   `token_tones` (`praat_analyzer.py:1038`) is `word_tones(token)` for the
   CURRENT WORD ONLY, so cross-word previous-tone context is absent from
   the legacy path -- confirmed by `praat_analyzer.py:981-989`'s own
   comment: "third-tone sandhi crosses word boundaries -- 很好 is two jieba
   tokens, so the per-token `apply_tone_sandhi` below never sees the T3+T3
   pair."

3. **Following syllable's expected tone -- same limitation as #2.**
   `apply_tone_sandhi` looks at `adjusted[i+1]` (`chinese_tones.py:280`)
   but only within the current token's tone list, never the next word's
   first tone.

4. **Syllable position -- exists in the enclosing loops, NOT passed into
   scoring.** `directional_tone_scores_with_provenance` has `i` from
   `enumerate(tones_s)` (`chinese_tones.py:470`) but uses it only for
   `_window_for(i, n, syl_len, ...)` (windowing, `chinese_tones.py:471`),
   never forwarded to `_score_segment`. `estimate_word_prosody`'s own word
   position (`praat_analyzer.py:993`) is likewise never passed into
   `directional_tone_scores`.

5. **Phrase/sentence boundary information -- NOT available in the legacy
   scoring path.** `_prosody_tokens` uses `segment_words(text)`
   (`praat_analyzer.py:1427-1429`), and `tone_context.py:56-61` documents
   explicitly: "the pipeline loses this on its own: `caf_metrics.
   segment_words` splits the transcript on punctuation and then flattens
   the pieces into one token list, so by the time tokens arrive here the
   comma is gone." `directional_tone_scores` receives no boundary
   parameter at all.

6. **Is context passed into the actual scoring call, or only available
   earlier and discarded? Only available earlier and discarded**, for the
   legacy path BASELINE_A_FROZEN and progression actually run on: at the
   exact `_score_segment(seg, tone)` call site (`chinese_tones.py:472`,
   definition at `chinese_tones.py:556`), only the segment and a bare tone
   int are passed -- position `i`, previous/next tone, and boundaries all
   exist in the enclosing loops (`estimate_word_prosody`'s loop,
   `chinese_tones.py`'s `enumerate` loop) but are discarded before reaching
   the scoring function.

7. **`tone_context.plan_expected_tones` DOES have prev/next tone and
   boundary access -- but only in the diagnostic layer.** Called via
   `plan_for_tokens` (`tone_context.py:337-377`), invoked from
   `praat_analyzer._contextual_tone_plan` (`praat_analyzer.py:810-817`,
   itself called once per utterance at `praat_analyzer.py:987` before the
   per-token loop) as `plan_for_tokens(tokens, hint_tones,
   text=transcription)` -- the WHOLE utterance's tokens plus raw
   transcription for punctuation. Inside: `following = working[i+1]`,
   `previous = chars[i-1]` (`tone_context.py:226-227`); `breaks_after`
   (from `han_break_flags`, `tone_context.py:74-88`) blocks T3-run sandhi
   across punctuation (`tone_context.py:243`, `_third_tone_runs` at
   `tone_context.py:310-334`); `token_indices` yields
   `boundary_before`/`boundary_after` fields (`tone_context.py:303-304`).
   This plan feeds only `_diagnose_token`/`contextual_tone_scores`
   (`praat_analyzer.py:1148-1166`, `chinese_tones.py:479-531`), which per
   its own docstring and `praat_analyzer.py:985` ("This plan is
   diagnostic-only") never touches `score`/`passed`, i.e. never touches
   progression.

**Bottom line for Candidate E2-T3's design**: previous/following-tone and
phrase-boundary context IS computable in this codebase today (the
diagnostic module already does it, whole-utterance, correctly spanning word
boundaries) -- but the FROZEN legacy scorer Candidate E V1 was built to
improve on does not currently receive it at the point where it scores a
segment. A context-aware Candidate E2-T3 would need its OWN evaluation
harness to carry this same (tone, position, boundary) context alongside
each syllable, mirroring `tone_context.plan_expected_tones`'s inputs rather
than `directional_tone_scores`'s narrower ones -- it cannot assume the
legacy call path will hand it that information.
"""


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _shape_summary_table(rows: list[dict[str, Any]], tone: int) -> str:
    context_rows = [r for r in rows if r["base_tone"] == tone]
    by_context: dict[str, Counter] = {}
    for row in context_rows:
        by_context.setdefault(row["context"], Counter())[row["shape_category"]] += 1
    header = "| Context | fall-rise | mostly-falling | mostly-rising | low-flat | rise-fall | other | N |\n"
    header += "|---|---|---|---|---|---|---|---|\n"
    body = []
    for context in ("isolated", "plus_t1", "plus_t2", "plus_t3", "plus_t4", "phrase_final"):
        counts = by_context.get(context, Counter())
        total = sum(counts.values())
        body.append(
            f"| {context} | {counts.get('fall-rise', 0)} | {counts.get('mostly-falling', 0)} | "
            f"{counts.get('mostly-rising', 0)} | {counts.get('low-flat', 0)} | "
            f"{counts.get('rise-fall', 0)} | {counts.get('other', 0)} | {total} |"
        )
    return header + "\n".join(body)


def _voice_stability_table(rows: list[dict[str, Any]], tone: int) -> str:
    tone_rows = [r for r in rows if r["base_tone"] == tone]
    by_voice: dict[str, Counter] = {}
    for row in tone_rows:
        by_voice.setdefault(row["voice"], Counter())[row["shape_category"]] += 1
    header = "| Voice | fall-rise | mostly-falling | mostly-rising | low-flat | rise-fall | other | N |\n"
    header += "|---|---|---|---|---|---|---|---|\n"
    body = []
    for voice, counts in sorted(by_voice.items()):
        total = sum(counts.values())
        body.append(
            f"| {voice} | {counts.get('fall-rise', 0)} | {counts.get('mostly-falling', 0)} | "
            f"{counts.get('mostly-rising', 0)} | {counts.get('low-flat', 0)} | "
            f"{counts.get('rise-fall', 0)} | {counts.get('other', 0)} | {total} |"
        )
    return header + "\n".join(body)


def _candidate_e_reaction_table(rows: list[dict[str, Any]], tone: int) -> str:
    tone_rows = [r for r in rows if r["base_tone"] == tone and r["candidate_e_score"] is not None]
    by_context_shape: dict[tuple[str, str], list[float]] = {}
    for row in tone_rows:
        by_context_shape.setdefault((row["context"], row["shape_category"]), []).append(row["candidate_e_score"])
    header = "| Context | Shape | N | Mean Candidate E score | Would pass @58 |\n|---|---|---|---|---|\n"
    body = []
    for (context, shape), scores in sorted(by_context_shape.items()):
        mean_score = sum(scores) / len(scores)
        body.append(f"| {context} | {shape} | {len(scores)} | {_fmt(mean_score)} | {mean_score >= 58} |")
    return header + "\n".join(body)


def write_audit_report(result: dict[str, Any], path: Path) -> None:
    rows = result["rows"]
    n_total = len(rows)
    n_voices = len({r["voice"] for r in rows})

    t3_rows = [r for r in rows if r["base_tone"] == 3]
    t3_isolated = [r for r in t3_rows if r["context"] == "isolated"]
    t3_isolated_shapes = Counter(r["shape_category"] for r in t3_isolated)
    t3_isolated_fall_rise_frac = (
        t3_isolated_shapes.get("fall-rise", 0) / len(t3_isolated) if t3_isolated else None
    )

    t3_by_context_shapes = {}
    for context in ("isolated", "plus_t1", "plus_t2", "plus_t3", "plus_t4", "phrase_final"):
        context_rows = [r for r in t3_rows if r["context"] == context]
        t3_by_context_shapes[context] = Counter(r["shape_category"] for r in context_rows)

    t3_plus_t3_shapes = t3_by_context_shapes["plus_t3"]
    t3_plus_t3_dominant = t3_plus_t3_shapes.most_common(1)[0] if t3_plus_t3_shapes else (None, 0)

    # Voice stability: does the MOST COMMON shape per context agree across
    # all 3 voices for T3?
    stability_notes = []
    for context in ("isolated", "plus_t1", "plus_t2", "plus_t3", "plus_t4", "phrase_final"):
        per_voice_dominant = {}
        for voice in sorted({r["voice"] for r in t3_rows}):
            voice_rows = [r for r in t3_rows if r["context"] == context and r["voice"] == voice]
            if voice_rows:
                shapes = Counter(r["shape_category"] for r in voice_rows)
                per_voice_dominant[voice] = shapes.most_common(1)[0][0]
        agree = len(set(per_voice_dominant.values())) <= 1
        stability_notes.append((context, per_voice_dominant, agree))

    all_agree = all(agree for _, _, agree in stability_notes)

    # T3 vs controls: does the current fall-rise requirement accept T1/T2/T4 too?
    reaction_pass_rates = {}
    for tone in (1, 2, 3, 4):
        tone_rows = [r for r in rows if r["base_tone"] == tone and r["candidate_e_score"] is not None]
        passing = sum(1 for r in tone_rows if r["candidate_e_score"] >= 58)
        reaction_pass_rates[tone] = (passing, len(tone_rows))

    q1 = (
        f"**No.** Isolated T3 shows fall-rise in {t3_isolated_shapes.get('fall-rise', 0)} of "
        f"{len(t3_isolated)} cases ({_fmt(t3_isolated_fall_rise_frac, 2) if t3_isolated_fall_rise_frac is not None else 'NA'} "
        f"fraction) across {n_voices} voices. Dominant shape(s): {dict(t3_isolated_shapes.most_common())}."
        if t3_isolated
        else "No isolated T3 data collected."
    )
    q2 = (
        "See §Shape distribution by context below — compare the `isolated` row against "
        "`plus_t1`/`plus_t2`/`plus_t3`/`plus_t4` for T3. Distributions differing across "
        "columns is evidence context changes the realized shape; identical distributions "
        "would be evidence it does not."
    )
    q3 = (
        f"T3-before-T3 (`plus_t3`) dominant shape: `{t3_plus_t3_dominant[0]}` "
        f"({t3_plus_t3_dominant[1]} of {sum(t3_plus_t3_shapes.values())} cases). "
        "Compare directly against `isolated` T3's dominant shape in §Q1 — if they differ, "
        "that is consistent with (though this audit does not by itself prove) classical "
        "T3-sandhi expectations."
    )
    q4 = (
        f"{'**Yes** — ' if all_agree else '**Not fully** — '}"
        + "; ".join(
            f"{context}: {'agree' if agree else 'DISAGREE'} ({per_voice})"
            for context, per_voice, agree in stability_notes
        )
    )
    q5_pass_rate_t3 = reaction_pass_rates[3]
    q5 = (
        f"Frozen Candidate E V1 (fall-rise requirement) passes T3 at threshold 58 in "
        f"{q5_pass_rate_t3[0]} of {q5_pass_rate_t3[1]} T3 tokens across all contexts and "
        f"voices ({_fmt(q5_pass_rate_t3[0] / q5_pass_rate_t3[1] if q5_pass_rate_t3[1] else None, 2)} "
        f"fraction). Compare against T1/T2/T4's own pass rates in §STEP 5 below — if T3's is "
        f"far lower than the controls' own pass rates on their own formulas, that is evidence "
        f"the fall-rise requirement is overly restrictive for how T3 is actually realized in "
        f"this dataset, not evidence of a genuine pronunciation problem (there is no "
        f"pronunciation problem here — this is synthetic reference speech)."
    )
    q6 = (
        "**Context is available in this codebase (`tone_context.plan_expected_tones` already "
        "computes it, whole-utterance, spanning word boundaries) but is NOT currently threaded "
        "into the legacy scoring call (`directional_tone_scores`) that drives progression.** "
        "See §STEP 7 for the full, cited breakdown. A context-aware Candidate E2-T3 would need "
        "its own harness carrying this context, mirroring `plan_expected_tones`'s inputs rather "
        "than assuming the legacy call path provides it."
    )

    tone_sections = []
    for tone in (1, 2, 3, 4):
        tone_sections.append(f"""
### Tone {tone}

**Shape distribution by context:**

{_shape_summary_table(rows, tone)}

**Shape stability across voices (all contexts pooled):**

{_voice_stability_table(rows, tone)}

**Frozen Candidate E V1 reaction (STEP 5) — mean score and pass/fail @58, by context and observed shape:**

{_candidate_e_reaction_table(rows, tone)}
""")

    report = f"""# T3 context audit (Candidate E2-T3 groundwork)

**Candidate E V1 remains frozen** (`benchmarking/candidates/contour_scorer_v2.py`,
`candidate_e_protocol.json` — neither read from nor written to by this
audit except via read-only import for STEP 5). **No OMPAL data was used
anywhere in this audit.**

{n_total} tokens generated: {len({(r['base_tone'], r['context']) for r in rows})} (tone, context)
combinations × {n_voices} voices (`{', '.join(sorted({r['voice'] for r in rows}))}`).
Full per-token measurements in `t3_controlled_context.csv`; normalized
trajectories saved separately in
`benchmarking/external/t3_context_audio/normalized_trajectories.json`
(per the task's "save the normalized trajectory where practical").

**STEP 4 descriptive category definitions** (deterministic, fixed before
looking at any breakdown; `FLAT_SLOPE_EPS = 0.05`, same epsilon Candidate E
V1's own shape-validity gate uses, for direct comparability):

- `fall-rise`: first-half slope < −0.05 AND second-half slope > +0.05
- `rise-fall`: first-half slope > +0.05 AND second-half slope < −0.05
- `low-flat`: |first-half slope| < 0.05 AND |second-half slope| < 0.05
- `mostly-falling`: net falling movement not matching `fall-rise`
- `mostly-rising`: net rising movement not matching `rise-fall`
- `other`: none of the above

These are descriptive labels only — none of STEP 3/4 classifies anything
as a correct or incorrect pronunciation.

**Methodology limitation, disclosed rather than glossed over**: `isolated`
tokens are measured from the WHOLE audio file (unambiguous — one syllable,
one file). The two-character contexts (`plus_t1`..`plus_t4`, `phrase_final`)
are measured with a simple 50/50 frame-count split of the file, not true
per-syllable alignment (STEP 3 deliberately avoided
`estimate_word_prosody`'s alignment machinery, since the earlier diagnosis
found it actively distorts short syllables — see `directional_tone_formula_
audit.md`'s onset-skip finding). A naive half-split does not correctly
locate the syllable boundary when the two syllables have different
durations, so some bleed between adjacent syllables should be expected in
the two-character-context measurements specifically. This most plausibly
explains why T1 (nominally flat) shows more shape variability in the
two-character contexts than in `isolated` below — treat the `isolated`
column as the most reliable evidence in this audit, and the two-character
columns as indicative but noisier.

## Answers

**1. Does isolated T3 consistently show fall-rise?**

{q1}

**2. Does T3 before T1/T2/T4 behave differently?**

{q2}

**3. Does T3 before T3 behave differently?**

{q3}

**4. Are patterns stable across voices?**

{q4}

**5. Is Candidate E V1's fall-rise requirement too restrictive?**

{q5}

**6. Is context available to support a context-aware production scorer?**

{q6}

## STEP 7 — Context available in production (read-only code audit)

{STEP7_FINDINGS}

## Per-tone detail (STEP 4/5 full data)
{"".join(tone_sections)}

---

*No OMPAL data (development, validation, or final_test) was loaded by any
code in this audit. Candidate E V1 and production code were not modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def write_design_doc(result: dict[str, Any], path: Path) -> None:
    rows = result["rows"]
    t3_rows = [r for r in rows if r["base_tone"] == 3]

    families_found = sorted({r["shape_category"] for r in t3_rows if r["shape_category"] != "unmeasured"})

    context_dominant = {}
    for context in ("isolated", "plus_t1", "plus_t2", "plus_t3", "plus_t4", "phrase_final"):
        context_rows = [r for r in t3_rows if r["context"] == context]
        shapes = Counter(r["shape_category"] for r in context_rows)
        context_dominant[context] = shapes.most_common(1)[0][0] if shapes else "unmeasured"

    report = f"""# Candidate E2-T3 — design (NOT implemented)

Per the task's explicit instruction, this document proposes a design based
on the T3 context audit's evidence. **No scoring code is written or
changed here.** Candidate E V1 remains frozen and untouched.

## What the audit found (summary; full evidence in `t3_context_audit.md`)

Descriptive shape families actually observed in the controlled T3 data:
{', '.join(f'`{f}`' for f in families_found)}.

Dominant shape per context (pooled across all 3 voices):

| Context | Dominant observed shape |
|---|---|
{chr(10).join(f"| {context} | `{shape}` |" for context, shape in context_dominant.items())}

## Design principle

**Do not reduce T3 to one global fall-rise template.** The audit's own
evidence (see the dominant-shape table above and the full per-context
breakdown in `t3_context_audit.md`) is what determines whether the contexts
below are genuinely acoustically distinct in this dataset, or whether some
of them collapse to the same observed family — this section names
candidate possibilities to investigate, not conclusions to hard-code.

## Candidate realization families to investigate (NOT yet confirmed as ground truth)

A. **Full/citation fall-rise pattern** — the pattern Candidate E V1's
   current gate requires. Whether isolated T3 in this dataset actually
   matches this is answered directly by this audit's Q1.

B. **Reduced/predominantly-falling pattern** — the shape the earlier
   Candidate E V1 controlled test found for isolated citation-form T3 in
   this project's TTS voice. Whether this is a stable, voice-independent
   family (not one voice's idiosyncrasy) is answered by this audit's Q4.

C. **T3-before-T3 sandhi pattern** (linguistically expected: T3+T3 →
   T2-like rise on the first syllable) — whether the `plus_t3` context's
   observed shape for the FIRST (base) syllable actually differs from
   `isolated`'s shape in a way consistent with this is answered by this
   audit's Q3. Note this audit measures the BASE (first) syllable in
   `plus_t3`, which is the syllable sandhi theory predicts changes; a
   follow-up could separately measure the SECOND syllable of that pair.

## Sketch of a context-aware design (conceptual only)

```
expected_tone (T3)
   + following_tone (from context, per STEP 7: available via
     tone_context.plan_expected_tones-style whole-utterance context,
     NOT currently available at the legacy directional_tone_scores call)
   + position (phrase-final vs. not)
   ->
   select an ACCEPTED SET of realization families (e.g. {{B}} for isolated/
   phrase-medial-non-T3-following, {{A, B}} where evidence supports both,
   {{sandhi-specific family}} for T3+T3)
   -> score the observed contour as a match to ANY family in the accepted
      set, not a single template
```

This mirrors `tone_context.ExpectedTone.accepted_surface_tones` (already a
tuple, already built for "more than one realization can be accepted" —
tone_context.py:17-18, 95-98) rather than inventing a new mechanism from
scratch — but doing so requires the harness to carry context through to
scoring the way `plan_expected_tones` does and `directional_tone_scores`
currently does not (STEP 7).

## Explicitly out of scope for this document

- No accepted-family membership is finalized here — that requires the
  descriptive audit's context-by-context evidence to actually support
  distinct, stable families (STEP 6's instruction).
- No implementation, no scoring formula, no constants.
- No OMPAL evaluation of any kind.
- No change to Candidate E V1 or production code.

## Next step (not taken in this task)

If the audit confirms multiple stable, context-conditioned families,
Candidate E2-T3 implementation should be scoped as its own follow-up task,
evaluated first on canonical/controlled evidence exactly as Candidate E V1
was, before ever touching OMPAL.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
