# Study-start gate

```
STUDY_START_READY = NO
```

There is exactly one master status, and it is here. It may become `YES` only
when every condition below is satisfied. Any single unmet condition keeps it
`NO`.

## Conditions

| # | condition | category | status |
|---|---|---|---|
| 1 | all 16 items teacher-approved | HUMAN | **PENDING** |
| 2 | 話 / 電 issue resolved by the teacher | HUMAN | **PENDING** |
| 3 | T3 acceptability rule approved and pasted into the rater instructions | HUMAN | **PENDING** |
| 4 | participant instructions finalised | HUMAN | drafted, **PENDING** approval |
| 5 | rater instructions finalised (includes the approved T3 rule) | HUMAN | drafted, **PENDING** condition 3 |
| 6 | rater training completed | HUMAN | **PENDING** |
| 7 | ethics / consent requirements confirmed | ADMINISTRATIVE | **PENDING EXTERNAL CONFIRMATION** |
| 8 | operational pilot completed | OPERATIONAL | **PENDING** |
| 9 | frozen system hash verified | TECHNICAL | **COMPLETE** — `8101bcaf8c92e1e3…`, 19/19 preflight |
| 10 | data paths verified | TECHNICAL | verified in preflight; re-confirmed by pilot item 5 (**PENDING**) |
| 11 | analysis script frozen | TECHNICAL | **COMPLETE** — no model import, no fit call |
| 12 | OMPAL Test sealed | TECHNICAL | **COMPLETE** — 5/5 seal checks, `verify_ompal_test_seal.py` |

```
TECHNICAL GATES        COMPLETE
HUMAN / ADMINISTRATIVE GATES   PENDING
```

## Recruitment plan

| | |
|---|---|
| preferred target | **30 completed CFL learners** |
| minimum usable | 25 |
| maximum practical | 40 |
| items per participant | 16 first attempts |
| planned first-attempt recordings | **≈480** at N=30 |

**N=30 is not a formally powered sample.** No power calculation supports it, and
it must not be described as powered. It is the planned prospective validation
sample, chosen to balance precision against feasibility: the simulated 95%
cluster-bootstrap interval width for PASS precision is 0.141 at N=25, 0.130 at
N=30 and 0.114 at N=40 (see `fresh_validation_sample_size_precision_plan.md`).
At N=30 the interval will be roughly ±0.065, which can detect a clear shortfall
but will not certify precision ≥0.90 unless true precision is around 0.95.

The protocol accepts **25–40** participants. Nothing in the analysis depends on
the exact number; the cluster bootstrap uses whatever participants completed.

## Stopping rule

Recruitment stops when **30 completed eligible participants** are reached (or at
a documented cut-off within 25–40 if recruitment is slower or faster than
expected).

Stopping depends on **completed eligible participants only**. It does not depend
on model performance.

- Do **not** stop early because preliminary PASS precision looks good.
- Do **not** continue past target because preliminary PASS precision looks bad.
- Do **not** compute validation outcomes during recruitment to inform any
  decision.

Withdrawals and unusable sessions are handled by the pre-registered rules in the
protocol (§15): a withdrawn participant's trials are excluded and the
participant is counted in the flow diagram. Replacing them to reach the target
is permitted and must be recorded.

## Interim-peeking safeguard

Before the recruitment target is reached, do **not** produce, for any
decision-making purpose:

- system–human PASS precision
- tone-specific precision
- confidence intervals
- any PASS/RETRY × ACCEPT/REJECT table

**Permitted technical monitoring** — these are about whether data collection is
working, not about whether the system is right:

- missing or empty files
- audio capture failure rate
- trajectory failure rate
- latency
- tracker completeness

The distinction is simple: monitor the *pipeline*, never the *verdict*.
`analyze_fresh_human_validation.py` is run **once**, after recruitment and
ratings are complete.

## Definition of phase completion

This validation phase is **COMPLETE** when all three hold:

1. target participant recruitment completed,
2. two-rater formal ratings completed,
3. the pre-registered final analysis executed as frozen.

**This holds regardless of the result. A negative result is a valid endpoint.**

If PASS precision falls below 0.90, the study has produced its finding. Do not
automatically begin a new tuning cycle, do not move `t_pass`, do not re-enable
T1, and do not refit on validation data. Any subsequent development is a new
project decision, made deliberately, with a new frozen system version and a new
independent validation set.

## Final analysis sequence — fixed

```
human–human reliability
    ↓
human consensus
    ↓
system PASS precision
    ↓
speaker-cluster CI
    ↓
coverage
    ↓
tone-specific results
    ↓
technical robustness
    ↓
usability
```

Reliability comes first because it is the ceiling: system–human agreement cannot
meaningfully exceed human–human agreement. The order is not changed after seeing
results, and neither is the analysis plan.

## Authorising the start

`STUDY_START_READY` moves to `YES` only by a dated, named entry here, after
conditions 1–12 all read COMPLETE.

**Authorised by:** ____________  **Date:** ____________
