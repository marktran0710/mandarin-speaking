# Phase C6 — time-normalised F0 trajectory representation

A representation experiment. Classifier, split, alignment, pitch settings and
labels are all frozen; only the description of the contour changes. Selection
ran inside Train; Dev was opened once, after freezing. Test untouched.

## 1. Trajectory extraction audit

20 points per token, semitones (12·log₂F0), time normalised across the **voiced
span** so the contour describes the tone rather than surrounding silence.
Interior gaps interpolated between voiced values; edge gaps hold the nearest
voiced value; a token is declared unavailable only below 3 voiced frames.

| | n |
|---|---|
| trajectory available | **1677 / 1746** |
| trajectory unavailable | **69** |
| — insufficient voiced frames | 53 |
| — Praat error (segment too short) | 16 |

Unavailable tokens split **61 Correct / 8 Incorrect**, close to the 83/17 corpus
balance, so the loss is not concentrated in one class. They were **kept** and
median-imputed inside each fold rather than dropped, as pre-specified.

## 2–5. Train grouped-CV results (GroupKFold(5) by speaker, class_weight balanced)

| representation | best C | dims | PR-AUC | ROC-AUC | fold PR (mean ± sd) |
|---|---|---|---|---|---|
| **R0 summary (baseline)** | 10 | 43 | 0.250 | 0.586 | 0.250 ± 0.107 |
| R1 trajectory N1 (onset-relative) | 1.0 | 83 | 0.288 | 0.613 | 0.265 ± 0.132 |
| **R2 trajectory N2 (median-centred)** | 0.1 | 83 | **0.292** | **0.637** | 0.270 ± 0.138 |
| R3 trajectory + summary | 10 | 123 | 0.276 | 0.632 | 0.268 ± 0.110 |

**R2 wins.** Median-centring beats onset-relative normalisation, which is
sensible: an onset-anchored contour inherits all the noise of a single first
point, whereas the token median is a robust anchor.

**R3 adds nothing.** Concatenating the 10 summary features onto the trajectory
*lowers* PR-AUC from 0.292 to 0.276. The summaries are derived from the same
contour, so they contribute no independent information and only add 40
parameters. That is itself a useful result: the trajectory subsumes the summary
representation rather than complementing it.

## 6. Native-template diagnostic

Usable. Native reference tokens per tone: T1 21, T2 21, T3 13, T4 30 — enough
for prototypes. Native tokens are an external reference and never entered
learner training labels.

| measure | Correct (median) | Incorrect (median) |
|---|---|---|
| distance to expected-tone prototype | 2.635 | **3.155** |
| expected-vs-alternative margin | −0.602 | **−0.873** |
| correlation with expected prototype | **0.781** | 0.561 |

All three move in the phonetically expected direction: tokens the raters marked
wrong sit further from the native prototype of the tone they were supposed to
produce, have a worse margin against competing tones, and correlate less with
the target shape. The correlation gap (0.78 vs 0.56) is the clearest.

This is a **diagnostic only**. The negative margins mean that for most tokens
some non-target prototype is actually closer, so nearest-template matching is
not a produced-tone classifier — and OMPAL could not validate such a claim
anyway, since it never records the produced tone.

## 7. R0 vs trajectory

| metric | R0 | R2 | Δ |
|---|---|---|---|
| PR-AUC | 0.250 | 0.292 | **+0.042** |
| ROC-AUC | 0.586 | 0.637 | **+0.051** |
| Balanced accuracy | 0.566 | 0.603 | +0.037 |
| Incorrect F1 | 0.327 | 0.367 | +0.040 |

The answer to the phase question is yes: compressing the contour into eight
summary statistics *was* discarding usable information. But the gain is modest,
and fold-to-fold PR-AUC varies ±0.138 — wider than the improvement itself.

## 8. Per tone (Train OOF ROC-AUC)

| representation | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| R0 summary | 0.599 | **0.475** | 0.654 | 0.589 |
| R1 trajectory N1 | 0.566 | 0.612 | 0.527 | 0.661 |
| **R2 trajectory N2** | 0.596 | **0.594** | 0.607 | 0.682 |
| R3 traj + summary | 0.587 | 0.545 | 0.680 | 0.674 |

**T2 moves off chance for the first time in this project**, 0.475 → 0.594. That
was the pre-specified mandatory diagnostic and it is the most substantive result
in C6. The rising tone is defined by *where* the rise happens, which a
mid-to-end slope statistic cannot express but a 20-point contour can.

T3 goes the other way, 0.654 → 0.607. The dipping tone was the one the summary
features handled best, and the trajectory representation trades some of that for
the T2 gain. R2 is more even across tones rather than uniformly better.

## 9. Trajectory-weight interpretation

Mean weight over early / middle / late thirds; positive pushes toward
**Incorrect**.

| tone | early | middle | late |
|---|---|---|---|
| T1 | −0.010 | −0.030 | −0.026 |
| T2 | −0.025 | **+0.204** | −0.128 |
| T3 | **−0.120** | +0.006 | −0.013 |
| T4 | −0.019 | −0.036 | **+0.090** |

These are phonetically readable, and each tone's largest weight sits where that
tone's defining event happens:

- **T2 (rising)** — a high middle is the strongest error signal of any tone
  (+0.204) while a high late region is protective (−0.128). A correct T2 rises
  *late*; a learner who is already high mid-syllable has produced something
  flatter, which is exactly the classic T2→T1 substitution.
- **T3 (dipping)** — a high early region pushes toward Incorrect (−0.120 means
  *low* early is penalised... read with the sign: the negative weight means
  lower early values push toward Correct). A correct T3 starts low and dips.
- **T4 (falling)** — a high late region is the error signal (+0.090). A correct
  T4 should have fallen by the end.
- **T1 (level)** — all three weights near zero, consistent with a level tone
  having no distinctive turning point to key on.

Caveat: one fit, 83 columns, 1424 tokens. Directions are interpretable;
magnitudes are not stable estimates.

## 10. Frozen Train-CV winner

**R2, median-centred 20-point semitone trajectory, C = 0.1, class_weight
balanced.** Frozen before Dev opened, with the trajectory definition, missing-F0
handling and CV design recorded in `ompal_phase_c6_protocol_FROZEN.json`.

## 11. One-time Dev confirmation

| metric | value |
|---|---|
| PR-AUC | 0.375 |
| ROC-AUC | 0.755 |
| Balanced accuracy | 0.711 |
| Incorrect F1 | 0.471 |

| tone | n | Incorrect | ROC-AUC |
|---|---|---|---|
| T1 | 82 | 11 | 0.572 |
| T2 | 74 | 10 | **0.773** |
| T3 | 40 | 10 | 0.730 |
| T4 | 126 | 24 | 0.791 |

Against C3's Dev figures (PR 0.385, ROC 0.726), PR-AUC is slightly lower and
ROC-AUC higher — the two are within the noise of a 6-speaker, 55-Incorrect set.

**The same optimism gap appears again**, and it should temper every number
above: Dev ROC 0.755 against a Train OOF estimate of 0.637, and Dev PR 0.375
against 0.292. The 32-speaker pooled estimate is the trustworthy one. The
honest summary is "ROC ≈0.64, PR ≈0.29", not the Dev figures.

## 12. Real-world technical interpretation

**Technical signal exists and improved. Deployment readiness did not change.**

What improved: the representation question is answered, T2 is no longer at
chance, and the learned weights are pedagogically readable — which matters,
because a system that eventually says "your second tone rose too early" needs
to be built on something that actually keys on the rise.

What did not: ROC ≈0.64 with 17% prevalence is still far from an operating
point that supports safe feedback. C4 showed that at ROC ≈0.60 no threshold
produced Incorrect precision above 0.60, and a 0.05 ROC gain does not overturn
that — the C4 machinery would need re-running to know, and it is deliberately
not re-run here. Fold variance (±0.138) still exceeds the improvement.

So the ordering is unchanged: a technical component improved, and the
deployment question remains answered **no**. Fresh human validation with at
least two independent Mandarin raters remains mandatory regardless, and cannot
be substituted by any benchmark result.

## 13. What follows

The natural next step is to re-run the decision-policy analysis (C4) on the
frozen R2 representation, since thresholds and abstention were last evaluated
against a weaker ranker. That is a re-run of an existing protocol, not a new
search, and it is the cheapest way to learn whether the improvement changes the
deployment answer.

Not justified: more normalisation variants, more trajectory point counts, or a
larger classifier family. The gain here came from *not* compressing the contour,
and that change has now been made once.
