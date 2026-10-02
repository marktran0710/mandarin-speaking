# BKT and adaptive vocabulary code review

Review date: 2026-10-02 (Asia/Taipei). Source baseline: `6a6a34fc204c129a2d22a7fd9e1e822c6225c364`.

## Conclusion

The production BKT equations are consistent with standard two-state, no-forgetting BKT. Input validation, server-side grading, immutable response facts, exposure deduplication, and the separate review scheduler are useful engineering safeguards. This supports using the implementation as a pilot baseline; it does not establish that its latent mastery estimates match learner knowledge.

The user reports a 40-student pilot and no calibration performed. This review did not read the pilot database, fit parameters, or inspect an active deployment. Numerical examples below use the code defaults. They are deterministic behavior checks, not estimates of how often a problem occurs in the pilot.

## Findings to address first

### 1. Corrective question selection can disagree with completion targeting

Sources: `frontend/src/entities/vocabulary/quizGeneration.ts:101`, `backend/analytics/learner_model/bkt/mastery.py:830`, and `backend/analytics/learner_model/vocabulary_state.py:91`.

The backend's `failedQuestionTypes` contains every question type ever answered incorrectly. The frontend selects the first bank item matching any of those types. Correct answers do not remove a type from that list. Meanwhile, the backend's corrective completion rule targets only the most recent failed dimension.

For a bank ordered meaning, pinyin, context, consider diagnostic outcomes meaning wrong, pinyin wrong, context right. Personalized selection continues to choose meaning. Even ten subsequent meaning successes leave the current pinyin requirement unsatisfied: default BKT reaches `pLearned=0.999999`, but practice remains `IN_PROGRESS`, review remains `NEEDS_PRACTICE`, and `targetedSuccess=False`.

This is a selection/completion mismatch, independent of calibration. Align question selection with the server's current unresolved dimensions, and stop selecting a dimension after its corrective requirement is satisfied. The desired policy should specify whether all failed dimensions or only the latest failure must be repaired.

### 2. Repairing the latest dimension can hide an older unresolved failure

Sources: `backend/analytics/learner_model/vocabulary_state.py:103` and `backend/analytics/learner_model/bkt/mastery.py:342`.

The practice rule replaces the accumulated failed dimensions with the latest failed dimension. BKT also uses one latent state for the entire word.

An isolated state replay with meaning wrong, context right, pinyin wrong, followed by three correct pinyin practice answers gives `pLearned=0.999708192577706`, practice `COMPLETE`, and review `STRONG`. Meaning evidence still contains one wrong answer and zero correct answers. This replay establishes a limitation of the state policy, not that the ordinary frontend will generate this exact sequence.

If `STRONG` is intended to mean competence across all three dimensions, track unresolved corrective requirements per dimension. If it means a pooled word-level estimate, its presentation and research interpretation should state that scope.

## What code establishes about BKT assumptions

| Assumption or modeling choice | Current implementation | Assessment |
|---|---|---|
| Skill mapping | One state per student and word; meaning, typed pinyin, and context observations update it | Explicit, but pooling these abilities is unvalidated. Format-specific guess/slip does not create separate skill states. |
| Binary latent knowledge | Learned/unlearned state with binary outcomes | Correctly implemented as a model; adequacy for partial vocabulary knowledge requires data. |
| Markov state and conditional observation independence | Replay summarizes previous evidence in current mastery | Exposure deduplication reduces duplicate evidence, but does not establish independence of distinct practices or eliminate item memorization. |
| Stationary learning transition | Default `P(T)=0.15` after every accepted observation | No activity-specific transition in production replay. Whether diagnostic, corrective practice, and maintenance have comparable learning opportunities is unvalidated. |
| Stable emission parameters | MCQ guess/slip `.20/.10`; typed `.05/.15` | Valid probabilities and positive discrimination are enforced. Their values and stability across items, students, and activities are unvalidated. |
| No forgetting | No time-dependent learned-to-unlearned transition | A wrong response can lower the inferred mastery; elapsed time alone cannot. SRS scheduling does not add forgetting to BKT. |
| Mastery decision | Threshold `.95`, minimum observations `3`, diagnostic coverage gate, plus corrective completion policy | Project policy, not a statistical certificate that assumptions pass. |

Sources: `backend/analytics/learner_model/bkt/core.py`, `mastery.py`, `vocabulary_state.py`.

`P(Learned)` and next-answer probability must be distinguished. With the default MCQ rates:

```text
P(correct next) = P(Learned) * 0.90 + (1 - P(Learned)) * 0.20
P(Learned) = 0.95 gives P(correct next) = 0.865
```

Three successful diagnostic answers in meaning, pinyin, context produce default `P(Learned)=0.9937862825198882`; the next MCQ prediction is approximately `0.8956503977639217`. A high latent probability therefore should not be described as the same percentage chance of answering correctly.

## Supporting algorithms and existing calibration code

- Modified SM-2 (`srs.py`, `srs_store.py`): binary grades are mapped to `q=4` for correct and `q=2` for incorrect. Newly official `STRONG` words are enrolled. Existing schedules advance only for due maintenance reviews with the elapsed-time guard; corrective practice does not advance them. This corrects the older snapshot's description of fast-response grading and early weak-practice advancement. Interval choices remain an uncalibrated scheduling policy.
- Review queue (`review_queue.py`): merges due words with selected weak words, labels the reason, and prevents duplicates. This is queue composition, not evidence of BKT validity.
- Personalized selection (`quizGeneration.ts`): a heuristic using failed/seen question types, not an IRT selection model. Finding 1 concerns this active path.
- PFA and the admin pilot BKT (`knowledge_tracing.py`, `knowledge_analytics_service.py`): predictions are made before applying the current outcome. PFA uses pooled intercept/success/failure coefficients. The admin BKT uses one guess/slip pair, unlike production's format-aware variant. Its metrics must not be presented as validation of the production configuration.
- Rasch (`backend/analytics/irt.py`): MAP joint estimation of student ability and item difficulty; it is not the active weak-word selector identified in this review. The fit function does not return convergence diagnostics, uncertainty, or assumption checks.
- Accuracy/time analysis (`backend/analytics/joint_time.py`): fits accuracy and response-time effects separately and then computes an ability/speed correlation. This is not a jointly estimated hierarchical speed-accuracy model.
- Placement initialization (`bkt/placement_prior.py`): chapter accuracy is shrunk toward the global prior and used for untested words; directly tested words use their own observations with the global prior. The mapping from accuracy to latent prior is a heuristic, not calibrated latent mastery.
- Calibration infrastructure exists (`bkt/format_aware_fit.py`, `calibration_store.py`, `deployment.py`). It includes student-grouped five-fold evaluation, parameter identifiability warnings, and explicit deployment. Having this code does not imply a pilot fit has run. Production can load a deployed model; this review did not query that registry.

These are targeted assessments of the vocabulary/adaptive path, not a complete review of speech scoring or every algorithm in the repository.

## Verification

Existing pure tests were run with `--noconftest`, `PYTHONDONTWRITEBYTECODE=1`, and pytest's cache provider disabled. Repository conftest otherwise connects to and truncates a test database, so it was deliberately excluded from this read-only data review.

- BKT arithmetic/integrity, SRS, review queue, vocabulary state: **70 passed, 2 deselected**. The two deselected tests require database fixtures. The initial run reported missing fixtures for those two tests; the filtered rerun passed.
- Knowledge tracing, legacy calibration, format-aware fitting: **32 passed**. These validate implementation and synthetic fitting behavior, not the 40-student pilot.
- Two in-memory replays reproduced findings 1 and 2. No learner data or serving configuration was changed.

Total: **102 selected tests passed**; database integration tests and frontend browser flows were not run. Source findings were checked against current files rather than the older `adaptive_system_snapshot.json`.

## Next evaluation with the existing pilot

First resolve the selection/completion policy. Then audit response provenance, counts and sequence lengths per student-word, correct/incorrect balance, formats, activity types, and time gaps. Evaluate the exact serving model using predictions before each update and student-grouped validation; report log loss, Brier score, and calibration against a simple baseline. With 40 students, folds and uncertainty should be reported at the student level, not treating all responses as independent learners.

Compare the pooled model with dimension-specific alternatives and inspect errors by dimension, item, activity, and time gap. Correct-answer calibration is observable; latent mastery is not directly observed. Verify `STRONG` using fresh items and delayed probes. Neither parameter fitting nor good aggregate prediction alone proves every structural assumption.

References: [Corbett and Anderson's original knowledge tracing paper](https://perso.liris.cnrs.fr/pierre-antoine.champin/2014/m2iade-ia2/_static/893CorbettAnderson1995.pdf); [pyBKT authors' implementation and model variants](https://github.com/CAHLR/pyBKT).
