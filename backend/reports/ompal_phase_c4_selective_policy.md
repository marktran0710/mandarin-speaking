# Phase C4 — calibration and selective feedback policy

The acoustic model is frozen (P1, `class_weight=balanced`, `C=10`). This phase
asked only whether a subset of learner attempts exists where automated feedback
is substantially safer than a forced binary verdict.

Developed on Train with nested speaker-grouped cross-fitting. **Dev was not
opened**, because no policy ever met the pre-specified admission rule. Test
untouched.

## 1. Cross-fitted calibration method

Outer `GroupKFold(5)` by speaker. Within each outer fold's training speakers,
an inner `GroupKFold(4)` produces out-of-fold scores, and a **single** sigmoid
(Platt) is fitted on those. The outer speakers touch neither the base model nor
the calibrator.

One implementation note that changed the numbers. `CalibratedClassifierCV`
averages *k inner models*, so its output is not a monotone transform of the
outer model's score — measured here it moved ROC from 0.586 to 0.428. A single
monotone calibrator was used instead, which is what the specified architecture
describes and what preserves ranking.

## 2. Calibration quality (Train OOF)

| | Brier | log loss | slope | intercept | mean predicted | ROC-AUC |
|---|---|---|---|---|---|---|
| raw P1 | 0.2359 | 0.7454 | 0.156 | −1.574 | 0.453 | **0.586** |
| calibrated sigmoid | **0.1429** | **0.4639** | −0.742 | −2.793 | **0.169** | **0.432** |

Calibration fixes the probability *scale* exactly as intended: mean predicted
0.169 against an observed prevalence of 0.169, with Brier improving from 0.236
to 0.143. Raw scores from a `balanced` model average 0.453 and are indeed not
usable as probabilities.

But the calibrated ROC **fell below chance**, which a monotone calibrator
cannot do within a fold. The cause is pooling:

| outer fold | test prevalence | train prevalence | sigmoid slope | calibrated mean | within-fold ROC |
|---|---|---|---|---|---|
| 1 | 0.069 | 0.195 | +0.110 | 0.193 | 0.627 |
| 2 | **0.299** | 0.137 | +0.120 | 0.141 | 0.519 |
| 3 | 0.190 | 0.164 | +0.005 | 0.164 | 0.643 |
| 4 | 0.130 | 0.179 | +0.157 | 0.174 | 0.611 |
| 5 | 0.158 | 0.172 | +0.088 | 0.173 | 0.610 |

Every fold's slope is positive and every within-fold ROC is above chance (mean
**0.602**). Pooled, the calibrated ROC is **0.432**.

The mechanism is speaker heterogeneity. Fold 1's held-out speakers are easy
(6.9% error) but its calibrator was fitted on 19.5%-prevalence data, so their
probabilities come out too high (mean 0.193). Fold 2's speakers are hard
(29.9%) but its calibrator saw 13.7%, so theirs come out too low (0.141). The
calibrated values end up **anti-correlated with true difficulty**, and pooling
inverts the ranking.

This is not a bug to fix — it is the finding. **A fixed probability threshold
does not mean the same thing for different speakers**, and for an unseen
learner their difficulty is exactly what is unknown. That is a direct obstacle
to any threshold-based deployment policy.

## 3. Binary threshold operating curve

Computed across 0.05–0.95 on Train OOF and saved in full. The summary is that
**no threshold reaches even 0.60 Incorrect precision**. At the prevalence of
16.9%, flagging is either so rare it is meaningless or so common that most
flags are wrong.

## 4. Three-way coverage–risk frontier

3,696 (t_accept, t_incorrect, T2-mode) combinations evaluated.

| target coverage | achieved | selective error | Incorrect precision | Acceptable precision |
|---|---|---|---|---|
| ~25% | 23.5% | 23.6% | — (0 flagged) | 0.764 (n=335) |
| ~50% | 47.5% | 19.5% | — (0 flagged) | 0.805 (n=676) |
| ~75% | 73.3% | 18.8% | — (0 flagged) | 0.812 (n=1044) |
| ~90% | not achievable with any flagged tokens | | | |

Two things stand out, and both are damaging.

**At every viable coverage point, zero tokens are flagged Incorrect.** The
policies that achieve reasonable selective error do so by only ever saying
"acceptable" — which is not feedback, it is silence.

**Acceptable precision never beats the base rate.** 0.764, 0.805 and 0.812
against a corpus base rate of **0.831 Correct**. Accepting everything without a
model would be *more* accurate than the selective accept set. The policy is
selecting a subset that is enriched for errors, not depleted of them — the
direct consequence of the ranking inversion in §2.

## 5. High-precision Incorrect operating points

| required precision | achievable? |
|---|---|
| ≥ 0.60 | **no** |
| ≥ 0.70 | **no** |
| ≥ 0.80 | **no** |
| ≥ 0.90 | **no** |

None is reachable at any threshold, at any coverage — not even by flagging a
handful of tokens. There is no operating point at which telling a learner "this
was incorrect" is more likely right than wrong.

## 6. Safe-Acceptable operating points

| required accept precision | achievable with ≥20 accepted tokens? |
|---|---|
| ≥ 90.0% | **no** |
| ≥ 95.0% | **no** |
| ≥ 97.5% | **no** |

The best observed acceptable precision is ≈0.81, below the 0.831 base rate.

## 7. Global vs T2-safe policy

Both were evaluated across the full grid.

| policy | admissible combinations |
|---|---|
| POLICY G (global thresholds) | **0** of 1,848 |
| POLICY T (T2 automatic-Incorrect disabled) | **0** of 1,848 |

The admission rule was fixed before any coverage number was computed:
Incorrect precision ≥ 0.50 (a flag must be more likely right than wrong),
Acceptable precision ≥ 0.90 (acceptance must beat the 83.1% base rate),
≥ 10 decisions in each category, and ≥ 20 of 32 speakers receiving a decision.

Disabling automatic Incorrect verdicts for T2 does not help, because the binding
constraint is not T2 specifically — no tone reaches usable flag precision.

## 8. Speaker and tone coverage

Not reported per policy, because no policy was frozen. The relevant speaker
finding is in §2: outer-fold prevalence ranges 6.9%–29.9%, so speaker
difficulty varies by more than a factor of four, and calibrated probabilities
are not comparable across those groups.

## 9. Error concentration

The abstention premise fails at the source. For abstention to help, errors must
concentrate near the decision boundary. Here the pooled calibrated ranking is
*inverted* relative to truth, so confidence does not order correctness at all —
high-confidence acceptances are enriched for actual errors rather than depleted.
Confidence-based abstention cannot be a safety mechanism when confidence is
anti-informative across speakers.

## 10. Frozen policy

**None.** No policy met the pre-specified rule, so nothing was frozen and
`ompal_phase_c4_policy_FROZEN.json` was deliberately not written. Freezing a
policy that fails its own admission criteria would misrepresent the state of
the work.

## 11. Dev confirmation

**Not performed.** Dev is opened only after a policy is frozen. There was
nothing to confirm, and opening Dev to look for a more flattering operating
point would be exactly the kind of search this protocol exists to prevent.

## 12. Practical interpretation

Phase C3 established that tone-conditional modelling produces genuine
discrimination — mean within-fold ROC 0.602, and that result stands. Phase C4
asked whether that discrimination is *enough to act on*, and the answer is no,
for two separable reasons:

1. **The signal is too weak in absolute terms.** ROC ≈0.60 with 17% prevalence
   cannot produce a flag that is more likely right than wrong at any threshold.
2. **The signal is not comparable across speakers.** Fold prevalence varies
   6.9%–29.9%, and a single calibrated threshold consequently means different
   things for different learners. This is the more fundamental problem, and it
   would not be solved by a slightly better classifier.

Selective automation is a sound idea and the machinery is now built and
validated. It is waiting on a stronger and more speaker-stable acoustic signal.

## 13. What would change the answer

Not more threshold search — the grid is exhausted. The candidates, in order of
expected value:

- **Speaker normalisation of the score**, so a threshold means the same thing
  for an easy and a hard learner. This addresses the §2 finding directly and is
  the only one that targets the fundamental obstacle.
- **A tone-sensitive front-end** preserving the F0 trajectory rather than eight
  summary statistics, since the late-contour features already carry what signal
  exists.
- **More speakers.** 32 training speakers with prevalence spanning 6.9%–29.9%
  is too few to estimate a stable operating point.

Fresh human validation remains required regardless, and cannot substitute for
any of the above.
