# Small teacher-validated pilot: implementation

Implementation of the SMALL TEACHER-VALIDATED PILOT architecture, built directly
on the conclusions of `stable_experimental_teacher_validation_audit.md` and
`runtime_scorer_audit.md`. No F1/E2/Candidate E V1 formula changed, no threshold
tuned, `tone_context.py` untouched, `final_test` never accessed, no benchmark or
research implementation deleted, no fake 0–100 teacher/machine common scale
created, no teacher rating pre-filled from a machine value. Every claim below is
backed by a file:line citation to code actually written and tested in this task.
Pilot ratings/participants have **not** been run — see STOP conditions at the end.

## PART 1 — one student mode

`src/components/StoryRecorder.tsx:750-753` computes `isPilotSession` from the
same `?pilot=1` query flag `resolvePilotContext()` already used for research
logging (`src/utils/pilotSession.ts`), and `showAnalysisVersionSelector =
isAdmin || !isPilotSession` (`:754`). This is threaded three ways:

- `analysisVersion` initializes to `"stable_v1"` (never a stored/experimental
  preference) whenever the selector is hidden (`:755-756`, and the
  `studentScope`-change effect at `:765-770` re-applies the same rule on every
  scene/topic change).
- `onAnalysisVersionChange` is passed as `undefined` to `SpeakingFlowCard` when
  hidden (`:2341`), which already only renders `<AnalysisVersionSelector>` when
  that prop is truthy (`SpeakingFlowCard.tsx:266-274` — no change needed there).
- The admin backdoor (login name `"admin"`, `isAdminSession()`, the same
  mechanism that already bypasses every other progression gate in this app —
  see `project_admin_backdoor` precedent) is the ONE way to reach the hidden
  dev/debug view, matching the spec's "hidden developer/admin/debug mechanism."

`AnalysisVersionSelector.tsx` and `routers/analysis_v2.py` are unmodified —
Experimental V2 stays fully intact and reachable by admin, just not offered to
a pilot student. Since `analysisVersion` is forced to `"stable_v1"`, the
Stable-vs-Experimental comparison panel (`SpeakingResultsFlow.tsx:437`, gated on
`analysisVersion === "phoneme_tone_v2"`) is unreachable for a pilot student too.

Tested: `src/components/StoryRecorder.test.tsx`, describe block "pilot mode
hides the Stable/Experimental selector (PART 1)" — 3 tests: selector shown by
default, hidden under `?pilot=1`, still shown for the admin backdoor even under
`?pilot=1`.

## PART 2 — authoritative pilot architecture

Unchanged from the prior audit's finding, re-verified structurally in this task
(`tests/test_pilot_safety.py::test_e2_is_the_only_public_e_family_scorer` and
`::test_e_v1_has_no_independent_production_call_path`, both passing): the only
code path that calls `assistive_feedback.e2_scoring`/`f1_artifact` is
`assistive_feedback/pipeline.py:compute_assistive_feedback`
(`main.py:1704-1713`, `_do_analyze`'s only caller of the assistive layer). No
router and no other request-path module imports Candidate E2/F1 directly.
`routers/analysis_v2.py` still only wraps `chinese_tones.detect_tone`, never
Candidate E V1/E2. The pipeline: `pitch_contour + transcription + pinyin_hint`
→ `tone_context.plan_expected_tones` (frozen, untouched) → F1 risk +
Candidate E2 (`assistive_feedback/pipeline.py:169-178`) → frozen policy
`classify()` (`assistive_feedback/policy.py:78-92`) →
`NO_ISSUE_DETECTED`/`NO_AUTOMATIC_JUDGMENT`/`CHECK_THIS_TONE`
(`STUDENT_FACING_NAME`, `policy.py:24-28`).

## PART 3 — legacy scorer non-interference

`chinese_tones.directional_tone_scores`/`SYLLABLE_PASS_THRESHOLD` are
untouched and still populate `word_prosody[].passed` exactly as before
(`praat_analyzer.py:1095,1123`) — this task changed no scoring formula. What
changed is **what a pilot session's progression gate reads**:

- `StoryRecorder.tsx:1703-1706`: `pilotAssistiveFeedbackActive =
  isPilotSession && Boolean(metrics.assistive_feedback)`, then
  `nextMasteryPassed = pilotAssistiveFeedbackActive ||
  (canScorePronunciation && prosodyGatePassed(metrics.word_prosody))` — a
  pilot attempt with the assistive layer active is ALWAYS `masteryPassed`,
  regardless of the legacy per-syllable verdict.
- `StoryRecorder.tsx:1713-1716` sets the same override into a new
  `pilotSceneReadyOverrideMap`, because `SpeakingFlowCard`'s `ready` gate ANDs
  `masteryPassed` with a SEPARATE legacy signal, `sceneReady(prog)`
  (bestTone≥70 / bestFluency≥65 / attempts≥4 —
  `src/utils/storyRecorderFeedback.ts:114-124`). Forcing `masteryPassed` alone
  would still strand a pilot student behind that second legacy threshold.
  `SpeakingFlowCard.tsx`'s new `sceneReadyOverride` prop
  (`SpeakingFlowCard.tsx:71,121,155-159`) bypasses it the same way.
- Both overrides are `false` — i.e. **zero behavior change** — until
  `metrics.assistive_feedback` is non-null, which itself requires an operator
  to have set `ENABLE_ASSISTIVE_FEEDBACK_PILOT_OVERRIDE=1` server-side
  (`assistive_feedback/pipeline.py:43,49-52`, untouched two-gate design). This
  task does not set that flag anywhere — see STOP conditions.

The bounded-retry flow (`src/utils/retryPolicy.ts`, pre-existing) is wired into
`SpeakingResultsFlow.tsx:996` and was NOT modified by this task; it already
satisfied "CHECK_THIS_TONE → at most one focused retry, then continue" and
"NO_AUTOMATIC_JUDGMENT/NO_ISSUE_DETECTED → continue" — `canAlwaysProgress`
(`retryPolicy.ts:30-32`) returns `true` unconditionally, and `shouldOfferRetry`
(`:21-24`) only ever returns `true` once per attempt. No repeat-until-pass loop
exists anywhere in this flow.

Tested: `StoryRecorder.test.tsx`, describe block "pilot progression policy
overrides legacy passed=false (PARTS 2/3)" — one test proving the unchanged
default behavior (legacy fail still blocks when assistive feedback is
inactive), one proving the override (legacy fail does NOT block when a pilot
session has an active `CHECK_THIS_TONE` syllable, and the optional retry offer
still renders). `src/utils/retryPolicy.test.ts` — 8 tests proving the retry cap
is exactly 1 and progression is never blocked, for any state/retry count.

## PART 4 — system/teacher join

New columns on `audio_records` (migration `0010_audio_records_pilot_identity.py`):
`session_id`, `attempt_id`, `attempt_number`, `attempt_type` — nullable,
non-FK, matching the existing `student_id` convention. `participant_id` is
NOT duplicated: it is `audio_records.student_id` (already existed, migration
0008). Item identity is NOT a new field either: `topic_id` + `image_index`,
combined at read time as `f"{topic_id}:{image_index}"`
(`routers/teacher_review.py:53-56, _item_id`).

Threaded end-to-end from the frontend: `StoryRecorder.tsx:1576-1579` computes
`attemptIdForRequest`/`attemptTypeForRequest` once per analysis and reuses the
SAME values for both the `/api/analyze` research-logging request AND the
`AudioRecord` object passed to `onAddRecord` (`:1651` for the V2/
analytics-only branch, `:1746` for the primary stable path) — previously
these were computed inline for the request only and never reached the saved
recording. `App.tsx`'s `AudioRecord`/`serializeAudioRecord` (`App.tsx:52-75,
520-538`) and `src/services/database.ts`'s `StoredAudioRecord`
(`:58-65`) carry the same four fields through to the JSON body POSTed to the
backend. `main.py`'s `AudioRecordRequest` (`:476-495`) and `save_audio_record`
(`:788-843`) accept and persist them; `database.py:row_to_audio_record`
(`:80-100`) reads them back.

`attempt_type` supports exactly `WHOLE_SENTENCE_INITIAL` / `FOCUSED_RETRY` /
`WHOLE_SENTENCE_FINAL`, matching `assistive_feedback/research_log.py`'s
existing `AttemptType` literal. Known limitation, unchanged from the prior
audit: the UI's "record again" button always produces a new whole-sentence
recording — there is no distinct focused-retry-only recording flow yet, so
`attemptType` is still assigned by the simple, explicit, non-heuristic rule
"attempt 1 = INITIAL, later attempts = FINAL" (`StoryRecorder.tsx:1700-1701`).
`FOCUSED_RETRY` exists as a first-class value or the schema and is exercised by
the PART 17 fixture below, but nothing in the current UI assigns it
automatically yet — a caller (e.g. a future dedicated retry-recording
component) can set it explicitly. This does not affect PART 3's retry-cap
behavior, which is UI-state-driven (`assistiveRetriesUsed`), not
attempt-type-driven.

## PART 5/6 — database join and teacher-rating table

Migration `0011_teacher_pronunciation_ratings.py` creates
`teacher_pronunciation_ratings` with every identity field PART 5/6 require:
`rating_id`, `teacher_id`, `audio_record_id`, `participant_id`, `session_id`,
`item_id`, `attempt_id`, `syllable_index` (nullable — NULL means
sentence-level). Not FK-enforced, matching this repo's existing
`student_id`/`topic_id` convention. The authoritative join chain
`participant → session → item → attempt → audio_record → syllable` is
realized as: `participant_id = audio_records.student_id`; `session_id`/
`attempt_id` copied verbatim from the `audio_records` row at rating-submission
time (`routers/teacher_review.py:274-292` for Stage 1, `:333-350` for Stage 2)
— never re-typed by the caller, so a rating can never carry an
identity field that disagrees with its own audio record's.

## PART 7-9 — Stage 1: blind, independent pronunciation rubric

`routers/teacher_review.py:182-198` (`GET
/api/teacher-review/attempt/{id}/stage1`) returns exactly: `audio_url`,
`script` (transcription), and `targets` — a list built by `_blind_targets`
(`:69-84`), which reads ONLY `syllable_index`, `character`,
`expected_underlying_tone`, `accepted_surface_tones`, `context_rule`,
`realization` off `praat_metrics.assistive_feedback`. It never reads
`assistive_state`, `assistive_state_label`, `assistive_message`,
`e2_diagnostic_category`, `explanation`, or any score, and the endpoint never
touches `word_prosody[].passed`, `analysis_version`, or any legacy field.
Blinding is enforced by the response-builder function itself (an allow-list of
keys copied out), not by hiding fields client-side.

The rubric (`routers/teacher_review.py:229-256`,
`TeacherStage1RatingRequest`): syllable-level `consonant_score`/`vowel_score`/
`tone_score` ∈ {0,1}; sentence-level `accuracy_score`/`fluency_score`/
`prosody_score` ∈ {1..5}. A `model_validator` (`:238-255`) rejects any request
mixing syllable-level and sentence-level fields (verified by
`test_mixed_syllable_and_sentence_fields_rejected`, HTTP 422).

Two independent raters: `POST /ratings/stage1` (`:270-314`) writes a new row
per submission; the unique index `ux_teacher_rating_unique` on
`(teacher_id, attempt_id, COALESCE(syllable_index, -1), rating_stage)`
(migration 0011) lets two different `teacher_id`s rate the identical
attempt/syllable independently while rejecting the SAME teacher submitting
twice (mapped to HTTP 409, `:311-314`) — "never overwrite one teacher's
result with another."

Tested: `tests/test_teacher_review.py` — 10 tests covering blinding,
independent two-teacher rating, duplicate rejection, and sentence/syllable
distinctness. `tests/test_pilot_safety.py::test_teacher_rating_is_never_prefilled_from_machine_values`
proves a teacher's tone_score is stored exactly as submitted even when it
disagrees with the system's own `CHECK_THIS_TONE` verdict for the same
syllable.

## PART 10 — Stage 2: pedagogical feedback validation

`GET /api/teacher-review/attempt/{id}/stage2` (`routers/teacher_review.py:201-224`)
403s unless the REQUESTING teacher already has a `stage_1_blind` row for this
`attempt_id` (`_has_rating`, `:120-130`) — checked per-teacher, so Teacher B
cannot ride in on Teacher A's Stage-1 submission. Once unlocked, it returns
`script`, `pitch_contour` (F0 visualization data), and `system_output`
(`_system_output`, `:87-112`) — the same target fields as Stage 1 PLUS
`e2_diagnostic_category`, `explanation`, `assistive_state`,
`assistive_state_label`, `assistive_message` (the actual learner-facing
feedback). Deliberately still omits raw F1 probability and raw E2 continuous
score — PART 10 authorizes "E2 explanation" (categorical + rationale), not the
numeric machine opinion, to avoid anchoring the teacher's judgment on a raw
number; those raw values remain available for later statistical work only
through `assistive_feedback/research_log.py`, never through this endpoint.

`POST /ratings/stage2` (`:317-360`, `TeacherStage2RatingRequest`) takes
exactly the two PART 10 questions: `retry_recommended: bool` ("Would you ask
this learner to retry this syllable?") and `feedback_appropriateness:
APPROPRIATE | PARTIALLY_APPROPRIATE | INAPPROPRIATE`. It 403s under the same
per-teacher Stage-1-first check as the GET, and is stored as `rating_stage =
"stage_2_feedback_review"` — a separate row from Stage 1, never an update to
it, so both remain independently queryable (satisfying PART 12's human-human
and machine-human analyses needing Stage 1 and Stage 2 as distinct records).

Tested: `test_teacher_review.py::test_stage2_locked_until_stage1_submitted`
(locked for a fresh teacher, unlocked after that teacher's own Stage 1, still
locked for a DIFFERENT teacher who hasn't done Stage 1).

## PART 11 — no forced common scale

No code anywhere in this task converts a teacher 0/1 or 1-5 value to/from an
F1 probability, E2 score, or legacy 0-100 score, or vice versa. The Stage-1
rubric fields (`consonant_score`/`vowel_score`/`tone_score`/`accuracy_score`/
`fluency_score`/`prosody_score`) and the system fields (`assistive_state`,
`e2_diagnostic_category`, raw F1/E2 in the research log) are stored in
entirely separate columns/files, in their native units, joined only by ID
fields (participant/session/item/attempt/syllable) — never by a shared
numeric scale.

## PART 12 — data stored for later validity analysis

- **(A) Human-human reliability**: `teacher_pronunciation_ratings` stores
  every teacher's Stage-1 row independently (unique per `teacher_id` ×
  `attempt_id` × `syllable_index` × `rating_stage`) — a query filtering
  `rating_stage = 'stage_1_blind'` and grouping by `(attempt_id,
  syllable_index)` yields every rater pair's `tone_score`/`consonant_score`/
  `vowel_score` (Cohen's kappa input) or `accuracy_score`/`fluency_score`/
  `prosody_score` (weighted-kappa/ICC input) — demonstrated directly by
  `test_pilot_e2e_fixture.py`'s T01-vs-T02 assertions.
- **(B) Machine-human validity**: `assistive_feedback/research_log.py`
  (untouched) already stores `f1_risk_score`, `e2_score`, `policy_state` per
  `(attempt_id, syllable_index)`. `teacher_pronunciation_ratings` stores the
  human `tone_score` and Stage-2 `retry_recommended` for the SAME
  `(attempt_id, syllable_index)`. `test_pilot_safety.py::test_attempt_id_links_research_log_audio_record_and_teacher_rating`
  proves these two independently-written stores resolve to the same
  participant/session/item when queried by the shared `attempt_id`.
- **(C) Feedback appropriateness**: `assistive_message` (the actual text shown
  to the learner) is reachable via Stage 2's `system_output`; the teacher's
  judgment of it is `feedback_appropriateness`, stored on the SAME
  `attempt_id`/`syllable_index` as the Stage-1 rubric row for that syllable.

No statistic is computed anywhere in this implementation — only storage is
guaranteed, per the task's explicit instruction.

## PART 13 — future metrics (documented, not computed)

Recorded here for the study-design record; none of these run in this task:

- **Human-human**: binary (consonant/vowel/tone) → Cohen's kappa; sentence
  1-5 (accuracy/fluency/prosody) → weighted kappa and/or ICC.
- **System-vs-human tone**: F1 continuous risk vs. teacher tone
  acceptability → ROC AUC; at the frozen policy cutoff → sensitivity/
  specificity/false-rejection-rate/false-acceptance-rate.
- **Assistive policy**: `CHECK_THIS_TONE` → proportion of teachers who
  independently recommend a retry (over-warning rate = teachers who say NO);
  `NO_ISSUE_DETECTED` → proportion of teachers who nevertheless recommend a
  retry (missed-feedback rate); `NO_AUTOMATIC_JUDGMENT` → abstention
  coverage and the distribution of teacher outcomes for that abstained case.
- **Feedback**: the %APPROPRIATE / %PARTIALLY_APPROPRIATE / %INAPPROPRIATE
  breakdown of `feedback_appropriateness`.

No success threshold is selected for any of these here.

## PART 14 — teacher review queue

`GET /api/teacher-review/queue?teacher_id=...`
(`routers/teacher_review.py:127-179`) returns, per attempt with pilot
identity: `audio_record_id`, `participant_id` (already an opaque roster UUID
generated by `uuid.uuid4()` at signup, `routers/students.py:37` — pseudonymous
by construction, never a name), `item_id`, `session_id`, `attempt_id`,
`attempt_number`, `attempt_type`, `review_status` ∈
`NOT_STARTED`/`STAGE_1_COMPLETE`/`STAGE_2_COMPLETE` (computed per-teacher from
two `EXISTS` subqueries, `:150-163`). No system-prediction field is ever
included in this response — verified by
`test_teacher_review.py::test_review_queue_hides_system_prediction_before_stage1`,
which asserts the exact key set of a queue row.

## PART 15 — teacher identity provenance

`teacher_id` is the signed-in teacher's freely-typed `session.name`
(`src/utils/session.ts:15-22`) — the SAME identity every other teacher-facing
feature in this app already uses. This codebase has no teacher password and no
`teachers` table (confirmed by the prior audit; the role-separation design is
UI-only by deliberate choice). No new table or auth mechanism was added. This
is a real, named limitation: `teacher_id` is self-declared, not
cryptographically authenticated — sufficient to keep two teachers' independent
ratings apart (PART 9's actual requirement) but not to prove WHO physically
typed a given rating. Documented in `routers/teacher_review.py`'s module
docstring (`:1-27`) as well as here.

## PART 16 — pilot student UI

Unchanged from the pre-existing `assistive_feedback/policy.py`
(`STUDENT_FACING_NAME`/`STUDENT_FACING_MESSAGE`, `:24-33`, built in an earlier
phase, not touched by this task): `CHECK_THIS_TONE` → "This tone may be worth
checking."; never "wrong"/"failed"/"incorrect". PART 1's selector-hiding work
above ensures the ONLY practice mode a pilot student can reach is "Speaking
Practice" — no Stable/Experimental/V1/V2/F1/E2/probability/research label is
newly exposed by anything in this task.

## PART 17 — end-to-end validation fixture

`tests/test_pilot_e2e_fixture.py::test_full_pilot_fixture_joins_by_id_fields_only`
builds exactly the named fixture — Participant `P001`, Session `S001`, Item
`ITEM001` (realized as `topicId="ITEM001", imageIndex=0` →
`item_id="ITEM001:0"`, per PART 5's "reuse existing identity" rule), Attempt
`A001`/AudioRecord `R001` with a `CHECK_THIS_TONE` system output, Teacher `T01`
and `T02` each submitting Stage 1 (syllable + sentence) and Stage 2, then
Attempt `A002` (`FOCUSED_RETRY`)/AudioRecord `R002` with its own Stage-1
rating — then queries `audio_records` and `teacher_pronunciation_ratings`
directly by `attempt_id` (never `created_at`) and asserts: both attempts'
audio rows carry the same participant/session/item; A001 carries exactly the 6
expected teacher rows with the two teachers' independent (and, for
`tone_score`, disagreeing) judgments both preserved; A002 carries exactly its
own 1 row, distinct from A001's; the review queue reconstructs correct
per-teacher status for both attempts from IDs alone. Passing.

## PART 18 — safety tests

All 12 implemented and passing; see the enumerated list with citations to the
concrete test file/test name for each item at the top of
`tests/test_pilot_safety.py`, repeated here:

1. Pilot student sees only Speaking Practice — `StoryRecorder.test.tsx`.
2. Stable/Experimental hidden from pilot UI — `StoryRecorder.test.tsx`.
3. Candidate E2 is the only public E-family scorer —
   `test_pilot_safety.py::test_e2_is_the_only_public_e_family_scorer`.
4. Candidate E V1 has no independent production path —
   `test_pilot_safety.py::test_e_v1_has_no_independent_production_call_path`.
5. Legacy FAIL cannot block pilot progression — `StoryRecorder.test.tsx`.
6. `CHECK_THIS_TONE` cannot cause endless retries — `retryPolicy.test.ts`.
7. Stage-1 API contains no system judgments —
   `test_teacher_review.py::test_stage1_view_excludes_all_system_judgment_fields`.
8. Stage 2 locked until Stage 1 submitted —
   `test_teacher_review.py::test_stage2_locked_until_stage1_submitted`.
9. Two teachers rate independently —
   `test_teacher_review.py::test_two_teachers_rate_independently_without_overwriting`.
10. Ratings never prefilled from machine values —
    `test_pilot_safety.py::test_teacher_rating_is_never_prefilled_from_machine_values`.
11. Sentence/syllable ratings stay distinct —
    `test_teacher_review.py::test_sentence_and_syllable_level_ratings_stay_distinct`,
    `::test_mixed_syllable_and_sentence_fields_rejected`.
12. `attempt_id` deterministically links research log/audio_record/system
    output/teacher rating —
    `test_pilot_safety.py::test_attempt_id_links_research_log_audio_record_and_teacher_rating`.

## Verification run for this task

- Backend: `python -m pytest` — new files `test_teacher_review.py` (10),
  `test_pilot_e2e_fixture.py` (1), `test_pilot_safety.py` (4); pre-existing
  suite unaffected (`test_audio_and_submissions_db.py` re-verified passing
  after the `audio_records`/`teacher_pronunciation_ratings` schema and
  `database.py`/`main.py` changes).
- Frontend: `npx tsc --noEmit` clean; `npx vitest run` — `StoryRecorder.test.tsx`
  (45, includes the 5 new PART 1/2/3 tests), `retryPolicy.test.ts` (8, new),
  `StoryRecorder.gates.test.tsx` and `SpeakingFlowCard.modelRecording.test.tsx`
  (pre-existing, re-verified passing after `SpeakingFlowCard`'s new
  `sceneReadyOverride` prop).
- F1/E2/Candidate E V1/`tone_context.py`: not edited by this task (no Edit/Write
  tool call touched `assistive_feedback/f1_artifact.py`,
  `assistive_feedback/e2_scoring.py`, `pronunciation/wav2vec_tone/`, or
  `tone_context.py`; confirmed by the structural import-guard tests in PART 2
  above, which would fail if a new caller had been introduced).

## STOP conditions honored

No teacher rating was run. No participant was run. No validity statistic was
computed. `ENABLE_ASSISTIVE_FEEDBACK_PILOT_OVERRIDE` was not set anywhere by
this task — the pilot progression override (PART 3) is fully implemented and
tested but stays inert in the live app until an operator deliberately sets
that flag, exactly matching this task's own architecture note in
`assistive_feedback/pipeline.py`.

---

```
STUDENT-FACING MODE:
Speaking Practice only

PUBLIC DIAGNOSTIC SCORER:
Candidate E2

F1 ROLE:
Pronunciation-risk signal

TEACHER RUBRIC ROLE:
Independent human pronunciation reference

DO TEACHER AND SYSTEM USE THE SAME RAW SCALE:
NO

HOW ARE THEY SYNCHRONIZED:
Same participant/session/item/attempt/audio/syllable + construct-level mapping

IS STAGE-1 HUMAN RATING BLINDED:
YES

CAN TWO TEACHERS RATE INDEPENDENTLY:
YES

CAN HUMAN-HUMAN RELIABILITY BE COMPUTED:
YES

CAN SYSTEM-HUMAN VALIDITY BE COMPUTED:
YES

CAN FEEDBACK APPROPRIATENESS BE EVALUATED:
YES

READY FOR SMALL TEACHER-VALIDATED PILOT:
NO

If NO:
list only remaining concrete blockers.

- `ENABLE_ASSISTIVE_FEEDBACK_PILOT_OVERRIDE` has never been set in any real
  deployment — the pilot progression policy (PART 3) has zero live traffic
  history; it is implemented and unit/integration-tested against synthetic
  fixtures only.
- No teacher-facing UI exists yet for the Stage 1/Stage 2 endpoints — only
  the API layer was built this task. A teacher today would have to call
  `/api/teacher-review/*` directly (e.g. via a REST client); there is no
  page in `teacher.html`/`TeacherShell` wired to it.
- `teacher_id` is a self-declared, unauthenticated free-typed name (PART 15)
  — acceptable for keeping two raters' data apart, but worth a conscious
  go/no-go decision before real teachers rate real students with it.
- No real teacher has been recruited, briefed on the Stage-1/Stage-2 rubric,
  or piloted the flow on a single real recording end-to-end through an
  actual browser session — every test in this task runs against synthetic
  fixtures or the FastAPI TestClient, not a human clicking through a UI.
- The `FOCUSED_RETRY` attempt-type has no dedicated recording flow in the
  UI yet (PART 4's known limitation) — the schema and rating APIs fully
  support it, but a real focused-retry attempt cannot currently be produced
  by a student's own actions, only by direct API calls (as the PART 17
  fixture does).
```
