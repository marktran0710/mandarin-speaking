# Phase C8 — one-sided PASS / RETRY confirmation policy

C7 established that this model identifies likely-acceptable productions far
better than incorrect ones. The product is therefore no longer a
Correct/Incorrect classifier: it confirms good attempts and says nothing
otherwise.

**RETRY means "not enough evidence to confirm". It never means "wrong".**

Test sealed. Policy frozen on Train; Dev opened once as *development
confirmation* — Dev is not independent, having already been inspected in C6.

## 1. Train PASS operating curve

Frozen R2, `GroupKFold(5)` by speaker. **1424 rows, 32 speakers, 0 speaker
leakage** (asserted). 63 tokens (4.4%) have no extractable trajectory and are
forced to RETRY, remaining in every denominator.

## 2–3. Precision targets (≥100 PASS, ≥20 speakers)

| target | achievable | t_pass | precision | 95% CI | n PASS | coverage | speakers | false PASS |
|---|---|---|---|---|---|---|---|---|
| ≥ 0.900 | **yes** | 0.4227 | 0.901 | [0.823, 0.962] | 284 | 19.9% | 31 | 28 |
| ≥ 0.925 | **NOT ACHIEVABLE WITH ADEQUATE SUPPORT** | | | | | | | |
| ≥ 0.950 | **NOT ACHIEVABLE WITH ADEQUATE SUPPORT** | | | | | | | |
| ≥ 0.975 | **NOT ACHIEVABLE WITH ADEQUATE SUPPORT** | | | | | | | |

Intervals are speaker-cluster bootstrap (4000 resamples of the 32 speakers,
not of tokens — tokens within a learner are not independent).

## 4–5. POLICY A vs POLICY B

**Tone-safety gate** at POLICY A's threshold (≥20 PASS and ≥0.85 precision):

| tone | n PASS | precision | false PASS | verdict |
|---|---|---|---|---|
| T1 | 24 | **0.708** | 7 | **GATED → RETRY** |
| T2 | 75 | 0.907 | 7 | eligible |
| T3 | 49 | 0.898 | 5 | eligible |
| T4 | 136 | 0.934 | 9 | eligible |

| policy | precision | 95% CI | n PASS | coverage | speakers | false PASS |
|---|---|---|---|---|---|---|
| A global (T1–T4) | 0.901 | [0.823, 0.962] | 284 | 19.9% | 31 | 28 |
| **B gated (T2,T3,T4)** | **0.919** | [0.861, 0.966] | 260 | 18.3% | 31 | **21** |

**POLICY B selected** on the pre-specified priority order: higher precision,
identical speaker coverage (31/32), better tone safety, at the cost of 24 PASS
decisions.

## 6. T1 analysis

T1 fails the safety gate on the evidence: **0.708 PASS precision on 24
decisions**, roughly 3 in 10 confirmations wrong. It is gated to RETRY.

This was not assumed from theory — Mandarin T1 is often described as the
easiest tone, and it is the *worst* here. A plausible reason is that a level
tone has no distinctive turning point for a contour model to key on, which is
consistent with C6's finding that T1's learned trajectory weights were near
zero across early, middle and late thirds. Whatever the cause, the empirical
result governs.

The cost is real: T1 is 27% of the corpus, and the system cannot confirm any
level tone.

## 7. T2 analysis

**Yes — R2 can safely confirm good T2 productions even though it cannot
diagnose bad ones.** T2 PASS precision is 0.907 on 75 decisions, second only to
T4, while C7 measured T2 *flag* precision at 0.216, the worst of any tone.

The asymmetry is the whole basis of this phase, and T2 is its clearest case: a
contour that clearly rises is good evidence of a correct T2; a contour that does
not is weak evidence of anything, because it could be a mistracked F0, a short
token, or a genuine error.

## 8. Speaker coverage

31 of 32 speakers receive at least one PASS; **1 speaker receives none**.
Confirmations are not concentrated in a few easy learners, which was the
central equity risk.

## 9. False-PASS audit

21 tokens under the frozen policy are genuinely Incorrect but confirmed. This
is now the principal harmful error: a learner is told a wrong tone was
acceptable. Per-token detail (tone, speaker, score, distance from threshold) is
in `ompal_phase_c8_summary.json`.

Descriptive only. The threshold was frozen before this audit, and nothing was
changed after inspecting it.

## 10. Frozen policy

```
POLICY_B_tone_gated
t_pass          = 0.4227
enabled tones   = T2, T3, T4   (T1 gated to RETRY)
trajectory rule = unavailable -> RETRY, never PASS
outputs         = PASS | RETRY only
Train precision = 0.919, 95% CI [0.861, 0.966]
Train PASS      = 260 (18.3% coverage), 21 false PASS
speakers        = 31/32 with >=1 PASS
```

## 11. One-time Dev confirmation

*Development confirmation, not independent validation.*

| | Dev |
|---|---|
| PASS | 75 (23.3% coverage) |
| PASS precision | **0.973**, 95% CI [0.930, 1.000] |
| false PASS | 2 |
| speakers with PASS | 6/6 |

Per tone: T2 1.000 (n=15), T3 1.000 (n=11), T4 0.959 (n=49), T1 0 by gate.

## 12. Train–Dev stability

Δprecision **+0.054** (0.919 → 0.973), Δcoverage **+0.050** (18.3% → 23.3%).

Both move in the same direction and both clear 0.90, so the policy does not
collapse when moved. But this is the **fourth consecutive phase where Dev
exceeds the Train estimate**, and with 6 speakers and a CI upper bound pinned at
1.000, the Dev figure should not be read as the expected performance. The Train
estimate of 0.919 — itself with a lower bound of 0.861 — is the number to plan
against.

## 13. Learner-facing interpretation

Allowed on PASS: *"Your tone sounds acceptable. You can continue."*

Allowed on RETRY: *"I'm not confident enough to confirm this attempt. Please try
once more."*

Forbidden in all cases: any wording equivalent to "your tone is wrong", and any
produced-tone claim such as "you said second tone instead of third". OMPAL
carries no produced-tone labels, so that capability has never been validated
and cannot be asserted.

The raw R2 score is internal. It is not a probability and must not be shown as
a percentage or a score out of ten.

What a learner would actually experience: roughly one attempt in five confirmed,
nothing confirmed for level tones, and about 8 in 100 confirmations wrong.

## 14. Interpretation

The one-sided reformulation works better than anything before it, and it works
only in a narrow band. Three things temper it:

- The Train 95% CI is **[0.861, 0.966]** — the point estimate clears 0.90 but
  the interval does not exclude values well below it. 32 speakers cannot
  establish precision ≥0.90 with confidence.
- **T1 cannot be served at all**, which removes 27% of the material from the
  product rather than from the metric.
- Coverage is 18–23%, so the system is silent on four attempts in five.

None of that makes the result worthless — a tool that reliably confirms good
attempts and otherwise asks for another try is pedagogically coherent and
cannot teach an error by asserting one. But it is a narrower product than
intended, and the evidence is not yet solid enough to call the policy
established.

## 15. What follows

Not more benchmark tuning. The next stage is **fresh human validation** on real
learner recordings, validating **PASS vs RETRY** rather than Correct/Incorrect
diagnosis. Protocol in `fresh_human_validation_protocol.md`.

Test stays sealed. It should be spent, if at all, only after the practical
formulation is fully frozen and has survived contact with real learners.
