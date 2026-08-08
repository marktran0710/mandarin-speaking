# OMPAL pronunciation assessment — real-world validation protocol

## Research objective

The question is not which acoustic representation scores highest. It is:

> Can this system make tone/pronunciation judgments consistent enough with
> human judgment, and safe enough in its errors, to be used with real CFL
> learners?

Benchmark accuracy is one input to that answer and is not sufficient on its
own. A system can agree with OMPAL labels and still be unusable — by rejecting
good speech often enough to demoralise a learner, by approving bad speech and
teaching an error, by failing for one learner in ten, or by reporting
confidence values that mean nothing.

Two layers are kept separate throughout:

**Layer 1 — benchmark validity.** Can the system separate Correct from
Incorrect for *unseen* learner speakers?

**Layer 2 — deployment validity.** Can the resulting system safely support
pronunciation practice with real learners?

Layer 1 passing does not imply Layer 2. Layer 1 failing does rule Layer 2 out.

## Phase structure

| Phase | Content | Status |
|---|---|---|
| A | Corpus, alignment, QC validation | complete |
| B | Speaker-disjoint benchmark construction | complete |
| C | Train/Dev acoustic model development | **complete (this document)** |
| D | One-time sealed Test evaluation | next |
| E | Fresh human-expert validation | future |
| F | Prospective learner pilot | future |

No phase may be skipped. Benchmark results never justify a deployment claim
directly.

## Stage 1 — benchmark validation (Phases C–D)

Three systems, one classifier, so the comparison is between representations:

- **MODEL_A** frozen wav2vec2 (mean or temporal-3 pooling)
- **MODEL_B** Praat relative-contour features
- **MODEL_C** concatenation of the two

Downstream model is L2 logistic regression in every case. No classifier
search, no neural fusion, no stacking.

**Expected tone** is represented as **option B: acoustic features plus an
explicit one-hot encoding of the expected tone.** Option A (a separate model
per tone) would divide 241 training Incorrect tokens into four groups of about
sixty, which cannot support the minority-class metrics this project reports.
Option B is also the faithful deployment representation: the real system always
knows the target the learner was asked to produce. The same rule applies to all
three models.

**Class imbalance** (17% Incorrect) is handled only by the `class_weight`
option. No resampling, no SMOTE, no duplication — those would change the
prevalence the deployment decision depends on.

**Selection metric** is Dev PR-AUC for the Incorrect class. Accuracy is
reported last and is descriptive only: predicting "Correct" for everything
scores 83%.

**Search grid** (fixed in advance, not widened afterwards): pooling
{mean, temporal-3} × class_weight {None, balanced} × C {0.01, 0.1, 1, 10}.

**Threshold rule**, pre-specified: maximise Incorrect F1 on Dev, with the
resulting false-rejection and false-acceptance rates reported alongside. The
threshold is frozen before Test opens.

## Stage 1 outcome and what it means for Stage 2

All three systems perform near chance on Dev (ROC-AUC 0.517–0.548, balanced
accuracy 0.56–0.59, PR-AUC 0.195–0.221 against a 0.171 prevalence floor). Full
numbers are in `ompal_dev_model_selection.md`.

**Layer 1 is therefore not satisfied, and Layer 2 cannot currently be
attempted.** Stages 2 and 3 below remain specified so the work is ready if a
future representation clears Layer 1, but running a human-validation study or
a learner pilot on a chance-level system would waste participants' time and
risk teaching learners from noise.

## Stage 2 — fresh human-expert validation (Phase E)

Agreement with OMPAL labels is not sufficient to establish real-world
validity. OMPAL is French-L1 read speech rated by three of four experts, with
no record of which wrong tone was produced. It cannot tell us how the system
behaves on our learners, on spontaneous speech, or against our teachers'
standards.

Requirements:

- Fresh learner recordings, collected through the actual app workflow, not
  from OMPAL.
- **At least two Mandarin raters**, ideally Taiwan-based CFL teachers, rating
  independently and blind to the system output.
- Same binary criterion as the benchmark (target tone produced correctly or
  not), plus a free-text note so systematic disagreements can be inspected.

Estimates to produce:

| Quantity | Why it matters |
|---|---|
| human–human agreement (Cohen/Fleiss κ) | the ceiling; system–human agreement cannot meaningfully exceed it |
| system–human agreement | the actual validity estimate |
| false rejection rate | good speech marked wrong — the frustration path |
| false acceptance rate | bad speech marked fine — the mis-teaching path |
| sensitivity for real errors | does it catch what a teacher would correct |
| specificity for acceptable speech | does it leave acceptable speech alone |

Human–human agreement must be reported **first**. If two teachers agree only
moderately, no system can be asked to do better, and the target moves.

## Stage 3 — prospective learner pilot (Phase F)

Real CFL learners using the real workflow:

```
teacher provides target/script → learner records → system analyses
→ system gives feedback → learner retries if needed
```

### Technical
- processing latency per item (median and 90th percentile)
- failed analyses (rate and cause)
- audio capture failures
- % of attempts that receive usable feedback

### Assessment validity
- human–system agreement on the same recordings
- false rejection rate, false acceptance rate — reported separately, never
  merged into one accuracy figure

### Learner usability
- completion rate
- retries per item
- time per item
- learner-reported clarity of feedback
- learner-reported usefulness
- reported frustration/difficulty

### Pedagogical usefulness
- change from first attempt to retry
- teacher judgement of whether the feedback supports correction

**Improvement from attempt to retry is not evidence of learning.** It measures
within-session change, confounded with practice and with the learner simply
trying harder. A learning claim needs a control condition and a delayed
post-test, which this pilot design does not have — so it must not be claimed.

## Deployment-readiness evidence table

| Criterion | Required evidence | Status |
|---|---|---|
| works on unseen speakers | speaker-disjoint Test | **not yet validated** — Dev near chance |
| detects Incorrect pronunciation | Incorrect recall / F1 | **not yet validated** |
| doesn't reject good speech | false rejection rate | **not yet validated** |
| doesn't approve bad speech | false acceptance rate | **not yet validated** |
| confidence is meaningful | calibration | **not yet validated** — probabilities span 0.12–0.49, no discrimination |
| stable across tones | per-tone analysis | **not yet validated** — Dev balanced accuracy 0.40–0.70 by tone |
| stable across learners | per-speaker analysis | **partially validated** — measured, but on 6 Dev speakers |
| fast enough | latency measurement | **not yet validated** — not measured |
| usable by learners | prospective pilot | **not yet validated** |
| consistent with teachers | fresh human validation | **not yet validated** |
| segment extraction is sound | blinded human QC | **partially validated** — 81/100 usable |
| benchmark is not lexically confounded | metadata-only baselines | **validated** — all at or below majority, ≤3.1% Incorrect recall |
| split has no speaker leakage | 25 programmatic assertions | **validated** |

Nothing in this table permits the phrase "real-world ready", and the first six
rows would each have to change before the phrase could be used.

## Statistical uncertainty for Test (Phase D)

Tokens are clustered within speakers: 322 Test tokens come from 7 speakers, so
they are nowhere near 322 independent observations. Treating them as
independent would produce intervals that are far too narrow.

**Pre-defined procedure, to be executed once at Phase D:**

1. Resample the **7 Test speakers with replacement**, 2000 times.
2. Within each resample, pool all tokens of the drawn speakers (a speaker drawn
   twice contributes its tokens twice).
3. Recompute every reported metric inside each resample.
4. Report the 2.5th and 97.5th percentiles as the interval.

With 7 clusters these intervals will be wide, and that width is the honest
representation of what 7 speakers can tell us — not a defect to be tuned away.

## Test-sealing rules

During Phase C: no Test predictions, no Test metrics, no Test error analysis,
no Test-based threshold selection. Test features were not even extracted.

At Phase D, Test is opened **once**. After it is opened, no model,
hyperparameter, threshold or feature may be changed on the basis of what it
showed. If the result is disappointing, that is the result.
