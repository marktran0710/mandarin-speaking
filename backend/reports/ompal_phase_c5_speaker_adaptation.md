# Phase C5 — unsupervised speaker/session adaptation feasibility

Base model frozen (P1, balanced, C=10). The question was whether a short
**unlabeled** warm-up from a learner makes scores comparable and useful.

No method met the bar, so **no protocol was frozen and Dev was not opened**.
Test untouched.

## 1. Simulation design

Leave-one-speaker-out over the 32 Train speakers: for each, the base model is
refit on the other 31 and the held-out speaker is scored as a completely unseen
learner. Their labels are revealed only for evaluation.

Within-speaker order is `utterance_id` then `token_index`. OMPAL has no
timestamps, so this stands in for recording order — documented as a limitation,
not a shuffle.

**Evaluation window is fixed at tokens from position 20 onward**, identical for
every K, so K=0 and K=20 are scored on exactly the same tokens. Without this,
larger K would silently evaluate on a different (later, smaller) set.

This costs coverage: only **16 of 32 speakers** have ≥25 tokens and are
evaluable. The 16 excluded speakers have 17 tokens each. Halving the speaker
pool is a real weakness of this simulation and the numbers below should be read
with that in mind.

Adaptation is label-blind by construction — `adapt()` receives warm-up scores
and tones only, and never a label. Asserted programmatically on every call
(192 assertions).

S2's scale floor (0.1630) is 0.25 × the median per-speaker score IQR, derived
from training speakers before any outcome was inspected. S3 requires ≥3
warm-up observations of a tone before using a tone-specific baseline, otherwise
falls back to S1.

## 2–5. Results

| method | K | pooled ROC | pooled PR-AUC | within-speaker ROC (median) | ρ(speaker median score, prevalence) |
|---|---|---|---|---|---|
| **S0 none** | 0 | **0.606** | **0.265** | **0.607** | **+0.615** |
| S1 centering | 5 | 0.582 | 0.248 | 0.607 | +0.053 |
| S1 centering | 10 | 0.601 | 0.260 | 0.607 | +0.400 |
| S1 centering | 20 | **0.613** | 0.284 | 0.607 | +0.285 |
| S2 loc+scale | 5 | 0.585 | 0.249 | 0.607 | +0.100 |
| S2 loc+scale | 10 | 0.605 | 0.222 | 0.607 | +0.347 |
| S2 loc+scale | 20 | 0.604 | 0.238 | 0.607 | +0.297 |
| S3 tone-cond. | 5 | 0.582 | 0.248 | 0.607 | +0.053 |
| S3 tone-cond. | 10 | 0.593 | 0.254 | 0.598 | +0.335 |
| S3 tone-cond. | 20 | 0.595 | 0.266 | 0.595 | +0.288 |

Best adapted result is S1 at K=20: pooled ROC 0.613 against a 0.606 baseline,
**+0.007**. At the practical budgets K=5 and K=10, every method is *worse* than
no adaptation at all.

## 6. Effect of warm-up size

K=5 costs 0.02 ROC. K=10 roughly restores the baseline. K=20 buys 0.007 above
it. The gain is not merely small — it is not monotone in K, which is what a
real effect would look like. A 20-token unlabeled warm-up before a learner
receives any feedback would be a heavy onboarding burden, and it purchases
nothing.

## 7. Within-speaker discrimination — the key measurement

Median within-speaker ROC is **0.607** and is **identical for S0, S1 and S2**.

That identity is not a coincidence and it is the analytic heart of this phase:
subtracting a per-speaker constant (S1) or dividing by a per-speaker scale (S2)
is a **monotone transform within that speaker**, so it cannot change the
within-speaker ranking at all. Only S3 can, because it shifts each tone
differently — and it makes things slightly *worse* (0.598 at K=10, 0.595 at
K=20).

So the ceiling for any score-normalisation approach is already visible:
within-learner discrimination is ≈0.61, and no amount of per-speaker rescaling
moves it.

## 8. Cross-speaker comparability — the C4 premise was wrong

Phase C4 concluded that cross-speaker score incomparability was the fundamental
obstacle. This phase shows that conclusion needs correcting.

The **unadapted** LOSO score already tracks speaker difficulty well:
ρ(speaker median score, speaker Incorrect prevalence) = **+0.615**. Speakers who
genuinely make more tone errors already receive systematically higher scores,
without any adaptation.

And pooled ROC (0.606) is essentially equal to median within-speaker ROC
(0.607) — if cross-speaker comparability were broken, pooling would be
*worse* than within-speaker performance. It is not.

What failed in C4 was the per-fold **calibrator**, which absorbed each fold's
training prevalence and so produced probabilities anti-correlated with true
difficulty. That is a defect of cross-fitted calibration under heterogeneous
folds, not a property of the raw score. The distinction matters: C4's
recommended next step (speaker normalisation) was aimed at the wrong target,
and this phase is the evidence that corrects it.

## 9. Per tone

| tone | n | Incorrect | S0 ROC | S1 K=20 ROC |
|---|---|---|---|---|
| T1 | 192 | 22 | 0.557 | 0.596 |
| T2 | 176 | 30 | **0.485** | **0.479** |
| T3 | 112 | 19 | 0.669 | 0.676 |
| T4 | 352 | 67 | 0.618 | 0.627 |

**T2 remains at chance and adaptation does not touch it** (0.485 → 0.479).
This was pre-specified as the test of whether normalisation solves tone
representation. It does not, and no claim to that effect can be made.

## 10. Does adaptation erase genuine learner difficulty?

**Yes, and this is the decisive harm.** The association between a speaker's
median score and their true error prevalence collapses from **+0.615**
unadapted to **+0.053** at S1 K=5, recovering only partially to +0.285–0.400 at
larger K.

A learner who genuinely produces many wrong tones is normalised toward
average — exactly the failure mode flagged in advance. The adaptation removes
real, correct information about learner proficiency and returns no
discrimination in exchange.

## 11. Frozen method

**None.** No method improved discrimination meaningfully, the only positive
result required the largest and least practical warm-up, and every method
damaged the score's genuine relationship to learner difficulty. Freezing one
would misstate the finding.

## 12. Dev confirmation

**Not performed**, per protocol: Dev opens only after a method is frozen.

## 13. Real-world implication

Neither deployment claim is supported:

- **One-shot unseen-speaker assessment** — not supported. Within-speaker ROC
  ≈0.61 with 17% prevalence, and C4 showed no safe operating point.
- **Session-adapted learner assessment** — not supported. Adaptation does not
  improve discrimination and cannot, since the useful transforms are monotone
  within a speaker.

The system is not real-world ready, and the obstacle is now located precisely:
it is **within-learner tone discrimination itself**, at ROC ≈0.61, not score
comparability across learners.

## 14. What this implies for the next stage

Score manipulation is exhausted. Thresholding (C4) and normalisation (C5) both
operate on a fixed ranking, and that ranking is the limit.

The justified next direction is a **tone-sensitive acoustic representation** —
not searched here, and to be pre-registered before implementation. The rationale
is that the current 10 features compress a tone contour into eight summary
statistics plus duration and voicing, discarding trajectory shape, while the
signal that does replicate is concentrated in late-contour measures. Candidate
directions to specify later: time-normalised F0 trajectories, expected-tone
template distance, and speaker-normalised semitone contours compared by
trajectory similarity rather than by summary statistics.

A supervised onboarding alternative (a teacher supplying a few labelled
calibration items) is theoretically possible but changes the deployment
workflow and would need its own research design. It is not investigated here,
and it would not address the within-learner ceiling either.

Fresh human validation remains required regardless and cannot substitute for
any of this.
