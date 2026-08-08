# Phase C2 — task / label / signal diagnostic

**Protocol amendment.** Phase C returned near-chance Dev performance across all
three systems. Before reformulating anything, this stage asks whether the
target label is wrong for the task, or the signal is absent from the
representations, or the model formulation cannot express the decision.

Test was not opened. Train and Dev only.

## 1. What the OMPAL label actually is

Provenance chain, traced through the code rather than assumed:

```
non-native_scores-detail.json
  └─ words[i].tone          ← the ONLY field used
       ["1","1","0"]  three raters, strings
  └─ majority (>=2 of 3)    prepare_ompal_benchmark.py:198,228
  └─ majority_tone_correct
  └─ manifest tone_correctness  → Correct / Incorrect
```

The sibling fields `phoneme_consonant` and `phoneme_vowel` exist in the same
record and are **not** used. So the label is a rater's judgement of the *tone*
specifically, not of overall pronunciation.

The corpus documentation records one contamination path: if a learner omits a
word or substitutes a filler, the annotators mark consonant, vowel **and** tone
incorrect together. Measured across the 2,068 learner tokens:

| tone | consonant | vowel | n |
|---|---|---|---|
| 1 | 1 | 1 | 1684 |
| 1 | 1 | 0 | 16 |
| 1 | 0 | 1 | 15 |
| 1 | 0 | 0 | 2 |
| **0** | **1** | **1** | **328** |
| 0 | 1 | 0 | 4 |
| 0 | 0 | 1 | 4 |
| 0 | 0 | 0 | 15 |

Of 351 Incorrect tokens, **328 (93.4%) are isolated tone errors** — the rater
judged the consonant and vowel correct and only the tone wrong. 15 (4.3%) have
all three marked wrong, consistent with the documented omission rule. 23 (6.6%)
carry any segmental co-error.

**Is the current binary label a tone-correctness label? YES**, with a small,
quantified contamination of about 4–7%.

This rules out the most attractive explanation for the weak result. The label
is not a broad "overall pronunciation" judgement, and it is well aligned with
the intended deployment decision (tone feedback). The failure is elsewhere.

## 2. What each system actually receives

**MODEL_A — wav2vec2.** `TencentGameMate/chinese-wav2vec2-base`, Mandarin
self-supervised pretraining on adult native speech, final hidden layer (12),
mean or temporal-3 pooling, 768 or 2304 dims, frozen, plus a 4-dim one-hot
expected tone.

**MODEL_B — Praat**, all ten features, per-syllable semitone normalisation
against the token's own median F0:

| group | features |
|---|---|
| F0 / tone shape | rel_f0_start, rel_f0_25, rel_f0_50, rel_f0_75, rel_f0_end, f0_range_st, slope_start_to_mid, slope_mid_to_end |
| duration | duration_seconds |
| voicing | voiced_proportion |
| intensity | *(none)* |
| segment/audio quality | *(none)* |

**MODEL_C** — concatenation of the two.

What they can theoretically detect: MODEL_B can represent tone contour shape,
duration and voicing, and nothing else — it has no access to segmental
identity, consonant quality, or spectral detail. MODEL_A could in principle
represent phonetic and coarticulatory detail, but wav2vec2 features are known
to be weakly tonal, and the encoder was pretrained on native adult speech, not
learner speech. Neither representation can detect comprehensibility or
prosodic context beyond the token.

Since 93% of the targets are isolated tone errors, MODEL_B's feature set is in
principle *well matched* to the label. A task–signal mismatch of the kind
"label is segmental but features are pitch" is therefore **not** the
explanation.

## 3. Score distributions — is there any continuous signal?

MODEL_B, refit exactly as frozen:

| | Correct median | Incorrect median | Cohen's d | distribution overlap | AUC |
|---|---|---|---|---|---|
| Train | 0.1657 | 0.1686 | 0.349 | 0.852 | 0.565 |
| Dev | 0.1634 | 0.1678 | 0.252 | 0.743 | 0.548 |

There is a real but small effect: d ≈ 0.25–0.35, in the same direction on both
Train and Dev. The distributions overlap by 74–85%.

**Threshold engineering cannot fix this.** The classes are not separated at any
cut point; a threshold only trades one error type for the other along a nearly
flat ROC curve. This confirms the Phase C threshold table rather than adding to
it.

## 4. Within-tone separability — the decisive finding

Evaluating the same frozen MODEL_B scores separately inside each expected tone
(Dev):

| tone | n | Incorrect | ROC-AUC | PR-AUC | Cohen's d |
|---|---|---|---|---|---|
| T1 | 82 | 11 | **0.355** | 0.115 | −0.253 |
| T2 | 74 | 10 | **0.355** | 0.115 | −0.424 |
| T3 | 40 | 10 | 0.540 | 0.287 | −0.004 |
| T4 | 126 | 24 | **0.687** | 0.382 | +0.604 |

(T1 and T2 are 0.3547 and 0.3547 to four decimals — verified as coincidence,
not a bug: 0.3546734955 and 0.3546875000.)

The model is **inverted below chance on T1 and T2**, useless on T3, and
moderately informative on T4. The pooled Dev AUC of 0.548 is a mixture of these
opposing behaviours, and materially overstates what the model does on any
single tone.

This identifies a concrete defect in the current formulation. Expected tone is
encoded **additively** as a one-hot vector into a linear model, which can shift
the intercept per tone but **cannot change the sign or magnitude of any feature
weight per tone**. Tone correctness inherently requires exactly that: a falling
contour is evidence of *correctness* for T4 and evidence of *error* for T2. One
shared weight vector must average those opposite requirements, and it does —
landing near chance overall while being actively wrong on the tones whose
direction it lost.

Formulation option B (acoustic + additive tone encoding) is therefore not
merely suboptimal; it is structurally unable to express the target decision
with a linear classifier.

## 5. Which Praat features carry stable signal

Univariate AUC on Train, then whether the direction replicates on Dev.
Replication requires the same direction and |Dev AUC − 0.5| ≥ 0.03.

| feature | Train AUC | Dev AUC | replicates |
|---|---|---|---|
| rel_f0_start | 0.462 | 0.448 | yes |
| rel_f0_25 | 0.457 | 0.423 | yes |
| rel_f0_50 | 0.463 | 0.468 | yes |
| **rel_f0_75** | 0.543 | **0.573** | yes |
| **rel_f0_end** | 0.542 | **0.572** | yes |
| f0_range_st | 0.546 | 0.423 | **no — sign flip** |
| slope_start_to_mid | 0.518 | 0.559 | yes |
| **slope_mid_to_end** | 0.539 | **0.582** | yes |
| duration_seconds | 0.502 | 0.487 | no |
| voiced_proportion | 0.519 | 0.509 | no |

Seven of ten replicate in direction. The strongest and most consistent are all
**late-contour** measures — `rel_f0_75`, `rel_f0_end`, `slope_mid_to_end` —
which is phonetically coherent: the second half of the syllable is where a
Mandarin tone contour is most distinctive, and where learner errors are most
audible. `f0_range_st` flips sign between Train and Dev and should not be
trusted.

So there is stable, interpretable acoustic signal. It is individually weak
(AUC 0.57–0.58) but it is real and it points at the right part of the syllable.

## 6. wav2vec2 layer diagnostic

Small pre-specified probe — early / middle / final, mean-pooled, same
classifier, Dev only. Not a sweep.

| layer | Dev PR-AUC | Dev ROC-AUC |
|---|---|---|
| early (L1) | 0.167 | 0.501 |
| middle (L6) | 0.225 | 0.487 |
| final (L12) | 0.183 | 0.488 |

Every layer sits at chance on ROC-AUC. The middle layer's slightly higher
PR-AUC comes with a *below*-chance ROC, so it is not evidence of recovered
signal. **Changing layer does not rescue the wav2vec2 representation**, and the
hypothesis that the final layer discards pitch information which an earlier
layer retains is not supported.

This is consistent with the checkpoint's provenance: self-supervised on adult
native Mandarin, with no objective that would force tonal information to
survive into a pooled utterance-level vector.

## 7. Task–signal assessment

| hypothesis | verdict |
|---|---|
| The label is a broad pronunciation judgement, not tone | **rejected** — 93.4% isolated tone errors |
| Praat features (pitch) are mismatched to a segmental label | **rejected** — label is tonal, features are tonal |
| There is no signal at all | **rejected** — 7/10 features replicate; d ≈ 0.25–0.35 |
| wav2vec2 layer choice discards the signal | **rejected** — all layers at chance |
| The formulation cannot express tone-conditional rules | **supported** — T1/T2 inverted, T4 informative |
| Signal is present but too weak for the available data | **supported** — best within-tone ROC 0.687 on 126 tokens |

## 8. What OMPAL can and cannot validate

**A. Alignment/extraction — PARTIAL.** Blinded human review put usable
original-boundary segments at 81/100. Good enough to build on, not good enough
to attribute residual error confidently.

**B. Overall pronunciation acceptability — NO.** The benchmark uses only the
`tone` field. The corpus does contain `phoneme_consonant` and `phoneme_vowel`,
so a *different* benchmark could be built for this — but the current one cannot
answer it, and segmental error rates are very low (~1.6% of tokens), which
would make that benchmark severely imbalanced.

**C. Tone correctness — YES, with caveats.** This is exactly what the label
records, from three raters, with 93% of positives being isolated tone errors.
The caveats are size (351 Incorrect, 45 speakers), no neutral tone at all, and
the 81% segment usability.

**D. Tone-confusion diagnosis (T3→T2 etc.) — NO.** OMPAL never records which
tone was produced. This is a hard limit of the corpus as published, not a
processing gap, and no amount of modelling recovers it.

## 9. Formulation assessment

**Formulation A — overall acceptability.** Not supported by the current label,
and poorly supported by the corpus (segmental errors too rare).

**Formulation B — tone correctness given expected tone.** *This is already the
task*, and the label supports it well. What failed is the *implementation* of
"given expected tone": additive one-hot encoding into a shared linear model.
The finding in §4 says the conditioning must be structural — tone-conditional
weights (interaction terms, or one model per tone) — not additive.

**Formulation C — two-stage: usability gate, then tone judgement.** Attractive
in principle and matches the deployment workflow, but Phase C2's predecessor
already showed no automatic QC rule reaches usable precision, so stage 1 cannot
currently be built.

## 10. Minimal fresh human-validation design (designed, not collected)

Whether the next best evidence is a small fresh labelled set rather than more
OMPAL optimisation: **yes, eventually — but not yet.** The current blocker is
technical and testable on data already in hand, and fresh collection cannot fix
a formulation that cannot express the decision.

Design, ready to run once a model clears Dev:

- 20–30 learner speakers, 10–20 target items each (400–600 tokens)
- recorded through the actual app workflow, not read from a corpus
- **2 independent Mandarin raters**, blind to system output and to each other
- labels matching the deployment decision: tone acceptable/incorrect; overall
  pronunciation acceptable/incorrect; comprehensibility if feasible
- estimate human–human agreement **first** — it is the ceiling
- then system–human agreement, sensitivity, specificity, false rejection rate,
  false acceptance rate

Critically, this design should also record **which tone the rater heard**,
which OMPAL lacks. That single addition would make tone-confusion diagnosis
possible and would let the system give actionable feedback ("you said second
tone; the target is third") rather than a bare right/wrong.

## 11. Decision

The label is right, the feature family is right, weak but replicating signal
exists, and the model formulation demonstrably cannot express the required
tone-conditional decision. The failure is technical, not a label or target
problem.

**Primary next action: D — technical/model failure requires a new acoustic
front-end and formulation.**

Specifically, and in this order:

1. Tone-conditional modelling (interaction terms or per-tone models), since the
   current additive encoding is provably unable to represent the decision.
2. A tone-appropriate front-end: the late-contour features carry the signal, so
   a representation preserving the F0 trajectory shape is the natural direction,
   rather than a pooled self-supervised vector that is at chance at every layer.
3. Only after Dev shows genuine discrimination, spend the sealed Test.

Secondary, and required before any deployment claim regardless of benchmark
outcome: **C** — fresh human-labelled learner data, with produced-tone recorded.

Do **not** open Test to confirm a near-chance model.
