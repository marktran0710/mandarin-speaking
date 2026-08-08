# Phase C — Train/Dev model selection

Split `ompal_speaker_split_v1` · Train 1424 tokens / 32 speakers · Dev 322
tokens / 6 speakers · Incorrect prevalence 17.1% on Dev.

**Test was not touched.** Features were extracted for train and dev rows only,
so no Test prediction exists.

## Headline

All three systems perform near chance on unseen Dev speakers.

| system | best config | PR-AUC (Incorrect) | ROC-AUC | Bal. acc. | Incorrect F1 |
|---|---|---|---|---|---|
| MODEL_A wav2vec2 | mean, balanced, C=10 | 0.197 | 0.528 | 0.561 | 0.314 |
| MODEL_B Praat | —, None, C=0.01 | **0.221** | 0.548 | 0.591 | 0.330 |
| MODEL_C fusion | mean, None, C=10 | 0.195 | 0.517 | 0.562 | 0.317 |

Reference points: a random ranker gives ROC-AUC 0.500 and PR-AUC equal to the
prevalence, **0.171**. Balanced accuracy for a coin flip is 0.500.

So the best system beats the no-information PR-AUC floor by 0.05, and beats
chance ROC-AUC by 0.048. **This is not a working classifier.** Praat "wins"
the comparison, but it wins by being marginally less close to chance than the
others, which is not a result to build on.

Selected under the pre-specified rule (highest Dev PR-AUC): **MODEL_B Praat,
class_weight=None, C=0.01**.

## Why Accuracy must not be quoted

Predicting "Correct" for every token scores **82.9%** on Dev. Every
configuration in the grid is at or near that. Accuracy is reported in the
results CSV for completeness and is meaningless here.

## Deployment error rates at the frozen threshold

The pre-specified threshold rule (maximise Incorrect F1 on Dev) selects a
threshold at which the selected model produces:

| | value | meaning for a learner |
|---|---|---|
| false rejection rate | **0.401** | 2 in 5 correctly-pronounced tokens are marked wrong |
| false acceptance rate | **0.418** | 2 in 5 genuinely wrong tokens are passed |
| Incorrect precision | 0.221 | ~4 of 5 "wrong" verdicts are unjustified |
| Incorrect recall | 0.582 | |

Both error types are near coin-flip simultaneously. A learner using this would
be corrected on good speech about as often as on bad speech.

This is also an illustration of why the F1-maximising rule needs its error
rates reported next to it: with a near-chance ranker, Incorrect F1 is maximised
by flagging a large share of everything, which the rate table exposes and the
F1 number alone would hide.

## Threshold behaviour

| threshold | Inc P | Inc R | Inc F1 | FRR | FAR | Bal. acc. | % flagged |
|---|---|---|---|---|---|---|---|
| 0.10 | 0.171 | 1.000 | 0.292 | 1.000 | 0.000 | 0.500 | 100.0% |
| 0.15 | 0.175 | 0.927 | 0.294 | 0.903 | 0.073 | 0.512 | 90.7% |
| 0.20 | 0.167 | 0.036 | 0.060 | 0.037 | 0.964 | 0.499 | 3.7% |
| 0.30 | 0.500 | 0.036 | 0.068 | 0.007 | 0.964 | 0.514 | 1.2% |
| 0.50 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 0.500 | 0.0% |

The model's predicted probabilities span **0.124 to 0.493**. Nothing ever
crosses 0.5, so at the conventional threshold the system says "Correct" to
everything and its balanced accuracy is exactly 0.500. Between 0.15 and 0.20
the behaviour collapses from flagging 91% of tokens to flagging 4% — there is
no operating region where both error types are acceptable.

## Calibration

Brier score **0.140**. Mean predicted probability 0.169 against an observed
prevalence of 0.171, so the model is well calibrated *on average* — and that is
the trap. Average calibration is achieved by predicting the base rate for
everybody.

Reliability by quantile bin:

| mean predicted | observed |
|---|---|
| 0.147 | 0.122 |
| 0.155 | 0.275 |
| 0.159 | 0.125 |
| 0.162 | 0.025 |
| 0.166 | 0.125 |
| 0.169 | 0.200 |
| 0.173 | 0.250 |
| 0.216 | 0.244 |

Predictions span 0.147–0.216 across the bins while the observed rate jumps
between 0.025 and 0.275 with no monotone relationship. The confidence values
carry essentially no information, so they must not be shown to a learner.

## Uncertainty / abstention analysis

Median distance from the decision boundary is **0.006 for errors and 0.007 for
correct predictions** — indistinguishable. An abstention band cannot separate
them:

| margin | % of Dev inside the band | % of errors captured | accuracy outside the band |
|---|---|---|---|
| 0.05 | 97.5% | 95.4% | 0.25 |
| 0.10 | 98.8% | 98.5% | 0.50 |
| 0.20 | 98.8% | 98.5% | 0.50 |

To capture 95% of errors the system would have to abstain on 97.5% of items.
**Abstention cannot rescue this model.** The idea remains sound for a model
that discriminates; it is untestable on one that does not.

## Robustness by tone

| tone | n | Incorrect | balanced acc. | Incorrect recall | FRR |
|---|---|---|---|---|---|
| T1 | 82 | 11 | 0.449 | 0.364 | 0.465 |
| T2 | 74 | 10 | 0.402 | 0.100 | 0.297 |
| T3 | 40 | 10 | 0.617 | 0.900 | 0.667 |
| T4 | 126 | 24 | 0.703 | 0.750 | 0.343 |

T1 and T2 are **below chance**. T3 attains high recall only by flagging
two-thirds of correct tokens as well. With 10–24 Incorrect tokens per cell
these are unstable, but the pattern — no tone reliably handled — is consistent
with the overall result.

## Robustness by speaker

| speaker | n | Incorrect | balanced acc. | Incorrect recall | FRR |
|---|---|---|---|---|---|
| 02004 | 17 | 2 | 0.383 | 0.500 | 0.733 |
| 02014 | 17 | 3 | 0.821 | 1.000 | 0.357 |
| 02023 | 72 | 2 | 0.800 | 1.000 | 0.400 |
| 02027 | 72 | 16 | 0.576 | 0.563 | 0.411 |
| 02036 | 72 | 9 | 0.643 | 0.667 | 0.381 |
| 02040 | 72 | 23 | 0.576 | 0.478 | 0.327 |

Balanced accuracy ranges 0.383–0.821 across six speakers. The two apparently
good speakers (02014, 02023) have **2 and 3 Incorrect tokens** — their recall
of 1.000 rests on getting two or three items right and means very little. False
rejection sits between 33% and 73% for every speaker, including the good ones.

## Error analysis against existing descriptors

Descriptive only; nothing was removed on the basis of it.

| descriptor | median when prediction correct | median when error |
|---|---|---|
| duration_seconds | 0.181 | 0.160 |
| voiced_proportion | 0.705 | 1.000 |
| alignment_score | 0.918 | 0.920 |
| rms_relative_db | 0.95 | 2.59 |
| local_snr_db | 28.2 | 29.1 |

No descriptor separates errors from correct predictions in a way that would
support a filter, which is consistent with the earlier QC finding. Errors are
not concentrated in acoustically poor segments — they are spread across the
data, as expected when the model is not discriminating.

## Interpretation

The most likely reading is that **the frozen representations do not carry the
information needed to judge tone correctness for unseen speakers on this
corpus**. Consistent with that, the earlier tone-identification probe on
AISHELL reached only 53% on a 4-way task, and the Praat contour features
reached 45%.

Three specific constraints are visible and none is fixed by a different
classifier: median token duration is 0.171 s, giving very few frames to work
with; the 81/100 usability estimate means about a fifth of segments are
imperfect and unidentifiable; and 241 training Incorrect tokens is a very small
budget for a 768- or 2304-dimensional representation.

What this does **not** establish: that tone correctness is unlearnable, or that
a fine-tuned encoder would also fail. The frozen-encoder linear-probe design
was chosen to measure what the representation already carries, and it answers
that question — it does not answer what a trained model could carry.
