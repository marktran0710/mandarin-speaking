# Fresh validation — sample size and precision plan

Planning only. **No future performance is assumed or fabricated.** The
simulation resamples the *observed* per-speaker PASS behaviour of the 32 OMPAL
Train speakers under the frozen policy. If real learners behave differently —
and they may, since OMPAL is French-L1 read speech while the study recruits a
mixed-L1 CFL sample — these figures shift.

## Coverage arithmetic

From the frozen C8 Train evidence:

| | value |
|---|---|
| overall coverage (all 4 tones) | **18.3%** |
| enabled-tone coverage (T2/T3/T4 only) | **25.0%** (260 PASS of 1040 tokens) |
| enabled-tone PASS precision | 0.919 |

The two differ because T1 is gated: 4 of 16 items can never PASS, so overall
coverage is mechanically 3/4 of the enabled-tone rate. **Report both.** The
first is what a learner experiences; the second is what the model achieves
where it is allowed to act. Reporting only the second would overstate the
product; reporting only the first would understate the model.

Per learner: 16 items → 12 enabled-tone items → **≈3 PASS decisions expected**.

## Speaker-cluster simulation

3000 simulated studies per N. Each draws N learners with replacement from the
32 OMPAL Train speakers, gives each 12 enabled-tone items, and applies that
speaker's own observed coverage and conditional precision. The reported width
is the median 95% cluster-bootstrap interval width for PASS precision.

| N learners | first attempts | PASS @18% | PASS @23% | clusters | simulated PASS (median) | **95% CI width** |
|---|---|---|---|---|---|---|
| 20 | 320 | 57 | 73 | 20 | 64 | **0.157** |
| **25** | **400** | **72** | **92** | **25** | **80** | **0.141** |
| 30 | 480 | 86 | 110 | 30 | 96 | **0.130** |
| 40 | 640 | 115 | 147 | 40 | 128 | **0.114** |

### Approximate binomial, ignoring clustering — for contrast only

This is the calculation to *avoid*; it is shown so the cost of clustering is
visible rather than assumed away.

| N | n PASS | true p=0.90 | p=0.92 | p=0.95 |
|---|---|---|---|---|
| 20 | ~60 | ±0.076 | ±0.069 | ±0.055 |
| 25 | ~75 | ±0.068 | ±0.061 | ±0.049 |
| 30 | ~90 | ±0.062 | ±0.056 | ±0.045 |
| 40 | ~120 | ±0.054 | ±0.049 | ±0.039 |

At N=25 the naive interval is ±0.068 (width 0.136) against a clustered width of
0.141. The gap is modest here only because each learner contributes ~3 PASS
decisions, leaving within-learner correlation little room to act. **Use the
clustered figure.** The binomial is optimistic and would become badly so if
items per learner were increased.

## What this means at the 0.90 criterion

At N=25 the expected half-width is roughly **±0.07**:

- If true precision is **0.95**, the observed CI sits near [0.88, 1.00] — the
  lower bound would probably still fall below 0.90.
- If true precision is **0.92**, the CI straddles 0.90.
- If true precision is **0.87**, the point estimate would likely land below
  0.90 and the study is clearly informative in the negative direction.

**The study can detect a clear failure at N=25. It cannot establish precision
≥0.90 with a CI lower bound above 0.90 unless true precision is around 0.95 or
better.** That asymmetry must be understood before recruiting, because the
protocol forbids repairing an ambiguous result by retuning `t_pass`.

Reaching a lower bound above 0.90 at a true 0.92 would need roughly 60+
learners on this design. It could also be reached by increasing items per
learner, at the cost of session length and stronger within-learner correlation
— which erodes the benefit non-linearly.

## Recommendation

**B. 25 learners is usable but precision will be limited.**

25 is adequate for an initial prospective validation: it will detect a clear
shortfall, produce usable coverage and technical-robustness estimates, and
surface usability problems. It will **not** deliver a confident "≥0.90"
certification unless true precision is high.

If recruitment beyond 25 is cheap, **30–40 materially narrows the interval**
(0.141 → 0.114) for a proportional increase in effort. If it is expensive,
proceed at 25 and report the interval honestly rather than over-claiming.

One design note that costs nothing to state: the 4 T1 items add 25% to session
length while contributing zero PASS decisions. They are retained deliberately —
they measure what the gate costs in coverage and whether T1 productions were
actually acceptable. But if session length becomes a recruitment obstacle,
dropping them is the first place to look, at the price of losing that estimate.
