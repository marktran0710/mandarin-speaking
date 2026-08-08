# OMPAL tone-correctness benchmark — full audit

Dataset `ompal-tone-benchmark-1.0` · pipeline `align-mmsfa-star-0ms-1.0` · commit `743f0d0`

## Corpus flow

| stage | tokens |
|---|---|
| rated tokens (audited metadata) | 20671 |
| audio/annotation matched | 13261 |
| MoE pronunciation verified | 8759 |
| eligible for alignment | 2176 |
| alignment attempted | 2176 |
| alignment successful | 2176 |
| token segment extracted | 2176 |

Reconciles exactly at every step:

```
20671 - 7410 = 13261
13261 - 4502 = 8759
8759 - 6583 = 2176
```

## Eligibility gap audit — why 6,583 tokens were not eligible

The gap is one rule, not many. The aligner runs on a whole utterance,
and the frozen eligibility check requires **every rated token in that
utterance** to have a determined pronunciation. When one does not, the
entire utterance is skipped — and its other rated tokens go with it.

The exclusion counter only ever recorded the undetermined tokens
themselves (1,394), so the 5,189 tokens lost alongside them were
invisible in the flow. Nothing was wrong with those 5,189 tokens.

| Primary exclusion reason | N |
|---|---|
| utterance_dropped_sibling_token_undetermined | 5189 |
| token_pronunciation_segmentally_undetermined | 1394 |
| **TOTAL** | **6583** |

Utterance-level view:

| utterance outcome | utterances |
|---|---|
| dropped_undetermined_sibling | 825 |
| no_matching_audio | 656 |
| eligible | 369 |

### Hierarchical vs overlapping

Within this stage every token carries exactly one reason, so the
primary and raw-flag counts coincide:

```
raw_flag utterance_dropped_sibling_token_undetermined: 5189
raw_flag token_pronunciation_segmentally_undetermined: 1394
```

Across stages the reasons are hierarchical rather than overlapping: a
token with no matching audio is never tested for pronunciation
ambiguity, so it appears once, at the stage where it exits.

## Alignment result

**2176 / 2176 eligible tokens aligned successfully. Technical alignment success rate = 100%.**

This does **not** mean 100% boundary accuracy. It means the aligner
returned a span for every token it was asked to place. An independent
blinded human review put usable original-boundary segments at
**81/100 (blinded, original boundaries)** — roughly one token in five is expected to be
imperfect for tone analysis, and the manifest cannot say which. No QC
rule reached a usable precision/retention trade, so none is applied.

## Benchmark composition

- learner tokens: **2068** from **45** speakers and **349** utterances
- native reference tokens: 108
- correct **1717** / incorrect **351** (17.0% incorrect)
- distinct characters: 59, distinct syllable bases: 53

| expected tone | tokens | incorrect | % incorrect |
|---|---|---|---|
| T1 | 553 | 89 | 16.1% |
| T2 | 468 | 71 | 15.2% |
| T3 | 272 | 52 | 19.1% |
| T4 | 775 | 139 | 17.9% |

Tokens per learner speaker: min 17, median 72, max 72.
Correct rate by speaker: min 43%, median 85%, max 100%.

## Lexical / speaker confound audit

The earlier AISHELL benchmark failed here: a no-audio lexical lookup
beat every acoustic model. This benchmark is checked the same way.

| metadata-only baseline (speaker-disjoint) | accuracy | recall on incorrect |
|---|---|---|
| majority_class | 83.0% | 0.0% |
| expected_tone_only | 83.0% | 0.0% |
| character_only | 82.5% | 3.1% |
| syllable_only | 82.8% | 0.0% |

A speaker-only predictor is undefined under speaker-disjoint evaluation because the test speaker is unseen; it collapses to the majority class. The in-sample figure below is leaky and is an upper bound only.

Leaky in-sample speaker-only accuracy: 83.6% (upper bound, not a usable result).

- characters occurring only with Correct: 3 of 59
- characters occurring only with Incorrect: 0
- syllable bases with only one class: 1 of 53
- tokens in characters carrying both classes: 2000 (96.7%)

Every metadata-only baseline sits at or near the majority-class rate
with near-zero recall on the incorrect class — it predicts 'correct'
almost always and is blind to the errors the task exists to find. That
is the opposite of the AISHELL pattern. Stated carefully: this shows
the label is not trivially recoverable from metadata, not that no
confound exists.

## Validation

All assertions passed: flow counts, the `8759 = 6583 + 2176` invariant, manifest row count, duplicate ids, audio paths, labels, expected tones, timestamps, provenance and speaker ids.

## Frozen decisions and known limitations

- existing CTC forced aligner, unchanged
- original 0 ms boundaries, no padding
- no RMS, SNR, duration or alignment-score filtering
- no QC classifier
- unresolved audio/annotation id mismatches not remapped
- ambiguous polyphonic pronunciations not guessed

- Blinded human usability of original boundaries: 81/100 (blinded, original boundaries). Roughly one token in five is expected imperfect and the manifest cannot identify which.
- No neutral-tone tokens: every neutral-capable character is tone-ambiguous under MoE and was excluded.
- 5,189 MoE-verified tokens were lost as collateral of the whole-utterance eligibility rule, not because of anything wrong with those tokens.
- Acoustic descriptors are metadata; no QC rule was validated.
