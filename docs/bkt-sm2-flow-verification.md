# BKT and modified SM-2 verification

Verified 2026-10-02 (Asia/Taipei), against code baseline `ebf7c085` and local
developer schema 0062. This review distinguishes implementation correctness,
model assumptions and evidence of retention. No model was fitted, activated,
deactivated or changed by this review. Developer-database queries used a
repeatable-read transaction with `READ ONLY`; API regression tests used the
separate `mandarin_test` database.

## Outcome

The tested BKT, dimension-repair and SM-2 integration behaves consistently with
the implemented policy. This supports using it for an operational pilot.
It does not establish that BKT's learning assumptions describe human learners,
that the 0.95 mastery cutoff is calibrated, or that the review intervals
achieve a measured retention target.

The current 40-account dataset has not exercised the entire production flow:
its 4,480 ledger rows are diagnostic observations, with no corrective-practice
or scheduled-maintenance responses and no SM-2 schedules for those accounts.
Across their observed lessons, no lesson diagnostic is complete under the
current requirement of one complete run covering every lesson word in each
of three rounds. Observations of a subset of lesson words do not unlock formal
corrective practice. This is why these accounts currently produce provisional
word classifications rather than an enrolled maintenance queue.

## What was verified

| Behavior | Evidence and result |
| --- | --- |
| Correctness comes from published assessment facts | Resolver tests reject unknown/stale items and ignore client-supplied grades or dimensions. |
| BKT observation update | Bayes observation update followed by learning transition; typed and MCQ responses use distinct guess/slip pairs. Golden vectors, replay and active-deployment tests pass. |
| Diagnostic completion | Partial runs and duplicate word exposures do not unlock practice; one complete retry can complete a round. |
| Corrective practice | Every failed dimension remains unresolved until two consecutive correct corrective answers in that dimension. Other-dimension, diagnostic and maintenance successes do not repair it. |
| STRONG gate | Requires complete lesson diagnostic, observed meaning/pinyin/context, sufficient observations, no unresolved dimension and `P(Learned) >= 0.95`. |
| First SM-2 enrollment | A newly STRONG word receives one schedule with interval 1 day; existing schedules are not overwritten by corrective practice. |
| Maintenance update | Only due, authoritatively graded maintenance updates an existing schedule. A full scheduling day must have elapsed. |
| Retention lapse | A due incorrect answer updates BKT, reopens its dimension and resets the schedule to 1 day with reduced ease. |
| Repair after a lapse | Two same-dimension corrective successes restore the STRONG gate when BKT permits; they leave the existing due date, interval, ease and repetition count unchanged. |
| Retry safety | Stable response identities and transaction-scoped learner locks prevent duplicate BKT observations and duplicate SRS transitions. Replaying an old lapse does not reopen a subsequently repaired dimension. |
| Queue composition | Due maintenance and weak corrective words are combined without duplicate word IDs; a weak word wins deduplication and is routed to corrective practice. |

Production implementation locations: `backend/services/vocab_quiz_attempt_service.py`,
`backend/analytics/learner_model/bkt/{core,mastery,deployment}.py`,
`backend/analytics/learner_model/{vocabulary_state,srs,srs_store,review_queue}.py`,
and `frontend/src/entities/vocabulary/quizGeneration.ts`.

## Active model and developer evidence

The earlier statement that no calibration exists was too broad. The local
registry already contains a synthetic fit created on 2026-09-28 and activated
that day: `bkt-synthetic-candidate-20260928T012541Z-36b68139`. It serves the
developer database's default BKT path. The code constants are fallback values,
not the currently active fitted parameters.

| Parameter | Active value |
| --- | ---: |
| Initial mastery | 0.261835 |
| Learning transition | 0.131310 |
| MCQ guess / slip | 0.257520 / 0.089203 |
| Typed guess / slip | 0.045928 / 0.152189 |
| Mastery cutoff / minimum observations | 0.95 / 3 |

This fit records 4,480 responses, 40 accounts and 28 concepts, with metadata
for five folds grouped by student and predictions before outcome updates.
Its stored candidate metrics are AUC 0.7213, Brier 0.2091, log loss 0.6046 and
calibration error 0.0193. These are historical synthetic-fit metrics, not
freshly recomputed human validation. `promotable=false`; local synthetic
activation is supported by an explicit development override.

Read-only checks found:

- All 1,164 stored mastery rows matched current full-ledger replay, including
  probabilities, observation/outcome counts and parameter fingerprint. No
  missing or extra mastery rows were found for existing students.
- No duplicate student/quiz/response slots and no missing UTC timestamps,
  fingerprints, activity types or knowledge dimensions in the 4,670-row ledger.
- Evidence labels comprise 4,494 synthetic rows across 41 identities, including
  test tooling, and 176 real-labelled rows belonging to one identity. A real
  label alone does not establish who generated those answers.
- The 40-account cohort contributes exactly 4,480 diagnostic rows. Its
  observed word projections remain provisional; its SM-2 schedule count is 0.
- Across the whole database, the SRS event history contains 3 enrollments and
  no maintenance successes or failures. Existing data therefore cannot show
  measured delayed retention or interval effectiveness.
- The local environment uses `APP_ENV=development` and `SRS_DAY_SECONDS=86400`.
  Production routes ignore development clock overrides and day compression.
- All 218 word/lesson pairs in the 12 currently published stories have bank
  items covering meaning, pinyin and context; no missing dimension was found.

## BKT assumptions: implementation versus validation

The reference model is [Corbett and Anderson (1995)](https://perso.liris.cnrs.fr/pierre-antoine.champin/2014/m2iade-ia2/_static/893CorbettAnderson1995.pdf).
The implementation uses a format-aware extension with pooled word-level
states and optional chapter placement priors.

| Modeling requirement or assumption | Current assessment |
| --- | --- |
| Binary outcomes for a mapped knowledge component | Implemented: each authoritative response maps to a word and correct/incorrect. The grading and routing contract is tested. |
| Valid probability parameters and informative emissions | Implemented: finite probabilities and `1-slip > guess` are enforced for both formats. Active parameters satisfy the constraints. This is a mathematical check, not human parameter validation. |
| One latent learned/unlearned state is adequate for a word | Unverified: meaning, pinyin and context share one probability. Dimension-repair gates stop some false completion cases but do not turn this into three independently estimated skills. |
| Observation dependence is explained by the modeled state and format | Unverified: repeated published items and consecutive immediate successes can reflect answer memory, feedback or task-specific competence. A learner lock and response deduplication do not establish statistical independence. |
| Stable learning and guess/slip rates adequately describe the population | Unverified: rates are pooled across learners/items, with two emission formats. Item difficulty, learner differences and parameter stability have not been established on human responses. |
| No learned-to-unlearned transition between observations | Implemented as a model choice, but unverified for vocabulary across long delays. Wrong answers can still lower the posterior; merely waiting does not decay `P(Learned)`. |
| Placement-derived priors transfer to untested chapter words | Implemented with shrinkage and tested for provenance/coverage; predictive validity of that transfer remains unverified on human data. |
| The mastery decision predicts future competence | Unverified: 0.95, three observations and two repair successes are application policies, not measured delayed-retention guarantees. |

`P(Learned)` is distinct from the probability of answering the next item
correctly. The latter is `p*(1-slip) + (1-p)*guess`. At `p=0.95`, the active
model predicts about 0.878 correctness for MCQ and 0.808 for typed responses,
not 0.95 for both. STRONG must therefore retain its meaning as a system
classification rather than certainty of performance.

## SM-2 and the combination

The schedule follows the main interval/ease mechanism in
[Woźniak's SM-2 description](https://www.super-memory.org/archive/english/ol/sm2.htm):
initial ease 2.5, minimum ease 1.3, early intervals 1 and 6 days, and subsequent
intervals scaled by ease. The implementation is explicitly modified: binary
correct/incorrect maps to quality 4/2, interval multiplication uses `round`
rather than the reference's upward rounding, STRONG acquisition creates the
first interval, and same-session corrective repetitions do not advance the
schedule. Failures lower ease; quality-4 successes leave ease unchanged, so
ease can decrease but cannot recover through the binary UI's successes.

BKT and SM-2 do not conflict in their tested responsibilities: BKT/repair
chooses what needs attention, and SM-2 tracks when previously acquired words
are due. Both consume the same authoritative outcome for different purposes;
the outcome is inserted into BKT once. SM-2 due dates do not constitute a
forgetting term in the BKT probability, and neither algorithm proves that the
other's assumptions hold. One SRS schedule per word and rotating dimensions
also do not measure delayed retention of every dimension separately.

The frontend now fails explicitly if a word lacks a published item in the
server's targeted dimension, including an empty bank. It shows an error before
starting the round or recording a started event; it never substitutes an
unrelated item. Regression tests cover this failure and a subsequent valid
practice attempt. The read-only content audit found no incomplete bank in the
current 12 lessons.

## Regression verification

218 existing backend tests passed across BKT, deployment, eligibility,
dimension correction, placement, quiz persistence, queue composition,
SM-2, reset behavior and removal migration. An additional API regression,
`test_due_failure_reopens_repair_without_practice_postponing_sm2`, passed
after adding deterministic development-clock settings to its fixture.
The 16 pre-existing API tests also passed when run with the new test.
Total distinct passing backend tests: 219. The new-test fixture
uses a replaced immutable route-settings object, leaving production settings
unchanged after the test.

73 frontend tests passed across seven files covering quiz selection, the
server dimension bridge, answer persistence, review refresh, clock forwarding
and lesson progression. No production logic or pilot evidence was changed.

To extend the operational pilot to the complete loop, complete all three
full-lesson diagnostic rounds for a pilot account, perform corrective answers
in each requested dimension, and record actual due maintenance responses.
To validate the learner model separately, evaluate human response predictions
before updates with learner-level holdouts, inspect dependence and subgroup
misfit, and measure delayed recall by dimension and elapsed time. Existing
synthetic fit metrics and passing application tests do not substitute for
those measurements.

## Fit provenance in reporting

Learning Engine, the Algorithm Verifier, live BKT verification, debug replay,
and pilot analytics now identify the registered active fit with its model version
and evidence origin. The current local fit is **SYNTHETIC FIT**: simulation only,
not human pilot calibration. This label comes from the model registry rather
than the account or the response trace being viewed.

JSON model reports expose `fitProvenance`; copied live traces retain that field.
Pilot analytics reports expose the active fit as `servingBktFit`, separately from
the exploratory real-evidence PFA/BKT comparison. Candidate previews report the
selected candidate's provenance without describing it as deployed. Calculator
reports also flag `parametersOverridden` when inputs change the selected fit's
transition or observation parameters. Engineering defaults and unavailable fit
provenance are labelled explicitly and do not imply human calibration.
