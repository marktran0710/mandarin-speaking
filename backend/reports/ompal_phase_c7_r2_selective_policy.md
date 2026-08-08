# Phase C7 — selective decision policy on the frozen R2 trajectory model

A re-run of the C4 decision-policy question against the stronger C6
representation. R2 is frozen; nothing about the model was searched or retuned.
Test sealed.

## 1. R2 OOF score generation

Frozen R2 (20-point median-centred semitone trajectory + expected-tone
interactions, L2 logistic, balanced, C=0.1), scored with `GroupKFold(5)` by
speaker. Trajectory available for **1361/1424** Train tokens; the **63**
failures route to RETRY and remain in every denominator.

## 2. Raw vs calibrated

| | Brier | log loss | slope | mean predicted | pooled ROC | within-fold ROC |
|---|---|---|---|---|---|---|
| CAL0 raw | 0.2323 | 0.6681 | +0.476 | 0.472 | **0.637** | 0.628 |
| CAL1 sigmoid | **0.1412** | **0.4568** | +0.293 | **0.168** | **0.500** | 0.628 |

**The C4 calibration pathology reproduces exactly.** Calibration fixes the
probability scale (mean 0.168 against prevalence 0.169, Brier 0.232 → 0.141)
and leaves within-fold ranking untouched at 0.628 — but pooled ROC collapses to
**0.500**, chance.

This is now confirmed as a property of cross-fitted calibration under
speaker-heterogeneous folds, not of the weaker model: each fold's sigmoid
absorbs its own training prevalence, so calibrated values are not comparable
across folds even though every fold is internally fine.

The policy therefore uses the **raw R2 score as a ranking score only**. It is
not a probability, must never be shown to a learner as a percentage, and no
"% pronunciation correctness" claim can be built on it.

## 3. Binary operating curve

Computed over score quantiles and saved in full. The ceiling is the headline:
**the best Incorrect precision at any operating point with ≥10 flagged tokens
is 0.512**.

## 4. Did R2 cross the C4 barriers?

| barrier | C4 result | C7 result |
|---|---|---|
| Incorrect precision ≥ 0.60 | not reachable | **not reachable** |
| Incorrect precision ≥ 0.50 (C4's own frozen bar) | not reachable | **reachable** |
| Acceptable precision ≥ 0.90 | not reachable | **reachable** (n=285, prec 0.902, 31 speakers) |

**Two of three barriers were crossed.** In C4 no accept set beat the 0.831 base
rate; here a 285-token accept set reaches 0.902, and the best at n≥200 is
0.910. That is a real improvement attributable to the representation, since
everything else is unchanged.

The Incorrect side did not cross the 0.60 bar specified for this phase, and its
ceiling of 0.512 means roughly one in two "incorrect" verdicts would still be
unjustified.

## 5. Coverage–risk frontier

| coverage | achieved | selective error | Acceptable prec | Incorrect prec |
|---|---|---|---|---|
| ~25% | 22.6% | **10.9%** | 0.895 (n=314) | 0.750 (n=8) |
| ~50% | 47.5% | 11.7% | 0.885 (n=668) | 0.750 (n=8) |
| ~75% | 73.1% | 23.8% | 0.880 (n=820) | 0.321 (n=221) |
| ~90% | 87.1% | 32.9% | 0.880 (n=820) | 0.262 (n=420) |

Selective error at low coverage (10.9%) is far better than C4's best (18.7%).
The Incorrect precision of 0.750 at 25–50% coverage rests on **8 tokens** and
should not be read as an operating point.

## 6–7. Precision-constrained operating points

| Incorrect precision | reachable at n≥10 |
|---|---|
| ≥ 0.60 / 0.70 / 0.80 / 0.90 | **no** |
| best achievable | **0.512** at n=41, recall 0.087, 19 speakers |

| Acceptable precision | best n | speakers |
|---|---|---|
| ≥ 0.90 | 285 (20.0% of tokens) | 31 |
| ≥ 0.95 / 0.975 | not reachable | — |

Accept-side feedback is now defensible in a limited region. Flag-side feedback
is not: at its best precision the system catches **8.7% of actual errors** and
is wrong about half the times it speaks.

## 8. Global vs T2-safe

| admission bar | POLICY G (global) | POLICY T2SAFE |
|---|---|---|
| IncPrec ≥ 0.60 (this phase's rule) | **0** | **0** |
| IncPrec ≥ 0.50 (C4's own bar) | **0** | **6** |

**Admissibility exists only with T2 restricted.** Despite T2's ROC improving
from 0.475 to 0.594, its *flag precision* remains the worst of any tone (0.216
at the reference point, against T4's 0.438 and T1's 0.750). Better ranking has
not translated into trustworthy T2 verdicts, and the C4-era caution about
automatic T2 feedback is still warranted on the evidence.

Best T2-safe policy at C4's bar: t_accept 0.4228, t_incorrect 0.6729, coverage
22.9%, Acceptable precision 0.902 (n=285), Incorrect precision 0.512 (n=41),
Incorrect recall 0.087, selective error 0.147.

## 9. Speaker coverage

For that policy: **31 of 32** speakers receive at least one automatic decision,
23 receive five or more, 31 receive an Acceptable verdict and **19** receive an
Incorrect verdict. Decisions are not concentrated in a handful of easy
speakers, which was a genuine risk and is the one structural criterion this
policy clearly passes.

## 10. Tone coverage (reference operating point)

| tone | n | automatic | retry | coverage | Acc prec | Inc prec (n) | selective error |
|---|---|---|---|---|---|---|---|
| T1 | 384 | 100 | 284 | 26.0% | 0.807 | 0.750 (12) | 0.200 |
| T2 | 320 | 142 | 178 | 44.4% | 0.895 | **0.216** (37) | 0.282 |
| T3 | 192 | 104 | 88 | 54.2% | 0.897 | 0.261 (46) | 0.385 |
| T4 | 528 | 224 | 304 | 42.4% | 0.903 | 0.438 (48) | 0.196 |

T1's accept precision (0.807) is the weakest, and T3 carries the highest
selective error (0.385) despite good coverage. No tone is uniformly safe.

## 11. Trajectory-unavailable handling

63 Train tokens (4.4%) have no extractable trajectory and are routed to RETRY
by rule, never to an automatic verdict. This is a deployment safety rule: a
failed F0 extraction is a reason to ask the learner to try again, not evidence
about their pronunciation. It costs 4.4 percentage points of maximum coverage,
and those tokens remain in every denominator rather than being excluded.

## 12. Frozen policy

**None.** The pre-specified C7 admission rule (Incorrect precision ≥ 0.60,
Acceptable ≥ 0.90, ≥10 each) is met by zero of 2,244 combinations, so nothing
was frozen. The rule was not weakened to manufacture a pass, and the fact that
C4's laxer 0.50 bar is now met is reported as a separate, real finding rather
than substituted for it.

## 13. Dev confirmation

**Not performed.** Dev opens only after a Train policy is frozen, and Dev is
already non-pristine from C6. Opening it to look for a friendlier operating
point would be exactly the misuse this protocol prevents.

## 14. Practical interpretation

Separating the layers, as required:

- **Discrimination** — improved and real. Within-fold ROC 0.628, up from ~0.586.
- **Decision reliability** — asymmetric. Accept-side verdicts reach 0.902
  precision over 285 tokens; flag-side verdicts top out at 0.512 and catch 8.7%
  of errors.
- **Coverage** — 22.9% automatic at the best admissible-under-C4 policy, i.e.
  the system would abstain on more than three attempts in four.
- **Technical availability** — 4.4% of tokens cannot be scored at all.
- **Real-world validity** — unestablished. No fresh human validation exists,
  and no OMPAL result can substitute for it.

A system that says "this sounds fine" reliably, says nothing most of the time,
and is wrong half the times it says "this is incorrect" is not a pronunciation
tutor. The accept-side result is nonetheless the first genuinely usable signal
this project has produced, and it points at a narrower product than the
original one: **confirmation of good attempts**, not diagnosis of bad ones.

Error confidence remains unhelpful: at the reference point, wrong automatic
decisions sit *further* from the score midpoint (median |dev| 0.120) than
correct ones (0.100). Errors are not concentrated near the boundary, so
widening the abstention band would discard correct decisions about as fast as
wrong ones.

## 15. What follows

Test is not opened, and C7 does not justify opening it. The decision between
(a) spending Test on the current evidence and (b) preparing fresh human-labelled
validation first is deliberately left open, as specified.

If the project continues on the benchmark, the informative question is whether
the accept-side region survives on Dev and Test — but that is one shot, and the
flag-side weakness means a positive result would still only support a
confirmation tool. Fresh human validation with at least two independent Mandarin
raters remains mandatory before any deployment claim, and would also be the only
way to check whether the accept-side precision holds on real learner recordings
rather than OMPAL read speech.
