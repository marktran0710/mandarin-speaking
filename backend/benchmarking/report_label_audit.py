"""Renders `label_audit.run()`'s result dict into
`benchmarking/results/ompal_label_methodological_audit.md`.

The interpretation rule (§ INTERPRETATION) is fixed here, in code, before
`label_audit.run()` is ever executed against real data -- same discipline as
`SUBSTANTIAL_AUC_BAR` in the Candidate B1/C1 reports, reused verbatim so this
audit is held to the same bar the candidates themselves were.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

REPORT_PATH = Path("benchmarking/results/ompal_label_methodological_audit.md")

#: Same bar Candidate B1/C1 were judged against.
SUBSTANTIAL_AUC_BAR = 0.65
#: An AUC jump smaller than this on a subset of this corpus's size is not
#: distinguishable from sampling noise; only a jump at or above this is
#: treated as evidence the clean subset behaves differently.
MEANINGFUL_DELTA = 0.05
#: Below this N, a subset's AUC is too noisy to anchor a conclusion on.
MIN_RELIABLE_N = 30


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _metrics_row(label: str, metrics: dict[str, Any]) -> str:
    return (
        f"| {label} | {metrics.get('n', 'NA')} | {_fmt(metrics.get('auc'))} | "
        f"{_fmt(metrics.get('balanced_accuracy'))} | {_fmt(metrics.get('matthews_correlation'), 4)} |"
    )


def _abc_table(entries: dict[str, dict[str, Any]]) -> str:
    header = "| Subset | N | Baseline A AUC | B1 AUC | C1 AUC |\n|---|---|---|---|---|\n"
    body = []
    for label, e in entries.items():
        body.append(
            f"| {label} | {e.get('n', e.get('baseline_a', {}).get('n', 'NA'))} | "
            f"{_fmt(e.get('baseline_a', {}).get('auc'))} | "
            f"{_fmt(e.get('candidate_b1', {}).get('auc'))} | "
            f"{_fmt(e.get('candidate_c1', {}).get('auc'))} |"
        )
    return header + "\n".join(body)


def _c1_by_tone_table(by_tone: dict[str, dict[str, Any]]) -> str:
    header = "| Tone | N | AUC | Balanced accuracy | MCC |\n|---|---|---|---|---|\n"
    body = [
        f"| T{tone} | {m.get('n', 0)} | {_fmt(m.get('auc'))} | "
        f"{_fmt(m.get('balanced_accuracy'))} | {_fmt(m.get('matthews_correlation'), 4)} |"
        for tone, m in by_tone.items()
    ]
    return header + "\n".join(body)


def write_report(result: dict[str, Any], path: Path = REPORT_PATH) -> None:
    q2, q3, q6, q7, q8 = result["q2"], result["q3"], result["q6"], result["q7"], result["q8"]

    # ---- Interpretation rule, applied to Candidate C1 (the best performer) ----
    all_auc = q2["all"]["candidate_c1"].get("auc")
    hc_auc = q8.get("candidate_c1", {}).get("auc")
    hc_n = q8.get("n", 0)
    delta = (hc_auc - all_auc) if (all_auc is not None and hc_auc is not None) else None

    if hc_n < MIN_RELIABLE_N:
        interpretation_number = 4
        interpretation_title = "INDETERMINATE"
        interpretation_text = (
            f"HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET has only N={hc_n} validation rows -- "
            f"below the {MIN_RELIABLE_N}-row reliability floor fixed in this report's "
            "code before the subset was ever evaluated. Any AUC computed on a sample "
            "this small is not distinguishable from noise, so this audit cannot "
            "responsibly choose between label mismatch and representation "
            "limitation from this evidence alone."
        )
    elif hc_auc is not None and hc_auc >= SUBSTANTIAL_AUC_BAR and delta is not None and delta >= MEANINGFUL_DELTA:
        interpretation_number = 1
        interpretation_title = "LABEL / UNIT MISMATCH"
        interpretation_text = (
            f"Candidate C1's AUC on HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET ({_fmt(hc_auc)}) "
            f"clears the {SUBSTANTIAL_AUC_BAR:.2f} bar and improves on all-validation "
            f"AUC ({_fmt(all_auc)}) by {_fmt(delta)}, at or above the "
            f"{MEANINGFUL_DELTA:.2f} threshold fixed for a 'meaningful' jump. "
            "The weak overall validation numbers substantially reflect annotation "
            "granularity and/or context-tone mismatch, not a ceiling on what the "
            "acoustic representations can discriminate."
        )
    elif delta is not None and delta >= MEANINGFUL_DELTA and (hc_auc or 0) < SUBSTANTIAL_AUC_BAR:
        interpretation_number = 3
        interpretation_title = "BOTH"
        interpretation_text = (
            f"Candidate C1's AUC improves from {_fmt(all_auc)} (all validation) to "
            f"{_fmt(hc_auc)} (HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET), a jump of "
            f"{_fmt(delta)} -- at or above the {MEANINGFUL_DELTA:.2f} 'meaningful' "
            f"threshold -- but still short of the {SUBSTANTIAL_AUC_BAR:.2f} bar. "
            "Label/context noise is suppressing part of the measured "
            "discrimination, but even with that noise removed the representation "
            "and model are not yet strong enough."
        )
    else:
        interpretation_number = 2
        interpretation_title = "REPRESENTATION / MODEL LIMITATION"
        interpretation_text = (
            f"Candidate C1's AUC on HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET ({_fmt(hc_auc)}) "
            f"is not meaningfully higher than on all validation ({_fmt(all_auc)}) -- "
            f"a difference of {_fmt(delta)}, below the {MEANINGFUL_DELTA:.2f} "
            "threshold fixed for a 'meaningful' jump. Removing annotation-granularity "
            "and context-tone ambiguity does not rescue discrimination, which points "
            "at the acoustic representations and linear classifiers themselves as "
            "the limiting factor, not the labels."
        )

    report = f"""# OMPAL label / methodological audit

Answers to Q1-Q8. No model was retrained, tuned, or re-thresholded anywhere
in this document -- every number below reads Baseline A's frozen
`system_tone_correct`/`system_character_score` columns, Candidate B1's frozen
`candidate_b_validation_predictions.csv`, or Candidate C1's frozen
`candidate_c_validation_predictions.csv` as-is. **final_test is not
referenced anywhere in this audit.**

## Q1 — Exact unit of the human tone label

Established directly from the raw OMPAL JSON files
(`private-data/ompal/native_scores.json`, `non-native_scores.json`,
`non-native_scores-detail.json`) and from `benchmarking/ompal_corpus.py` /
`benchmarking/diagnostics.py` — not inferred.

**1. Attachment unit.** The raw corpus's `tone` field is attached to an
entry in each utterance's `words[]` array. Across the full corpus (82 native
+ 1,768 non-native utterances, 20,689 `words[]` entries total): **20,671
entries (99.91%) span exactly one Chinese character**; 18 entries (0.09%)
span two characters. There is no utterance-level tone field at all — only
`accuracy`/`fluency`/`prosody` are rated per whole utterance.

**2. Multi-character words: A or B?** Inspecting all 18 two-character
entries directly (e.g. utterance `00100218`, sentence "正月初一人們穿上新衣服":
one entry has `text: ["正", "人"]`, five characters apart in the sentence)
shows they are **not genuine contiguous lexical words** — they're a rare raw-
data artifact pairing two non-adjacent characters under one shared rating.
Every genuine multi-character word in the corpus (他們, 衣服, 新衣, ...) is
instead split into separate single-character `words[]` entries, each with
its own independent 3-rater tone judgement. So: OMPAL's real answer is
effectively **A — one label per syllable**, with 18 anomalous exceptions
(0.09% of the corpus) that are not true multisyllabic words at all.

**3. Does our pipeline duplicate a word-level label across syllable rows?**
`ompal_corpus.py`'s `_build_words` (lines 363-378) maps one raw `words[]`
entry to exactly one `OmpalWord`, with no duplication. But
`benchmarking/diagnostics.py`'s `extract_utterance_rows` computes
`human_correct`/`panel` **once per `OmpalWord`**, then loops
`for offset in range(len(word.text))` to emit one CSV row per character in
that word's span — so **if a raw entry's span is 2 characters, the same
`human_majority_tone_correct` value is written to both resulting rows.**
Given (2), this mechanism only ever fires on the 18 anomalous raw entries,
never on a genuine multi-syllable word (because none exist in the raw
data). `expected_tone`, by contrast, is *not* duplicated in this path — it
correctly indexes `word.expected_tones[offset]`, a separate citation-tone
lookup per character position.

**Concrete counts, current diagnostics table**: `word_character_count`
(`len(word.text)`, computed downstream) is **1 for all {result['n_rows']:,}
validation rows evaluated in this audit** — none of the 18 corpus-wide
anomalies survive the join/exclusion rules into the validation split this
audit and Candidates B1/C1 evaluate on. As far as this validation set is
concerned, **every `human_majority_tone_correct` label is genuinely
character-specific, not inherited from a larger word.**

### Q1 conclusion

**No evidence of label-unit mismatch in the current validation set.** OMPAL
tone labels are single-character level for 20,671/20,689 raw entries
(99.91%), and the validation set this audit and Candidates A/B1/C1 evaluate
on contains zero surviving multi-character annotation spans
(`word_character_count == 1` for all {result['n_rows']:,} rows). Label
duplication across syllables is therefore not a plausible explanation for
the candidates' weak validation performance.

**A separate, auxiliary question — not OMPAL annotation granularity.**
Whether a character's *Mandarin lexical word* (as a listener would parse the
sentence: 朋友, 學校, ...) is one or several characters long is unrelated to
how OMPAL rated it — OMPAL's own unit is already single-character regardless
of lexical word length. This audit still reports a lexical-word-length
breakdown (Q2/Q3, using `jieba.lcut`, the same segmenter
`ompal_corpus.py` already uses for a related purpose) because within-word
context could plausibly affect production or scoring even though it has
nothing to do with the label's granularity — but it is reported below as
**exploratory, auxiliary lexical-context analysis**, built from
`jieba`-reconstructed metadata rather than any original OMPAL annotation
field, and is **not** used to define the primary
`HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET` (Q8).

## Q4 — Provenance of `expected_tone`

**Full path**: Chinese character (from OMPAL's `words[].text`, itself split
to one character per rated unit per Q1) → `pypinyin.pinyin(char,
style=Style.TONE3, ...)` with `taiwan_pinyin.apply()` active (Taiwan-Mandarin
readings) → `chinese_tones.word_tones()` → `OmpalWord.expected_tones` →
`expected_tone` column in `human_vs_system_diagnostics.csv`
(`ompal_corpus.py:372`, `error_analysis.py:140-142`).

**This is a pure citation-form dictionary lookup, computed per isolated
character, with no sentence context and no tone sandhi applied anywhere in
this call path** (`ompal_corpus.py` never calls any sandhi function — grep
confirms zero matches for "sandhi" in that file). The raw OMPAL files
themselves carry no pinyin or tone-value field at all (only the 0/1
correctness verdict, Q1) — the tone target is entirely re-derived by our own
code, never read from the corpus.

**This differs from what the live production scorer targets internally.**
`praat_analyzer.py`'s `estimate_word_prosody` makes an *independent*
`word_tones()` call per jieba token, then applies
`chinese_tones.apply_tone_sandhi` (T3+T3 → T2+T3 only) to that result before
scoring (`praat_analyzer.py:1038-1039`) — so the value the frozen scorer
actually targets for `system_tone_correct`/`system_character_score` *is*
partially sandhi-adjusted, but only within a single jieba token, never
across token boundaries (documented directly in a code comment at
`praat_analyzer.py:981-986`: "很好 is two jieba tokens, so the per-token
`apply_tone_sandhi` ... never sees the T3+T3 pair"). A third, more complete
sandhi module (`tone_context.py`, full T3/一/不/neutral rules, spanning jieba
token boundaries) exists but is wired only into a diagnostic-only
`diagnostic_status` field — it does not touch `expected_tone`, the pass/fail
score, or progression.

**Net effect**: the `expected_tone` this audit and Candidates A/B1/C1 were
all evaluated against is the *least* context-aware of the three tone values
that exist in this codebase for the same character. Whether that gap
actually degrades measured discrimination is exactly Q5/Q6, next.

## Q5 — Tone sandhi / context audit

Flags computed by calling `tone_context.plan_expected_tones` — the existing,
already-tested production sandhi-planning function — read-only, over each
validation utterance's full Han-character sequence (reconstructed from
`benchmarking.ompal_corpus.load_utterances`, not from the diagnostics CSV's
possibly-gapped rows, so a syllable excluded from scoring doesn't distort
the sandhi context of its neighbors). No expected tone was rewritten
anywhere — this only labels each row's `sandhi_status` in
`ompal_sandhi_audit.csv` ({result['n_sandhi_written']:,} rows, the full
validation set).

| sandhi_status | Rule source | N |
|---|---|---|
| stable | no rule fired | {result['sandhi_counts'].get('stable', 0):,} |
| T3_sandhi_candidate | `RULE_T3_T3` / `RULE_T3_CHAIN` | {result['sandhi_counts'].get('T3_sandhi_candidate', 0):,} |
| yi_sandhi_candidate | `RULE_YI` (一) | {result['sandhi_counts'].get('yi_sandhi_candidate', 0):,} |
| bu_sandhi_candidate | `RULE_BU` (不) | {result['sandhi_counts'].get('bu_sandhi_candidate', 0):,} |
| neutral_or_other | `RULE_NEUTRAL_LEXICAL` / `RULE_NEUTRAL_OPTIONAL` | {result['sandhi_counts'].get('neutral_or_other', 0):,} |
| unknown | plan computation failed or utterance unresolved | {result['sandhi_counts'].get('unknown', 0):,} |

Unresolved audio IDs (utterance not found via `load_utterances`, so no plan
could be computed): {len(result['unresolved_audio_ids'])}
{"(" + ", ".join(result['unresolved_audio_ids'][:10]) + (", ..." if len(result['unresolved_audio_ids']) > 10 else "") + ")" if result['unresolved_audio_ids'] else ""}

Note: as established in Q1, neutral tone (`expected_tone == 5`) is already
excluded from `human_vs_system_diagnostics.csv` by the corpus's existing
exclusion rules — the `neutral_or_other` count above therefore reflects
*neighboring* characters whose own tone is non-neutral but which sit next to
a neutral-tone syllable (affecting the sandhi plan's neutral-tone pass), not
surviving neutral-tone rows themselves.

## Q2 — Monosyllabic-only analysis (AUXILIARY — exploratory lexical-context analysis)

**Not an OMPAL-annotation-granularity question** — see the Q1 conclusion
above. "Monosyllabic" here means the character's `jieba`-segmented lexical
word is one character long; `jieba` segmentation is reconstructed metadata,
not an original OMPAL field, so this section is exploratory context, not a
label-quality finding. Existing predictions only; no retraining.

{_abc_table({"All validation": q2['all'], "Monosyllabic (lexical) only": q2['monosyllabic']})}

Human-correct rate: all validation = {_fmt(q2['all']['human_correct_rate'])},
monosyllabic-only = {_fmt(q2['monosyllabic']['human_correct_rate'])}.

### Candidate C1, monosyllabic-only, per tone

{_c1_by_tone_table(q2['monosyllabic_c1_by_tone'])}

## Q3 — Monosyllabic / 2-syllable / 3+-syllable breakdown (AUXILIARY — exploratory lexical-context analysis)

**Not an OMPAL-annotation-granularity question** — see the Q1 conclusion.
"Syllable" here means lexical (`jieba`-reconstructed) word length, reported
purely as exploratory within-word context, independent of label quality.
Existing predictions only; no retraining.

{_abc_table({
        "Monosyllabic (1 char)": q3['monosyllabic'],
        "2-syllable word": q3['two_syllable'],
        "3+-syllable word": q3['three_plus_syllable'],
    })}

Human-correct rate by group: monosyllabic = {_fmt(q3['monosyllabic']['human_correct_rate'])},
2-syllable = {_fmt(q3['two_syllable']['human_correct_rate'])},
3+-syllable = {_fmt(q3['three_plus_syllable']['human_correct_rate'])}.

## Q6 — Context-stable vs potential-sandhi subsets

Existing predictions only; no retraining.

{_abc_table({"All validation": q6['all'], "Context-stable only": q6['context_stable'], "Potential-sandhi only": q6['potential_sandhi']})}

### Candidate C1, context-stable subset, per tone

{_c1_by_tone_table(q6['context_stable_c1_by_tone'])}

## Q7 — Human agreement: all labels vs unanimous only

Existing predictions only; no retraining. Unanimous = all 3 raters gave the
same tone verdict (`individual_rater_labels` is "000" or "111").

| | N | B1 AUC | B1 balanced acc. | B1 MCC | C1 AUC | C1 balanced acc. | C1 MCC |
|---|---|---|---|---|---|---|---|
| All human labels | {q7['all']['b1'].get('n')} | {_fmt(q7['all']['b1'].get('auc'))} | {_fmt(q7['all']['b1'].get('balanced_accuracy'))} | {_fmt(q7['all']['b1'].get('matthews_correlation'), 4)} | {_fmt(q7['all']['c1'].get('auc'))} | {_fmt(q7['all']['c1'].get('balanced_accuracy'))} | {_fmt(q7['all']['c1'].get('matthews_correlation'), 4)} |
| Unanimous only | {q7['unanimous']['b1'].get('n')} | {_fmt(q7['unanimous']['b1'].get('auc'))} | {_fmt(q7['unanimous']['b1'].get('balanced_accuracy'))} | {_fmt(q7['unanimous']['b1'].get('matthews_correlation'), 4)} | {_fmt(q7['unanimous']['c1'].get('auc'))} | {_fmt(q7['unanimous']['c1'].get('balanced_accuracy'))} | {_fmt(q7['unanimous']['c1'].get('matthews_correlation'), 4)} |

Baseline A's own unanimous-subset behavior was already reported in
`tone_diagnostic_summary.md` §"unanimous-subset" as essentially unchanged
from its all-labels AUC (0.519 vs 0.511) — the same comparison for B1/C1 is
the table above.

## Q8 — HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET

**Revised** after Q1 was resolved: label duplication is not plausible in
this validation set, so lexical (`jieba`) monosyllabic word is **not**
required for the primary clean subset — it stays a separate, auxiliary
analysis (Q2/Q3). Defined before looking at its performance: unanimous
human rating (Q7) AND valid single-character OMPAL annotation
(`word_character_count == 1` — Q1; true for every row in this validation
set today, kept as an explicit criterion so the definition doesn't silently
depend on that staying true) AND context-stable tone (Q5/Q6,
`sandhi_status == "stable"`) AND usable alignment (already guaranteed — this
audit only ever operates on B1/C1's own usable row set) AND non-neutral tone
(`expected_tone != "5"`, already guaranteed by the corpus's existing
exclusion rules, applied again here so the subset's definition is
self-contained).

Written to `ompal_high_confidence_subset.csv`
({result['n_high_confidence_written']:,} rows).

**N = {q8['n']:,}**. Label distribution: {dict(q8['label_distribution'])}.

| | N | Baseline A AUC | B1 AUC | C1 AUC |
|---|---|---|---|---|
| HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET | {q8['n']} | {_fmt(q8['baseline_a'].get('auc'))} | {_fmt(q8['candidate_b1'].get('auc'))} | {_fmt(q8['candidate_c1'].get('auc'))} |

### Candidate C1, HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET, per tone

{_c1_by_tone_table(q8['c1_by_tone'])}

**Caveat on this subset's reliability**: {q8['label_distribution'].get('0', 0)}
of {q8['n']} rows are the minority ("incorrect") class. AUC is computed from
ranking the minority class against the majority class, so its effective
sample size tracks the *smaller* count, not the total N — whether
{q8['label_distribution'].get('0', 0)} minority examples is enough to trust
the estimate precisely (rather than just indicatively) is independent of the
{MIN_RELIABLE_N}-row floor below (which checks total N, not per-class N).

## INTERPRETATION

Decision rule (fixed in `report_label_audit.py` before this run): compare
Candidate C1's (the strongest of the three methods) validation AUC on
HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET against its all-validation AUC.
- If the subset AUC clears {SUBSTANTIAL_AUC_BAR:.2f} **and** improves by at
  least {MEANINGFUL_DELTA:.2f} over all-validation: **LABEL / UNIT MISMATCH**.
- If it improves by at least {MEANINGFUL_DELTA:.2f} but still falls short of
  {SUBSTANTIAL_AUC_BAR:.2f}: **BOTH**.
- If the improvement is below {MEANINGFUL_DELTA:.2f}: **REPRESENTATION /
  MODEL LIMITATION**.
- If the subset has fewer than {MIN_RELIABLE_N} rows: **INDETERMINATE**,
  regardless of the numbers, because the estimate isn't trustworthy at that
  size.

All-validation Candidate C1 AUC: {_fmt(all_auc)}. HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET
Candidate C1 AUC: {_fmt(hc_auc)} (N={hc_n}). Difference: {_fmt(delta)}.

### Conclusion {interpretation_number}: {interpretation_title}

{interpretation_text}

---

*final_test remains locked. This audit contains no final_test numbers,
predictions, or references. No model was trained, tuned, or re-thresholded;
no production code (`praat_analyzer.py`, `chinese_tones.py`, `tone_context.py`,
threshold 58) was modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
