# PFA vs BKT pilot audit

Date: 2026-08-27
Baseline: `d9f1513 add PFA and BKT quiz analytics pilot`

## Audit result

| Component | Expected | Actual | Result | Risk / limitation |
|---|---|---|---|---|
| Identity | Stable `studentId + conceptId`, legacy fallback visible | `conceptId` is preferred, `word` fallback is counted, records are ordered and duplicate attempt positions are removed | PASS | Id-less attempts cannot be safely deduplicated without collapsing legitimate retries; they remain eligible and are counted in `attemptsWithoutId` |
| PFA | Count-based prediction with regularized global coefficients | Counts successes/failures per student/concept; predicts with logistic sigmoid; fits coefficients on the training prefix with L2 regularization | PASS | `mastery` is the predicted-correct probability, not a separate latent variable |
| BKT | Bayesian posterior + learning transition with shared parameters | Uses prior/guess/slip for prediction, Bayesian posterior after the response, then applies `learn`; parameters are shared across skills in the requested scope | PASS | Parameters are refit per API scope; this is not a cached cohort-wide parameter set |
| Evaluation | Time-split, pre-response prediction, no leakage | Normalized records are split in order; parameters/state use the prefix; each evaluation response is predicted before update | PASS | Pilot currently uses one holdout split; multi-split stability and confidence intervals are not yet implemented |
| Data quality | Invalid/legacy/duplicate data visible | Quality counters include skipped responses, legacy concepts, duplicate responses, missing ids and invalid timestamps | PASS | Level filtering depends on `question_results[].level`; old records without that field cannot be recovered by the filter |
| API auth | Admin-only analytics | Anonymous receives 401; teacher/student receive 403; admin receives the model response | PASS | No schema migration or cache is involved |
| UI | Admin-only, provisional, no student behavior change | Admin analytics renders PFA/BKT comparison, loading/error/insufficient-data states and explicit mastery semantics | PASS | UI currently loads the unfiltered comparison view only |

## Model mechanics

For each `studentId + conceptId`, the pipeline is:

```text
stored quiz response
→ normalize identity / order / quality counters
→ fit on historical prefix
→ predict the next response
→ update model state with the observed result
→ calculate log loss, Brier, calibration and optional AUC
```

PFA uses:

```text
sigmoid(intercept + successWeight × successes + failureWeight × failures)
```

BKT uses:

```text
P(correct) = mastery × (1 - slip) + (1 - mastery) × guess
posterior = Bayesian update from correct/incorrect
next mastery = posterior + (1 - posterior) × learn
```

The API reports PFA skill values as `predicted_correct_probability` and BKT skill values as `latent_mastery_probability`, so the two meanings are not conflated in the admin UI.

## Verification performed

- Backend pilot and API tests: `20/20` passed.
- Backend regression set including vocab attempts, weak words and auth: `56/56` passed.
- Frontend pilot/admin targeted tests: `6/6` passed.
- Frontend production build: passed.
- Full frontend suite: `92` files passed, `4` existing unrelated files failed (`StoryVocabQuiz` button text and `teacherStories` snapshot expectation); no pilot file is involved in those failures.

The pilot remains analytics-only. It does not select quiz questions, change scoring, change weak-word behavior, unlock activities, or affect pronunciation/tone evaluation.
