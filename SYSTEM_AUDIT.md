# Current Adaptive Vocabulary System Audit

Audit date: 2026-09-17. This is a read-only audit of the current working tree and the running `docker-compose.dev.yml` stack. No learning algorithm or application code was changed.

## 1. System overview

The student vocabulary system is a layered, lesson-scoped practice loop:

1. A published lesson supplies vocabulary and, when available, an approved assessment bank.
2. The learner plays three diagnostic rounds: meaning, pinyin production, and contextual recall.
3. Each authoritative diagnostic answer is written to a normalized response ledger and replayed into one per-student/per-word probability.
4. After three complete diagnostic rounds over the lesson vocabulary, the service selects a small bottom-ranked weak-word list.
5. Weak words are offered a personalized bank question. The same response also contributes to the word's BKT history and, for `weak_words` activity, to a separate SM-2 schedule.
6. The review queue merges weak words with due scheduled words, preserving different reasons in the payload.

Educationally, the system does produce a useful distinction between “you missed this word” and “this word is due for maintenance,” and it changes practice by word and by failed question type. However, its main mastery estimate is based on only three diagnostic observations, does not decay with time, and is not calibrated against human judgments. The output is therefore best treated as a transparent research prototype, not a validated mastery measure.

Educational logic diagram:

```text
lesson vocabulary -> know meaning -> produce pinyin -> use in context
                         |              |                 |
                         +-------------- response history
                                           |
                              weak words / targeted practice
                                           |
                              later maintenance review
```

Technical logic diagram:

```text
React quiz -> authoritative resolver -> vocab_quiz_responses
                                      -> BKT replay/cache
                                      -> weak-word endpoint
                                      -> personalized weak_words answer
                                      -> BKT replay + SM-2 state
                                      -> combined review queue
```

The running stack was checked through the intended proxy: `:5177/` returned 200, unauthenticated `:5177/api/students` returned 401, and backend readiness at `:8001/health/ready` returned 200. The dev database was queried only through `docker compose -f docker-compose.dev.yml exec db psql -U mandarin -d mandarin`; the unrelated port-5433 Postgres was not used.

## 2. Current learning flow

| Stage | What/data | Decision | Student-visible result | Code evidence |
|---|---|---|---|---|
| Load lesson | Published story, vocabulary, assessment rows | `topicQuizEntries` groups assessment rows by `wordId`; approved bank rows become quiz entries | Vocabulary Quiz opens for a story | `frontend/src/utils/topicQuiz.ts:154`, `topicQuizEntries` |
| Choose round | Three tier modes and current stars | Tier 1 is open; tier 2 requires star 1; tier 3 requires star 2; speaking requires 3 | Ordered tier cards and pass requirements | `frontend/src/utils/quizTiers.ts:26`, `isTierUnlocked`, `practiceUnlocked`; `QuizScreens.tsx:144` |
| Round 1 | One published/basic meaning MCQ per unique lesson word | Server resolves it as `tier1`, `know_it`, `meaning`, `basic_meaning_mcq` | “Know it” meaning recognition | `model.ts:390`, `DIAGNOSTIC_ROUNDS`; `bkt_assessment_resolver.py:_ROUND_FACTS` |
| Round 2 | One typed pinyin item per word | Server resolves it as `tier2`, `say_it`, `pinyin_production`, `character_to_pinyin_typing` | “Say it” pinyin production | `model.ts:390`; `bkt_assessment_resolver.py:_ROUND_FACTS` |
| Round 3 | One context cloze MCQ per word | Server resolves it as `tier3`, `use_it`, `contextual_recall`, `context_cloze_mcq` | “Use it” context recognition, not free Chinese production | `model.ts:390`; `bkt_assessment_resolver.py:_ROUND_FACTS` |
| Answer | Selected answer, correctness, timing, stable item/concept IDs and metadata | Server ignores client grading fields where authoritative published facts exist; pinyin numeric tones are normalized | Immediate correctness feedback; answer is posted incrementally | `useQuizSession.ts:339-438`; `bkt_assessment_resolver.py:101` |
| Persist/rebuild | Cumulative response payload, normalized ledger row | Idempotent slot `(student_id, quiz_id, attempt_order)`; accepted rows rebuild the learner cache | The menu can refresh after an answer | `part_001.py:297`, `bkt_mastery.py:329` |
| Complete attempt | Local attempt summary and parent callback | `StoryRecorderRuntime` calls `createVocabQuizAttempt` on completion; the quiz hook also saves local progress | Summary, star result, next-round action | `useQuizSession.ts:293`; `StoryVocabQuiz.tsx:21`; `StoryRecorderRuntime.js` completion callback `kn` |
| Diagnose | Full-run coverage by mode and word | A diagnostic round is complete only when one run covers every known lesson word exactly once; pass percentage is not required | Server stays locked until all three full runs exist | `bkt_mastery.py:_diagnostic_round_metrics`, `_round_has_complete_run`, `_completed_diagnostic_quizzes` |
| Review | Per-word BKT rows and optional SRS rows | Weak list is selected only after diagnostic unlock; due rows are added separately | Weak words, due review, mastered/on-track words, passive vocabulary list | `part_001.py:130-179`; `review_queue.py:22-75`; `QuizScreens.tsx:18-74` |

The current React flow therefore has two progress concepts: stars are a local/server attempt-history progression gate, while the backend diagnostic unlock is exact full-word coverage. They usually agree after a clean complete lesson, but they are not the same rule.

## 3. Current adaptive pipeline

1. **Question eligibility.** `classify_bkt_response` requires a diagnostic mode, tier level, approved question type/material, stable item and concept identity, binary correctness, diagnostic exposure ID, and no assistance. The resolver in `bkt_assessment_resolver.py` derives the word, answer, round, activity, and correctness from the published bank. Unresolved or legacy rows remain raw audit data but do not become diagnostic BKT evidence.
2. **History assembly.** `_ordered_responses` reads eligible `tier1`/`tier2`/`tier3` rows plus `weak_words` learning rows, ordered chronologically. `_group_response_history` deduplicates eligible diagnostic exposures by `(item_id, diagnostic_exposure_id)`. Replaying the same stable diagnostic item does not create another diagnostic observation; weak-word rows are not in that deduplication branch.
3. **Per-word estimate.** `_mastery_states_from_responses` replays one BKT state for each `word_id`, records observations/correct/incorrect/last response/seen types/failed types/round types, and writes `student_vocab_mastery`.
4. **Completion gate.** `_completed_diagnostic_quizzes` counts complete tier runs, capped at three. It is a coverage condition, not a score condition.
5. **Weak selection.** `get_priority_review_words` requires diagnostics unlocked, `observationCount >= 3`, and `pLearned < .95`, then sorts by `(pLearned, observationCount, lastResponseAt, wordId)` and returns up to five by default.
6. **Immediate interim support.** Before the formal unlock, `useQuizSession.ts:275` exposes any word with an incorrect response and `pLearned < .95`, ordered lowest first. This is explicitly provisional and is not the backend weak-word verdict.
7. **Personalization.** `buildPersonalizedAssessmentQuestions` chooses, per selected word, a bank level associated with a failed diagnostic type first, then an unseen level, then the first available question. It randomizes options but creates one question per selected word.
8. **Scheduling.** `apply_srs_updates` updates SM-2 only for `weak_words` activity, using the last response for each word in the batch. Diagnostic activity changes BKT but not SRS.

## 4. Algorithms currently used

### Production student path

**Format-aware Bayesian Knowledge Tracing (BKT).** This is the active mastery/recommendation model (`backend/analytics/bkt.py:update_bkt`, `replay_bkt_typed`). For current probability `p`, guess `g`, and slip `s`:

```text
correct posterior   = p(1-s) / [p(1-s) + (1-p)g]
incorrect posterior = ps    / [ps    + (1-p)(1-g)]
p_next              = posterior + (1-posterior) * 0.15
```

The value is clamped to `[0.000001, 0.999999]`. Multiple choice uses `g=.20, s=.10`; typed pinyin uses `g=.05, s=.15`. Initial mastery is `.20`. This is a single latent probability despite the three educational dimensions.

**SM-2-style scheduler.** This is active only for `weak_words` reviews (`backend/analytics/srs.py:review`, `srs_store.py:apply_srs_updates`). It does not modify BKT. The UI supplies binary correctness and time, which becomes `q=2` for wrong, `q=5` for correct in `<=5000 ms`, and `q=4` for correct slower than that or with no timing. Ease starts at `2.5`, floors at `1.3`; successful intervals are 1 day, 6 days, then `round(previous_interval * ease)`. Failure resets repetitions and interval to 1 day.

**Simple progression and heuristics.** The star ladder uses pass ratios `.70`, `.82`, `.88` for tiers 1/2/3; tier 3 has a whole-run 150,000 ms cap. `effectiveTierPassCount` is `max(1, ceil(ratio * totalQuestions))`. Stars are contiguous and do not demote. Question construction uses fixed weights for legacy question kinds and seeded/random option shuffles. Local progress separately uses latest attempt presence, current statuses, and localStorage snapshots (`lesson-vocab-progress.ts:190`).

### Present but not active in the student recommendation path

* `weak_words.py:score_weak_words` implements an older/experimental rule using recency decay `.65`, minimum model exposures 2, expected-vs-observed gap `>.15`, time residual `>.35` log units, and a `.15` time bonus. A latest wrong answer is always weak. Static call-site search found no production caller for this function; `/weak-words` uses BKT bottom-K instead.
* `knowledge_tracing.py` contains an admin pilot PFA model: `sigmoid(intercept + .35*successes - .55*failures)` with L2 1.0, plus a separate pilot BKT. `knowledge_analytics.py` serves exploratory admin output and explicitly says it does not change scoring, weak words, gating, or student feedback.
* `irt.py:fit_rasch` is an offline Rasch/1PL fit, `joint_time.py:fit_joint_mode` is an offline response-time fit, and `frex.py:compute_frex` ranks missed words by frequency/exclusivity. These are not used by student weak-word selection.
* `bkt_calibration.py` and `bkt_calibration_store.py` define offline cross-validation/promotion gates but do not promote parameters into `BKT_CONFIG`. The serving defaults remain manual engineering defaults.

## 5. Student × Vocabulary state

The stable key is `wordId`/`conceptId`, normalized where necessary; display text is a fallback for legacy stories (`model.ts:184`, `bkt_mastery.py:33`). The primary persisted state is:

* `vocab_quiz_responses`: immutable-ish normalized response evidence, including word/item/question type, correctness, response time, mode, round, exposure, validation, timestamps, and fingerprint.
* `student_vocab_mastery`: `p_learned`, observation count, correct/incorrect counts, last response/item/type/lesson, model version and parameter fingerprint. A known but unseen word is presented with `p=.20`, zero observations, and `UNASSESSED`.
* `student_vocab_srs`: repetitions, ease, interval in day units, due instant, and last reviewed instant. It is separate from mastery.

An actual live row for demo student `C5-5-1-I2-W002` had 17 stored diagnostic response rows but only three distinct stable diagnostic item/exposure slots, all correct. The API reported `observationCount=3` and `pLearned=0.993786...`; its status was still `UNASSESSED` because the student had not completed full coverage over all 317 required published words. This is a useful example of raw event count versus model observation count.

## 6. Round 1 / Round 2 / Round 3 behavior

The rounds intentionally cover different task demands, but their results are collapsed into one probability per word:

| Round | Bank level | Task | BKT rates | Educational interpretation |
|---|---|---|---|---|
| 1 / `know_it` | easy | meaning MCQ | MCQ `g=.20,s=.10` | recognition of meaning |
| 2 / `say_it` | medium | typed pinyin | typed `g=.05,s=.15` | productive reading/orthography |
| 3 / `use_it` | hard | context cloze MCQ | MCQ `g=.20,s=.10` | contextual recognition |

For C/I/C, the model gives `0.200000 -> 0.600000 -> 0.312766 -> 0.721127`. The typed error causes a sharp fall; the contextual MCQ recovers part of it. The system does not retain separate meaning, pinyin, and context mastery scores. Round 3 is not a free production measure, so “use” is a stronger label than the current evidence supports.

## 7. Weak vocabulary detection

The active formal rule is in `bkt_mastery.py:get_priority_review_words`:

```text
diagnostics unlocked
AND observation_count >= 3
AND p_learned < 0.95
=> eligible weak/review candidate
```

Only the lowest `review_count` candidates are returned; the default is 5. `p=.95` is not weak because the comparison is strict. Two observations are not enough. A candidate can be below `.95` but not selected when it falls outside bottom-K; its status is `DEVELOPING`, while a selected candidate is `NEEDS_REVIEW`. A word at or above `.95` is `MASTERED` after the observation minimum.

Before full diagnostic coverage, the frontend shows a separate provisional list for any word with at least one incorrect answer and `p<.95`. This is useful for immediate action but creates two meanings of “review.” The older `weak_words.py` model would use the latest wrong answer, recency-weighted accuracy, expected ability gap, and time; it is not active and must not be reported as the current rule.

## 8. Personalized practice mechanism

The selected words are ordered server-side and joined back to lesson entries by stable ID. For each word, the frontend selects one approved assessment item:

1. map failed diagnostic question kinds to bank levels;
2. choose a level that was failed;
3. otherwise choose an unseen level;
4. otherwise choose the first bank item;
5. shuffle its options and present one question.

The whole weak list can be practiced, a provisional-miss list can be practiced, a single mastered word can be voluntarily practiced, or due words can be routed into the same `weak_words` mode. There is no explicit retry limit, stopping rule, success criterion, or delayed post-practice test. A weak word can leave the list after one response if its BKT estimate crosses `.95`; for example, a typed correct response moves the C/I/C value `.721127` to approximately `.981094`. That is computationally consistent but educationally thin evidence for durable relearning.

## 9. Time and forgetting behavior

Response time is stored in the ledger but is deliberately absent from BKT. The only diagnostic time limit is the tier 3 whole-run cap of 150 seconds, used for star passing rather than word mastery.

The current BKT has no elapsed-time or forgetting transition. A word's `pLearned` stays constant between responses. Time matters only to SM-2 quality: fast correct `q=5`, slow/no-time correct `q=4`, incorrect `q=2`.

Therefore, days 1/2/4/7/14/30 do not alter BKT merely because they pass. They matter only if a scheduled review is actually graded, or if the learner enters weak-word practice.

## 10. Review scheduling behavior

SM-2 state starts empty. The exact scheduler constants are `INITIAL_EASE=2.5`, `MIN_EASE=1.3`, first interval 1, second interval 6, `PASS_QUALITY=3`, fast cutoff 5000 ms, and a real scheduling day of 86400 seconds.

The queue first puts earliest due SRS words (excluding words already in the weak list), then the existing BKT weak order. Due rows require a positive observed mastery count. The UI labels due rows separately, so a mastered-but-due word is not called weak.

`should_advance` prevents more than one schedule update per full scheduling day, but `apply_srs_updates` does not require `is_due`. A learner who manually practices a weak word before its due instant can therefore advance/reset the schedule early. This is a confirmed implementation behavior, not a proposed interpretation.

## 11. Example student simulations

These values were run against `backend/analytics/bkt.py` with the current defaults. The examples assume three distinct eligible observations and that the diagnostic unlock condition is satisfied for the word/lesson.

| Case | Answers by round | p after each observation | Final status | Weak/priority result | Star/next round |
|---|---|---|---|---|---|
| A | C/C/C | `.600000 -> .967925 -> .993786` | `MASTERED` | not weak | 3 stars; speaking may unlock |
| B | C/I/C | `.600000 -> .312766 -> .721127` | `NEEDS_REVIEW` when selected | weak, rank depends on other words | tier 1 star only; tier 2 must be passed |
| C | I/I/C | `.175758 -> .177686 -> .569045` | `NEEDS_REVIEW` when selected | weak | no star; retry tier 1 |
| D | I/I/I | `.175758 -> .177686 -> .172355` | `NEEDS_REVIEW` when selected | weak, likely high priority | no star; retry tier 1 |
| E | session 1 I/I/C, session 2 C/C/C | `.175758 -> .177686 -> .569045 -> .877556 -> .993080 -> .998686` | `MASTERED` | no weak result at final state | if the second session is three new passed rounds, 3 stars |

Case E is a mathematical six-distinct-exposure simulation. In the actual implementation, repeated eligible diagnostic items with the same stable exposure identity are deduplicated, so a repeated diagnostic session must generate distinct exposure identity to count as new BKT evidence. Weak-word practice rows are non-diagnostic and are not deduplicated by that diagnostic-exposure rule.

The current demo account was not used for write simulations. Live state on the audit date: 14 stories returned; the first published story had 69 assessment rows; aggregate mastery exposed 320 known rows; 317 words were required for the current diagnostic coverage; server response was `unlocked=false`, `completedDiagnosticQuizzes=0`, `sufficientWords=15`; the demo had 287 response rows, 18 completed-attempt rows, and zero SRS rows for that student. The partial runs do not satisfy a full lesson run.

## 12. Student-facing outputs

Meaningful outputs include:

* tier cards with required correct counts and the three round labels;
* immediate answer correctness and end-of-round missed words;
* provisional “Review your misses” before formal diagnostic unlock;
* formal “Weak words” after full coverage, ordered from lowest estimated mastery;
* “Due for review” for scheduled maintenance, separate from weak words;
* mastered/on-track word lists and a lesson vocabulary progress bar;
* personalized questions selected from failed/unseen assessment levels;
* a passive all-vocabulary review list and a mixed lesson challenge.

The UI does not show the numerical BKT probability, the observation count, the guess/slip assumptions, or the distinction between “mastered this round” and model `MASTERED` consistently. Summary copy uses “mastered this round” for round-correct words, while the progress component uses backend status.

## 13. Teacher/researcher outputs

Teacher-facing data includes completed attempt history, tier stars, question results, correct/incorrect counts, timings, and material validation/approval fields. The admin knowledge-model panel exposes exploratory PFA/BKT comparisons and evaluation metrics; `knowledge_analytics.py` gates output on minimum training/evaluation counts and states that the pilot does not change student behavior. The BKT question audit reports material quality/eligibility issues. The FREX endpoint ranks missed words using corpus frequency and student exclusivity. These are useful research/quality outputs, but not all are connected to an instructional decision.

## 14. Potential redundant complexity

* The `.95` threshold is manually mirrored in backend BKT and frontend `useQuizSession.ts`; a future mismatch could change what is shown versus what the server selects.
* Stars, backend diagnostic completion, local lesson progress, BKT `MASTERED`, and SRS due state are parallel progress vocabularies. Each has a valid local purpose, but the combined learner experience can be difficult to explain.
* The old `weak_words.py` model, PFA/BKT pilot, Rasch, joint-time, FREX, and calibration machinery add technical sophistication without currently improving the student weak-word decision.
* The raw JSON attempt table and normalized response ledger are both intentional: the former preserves client-facing completed attempts, while the latter supports replay/idempotency/calibration. This is justified infrastructure, not automatically redundant.
* Question validation, server-authoritative resolution, stable IDs, and exposure deduplication are not educational algorithms, but they protect the validity of educational evidence and should not be removed merely to simplify the model.

## 15. Important implementation assumptions

* A published assessment bank is the authoritative source for diagnostic correctness. Draft, stale, assisted, unknown, or malformed items are excluded from diagnostic BKT.
* A question's `wordId` is the concept identity; display variants are not reliable identity.
* One complete run means one run containing every known published word exactly once per tier. The server counts coverage, not pass ratio, for diagnostic unlock.
* Diagnostic exposure identity is stable by story/mode/item. This intentionally prevents repeated writes of the same exposure from inflating evidence.
* `weak_words` is both the personalized-practice mode and the only student activity that currently advances SRS.
* The dev database was at Alembic revision `0034` during this audit. The working tree contains an un-applied `0035_srs_datetime_precision.py`; the intended datetime widening is not part of the running database snapshot.
* The audit describes current in-flight source files, including BKT/SRS changes already present in the dirty worktree. Those implementation files belong to another session and were deliberately left untouched.

## 16. Potential educational-design problems

1. **Overconfident short evidence.** Three observations can produce `.993786` for C/C/C even though the evidence spans two recognition tasks and one typed task. That is transparent, but not evidence of durable or transferable mastery.
2. **No forgetting.** A learner who does not return retains the same BKT probability indefinitely. The SRS queue can ask for maintenance, but it does not lower the mastery estimate when a review is missed or time passes.
3. **Recognition is called “use.”** The hard round is context cloze MCQ. It may measure contextual recognition, not spontaneous use in a sentence.
4. **Threshold discontinuity.** `p=.950000` is mastered and omitted from weak candidates; `.949999` can be selected. The hard boundary is easy to implement but has no reported human-rater validation.
5. **Coverage lock.** Formal weak-word selection waits for a complete run over all 317 required words. This gives a clean denominator but delays personalized support; the frontend compensates with a separate provisional list.
6. **Practice can end too quickly.** One successful personalized answer can move a word out of the list, and there is no delayed retention check or minimum successful varied evidence.
7. **Scheduling and mastery can disagree.** A word can be model-mastered but due, or model-weak but have its SRS state advanced early by manual practice. The separate labels reduce one kind of confusion but do not resolve the conceptual split.

## 17. Questions that require researcher decisions

1. Is three observations, with one typed and two MCQ tasks, sufficient evidence for a word-level “mastered” claim, or should the research outcome remain dimension-specific?
2. Should “use it” be recognition in context, cloze production, or a sentence-production task? What construct is intended?
3. Is the `.95` threshold a temporary engineering display cutoff or a planned research outcome? If the latter, what external evidence will calibrate it?
4. Should repeated practice with the same published item count as new evidence, and if so how will exposure identity be defined?
5. Should elapsed time lower a mastery estimate, or should time remain exclusively a scheduling concern?
6. Should weak-word practice require varied question types and a delayed successful check before removal?
7. Is the learner-facing distinction between stars, model mastery, weak words, and due review understandable enough for the study population?
8. Which offline outputs (PFA, Rasch, time fit, FREX, calibration) are research outcomes, and which should be removed from the operational system until they support a defined decision?

## HANDOFF SUMMARY

### Current research goal

The current prototype is intended to personalize adult Mandarin vocabulary practice while keeping decisions inspectable. Its operational goal is to identify words that appear least learned after three lesson diagnostic rounds and give those words targeted practice, with a separate maintenance schedule.

### Current learning flow

Published lesson vocabulary is turned into entries by `frontend/src/utils/topicQuiz.ts:topicQuizEntries`. With an approved assessment bank, the learner completes one question per unique word in each of three rounds. `model.ts:buildDiagnosticRoundQuestions` builds meaning MCQ, typed pinyin, and context cloze MCQ items. `useQuizSession.ts:choose` sends accepted answers after each question. `bkt_assessment_resolver.py:resolve_assessment_response` re-derives identity and correctness from the published bank. The normalized response is replayed by `bkt_mastery.py:record_attempt_and_rebuild`. On completion, the parent `StoryRecorderRuntime` also posts the completed attempt.

### Current algorithms

The student-serving mastery model is format-aware BKT. It starts every unseen word at `.20`, uses learn rate `.15`, MCQ guess/slip `.20/.10`, typed guess/slip `.05/.15`, and calls `.95` the mastery threshold. It requires 3 observations and 3 complete diagnostic tiers. The active scheduling model is a separate SM-2-style scheduler: ease `2.5` with floor `1.3`, intervals 1 day, 6 days, then rounded ease-scaled intervals; wrong is quality 2, fast correct (<=5000 ms) quality 5, slow/no-time correct quality 4. Stars are separate heuristics with pass ratios 70%, 82%, and 88%, and tier 3 has a 150-second run cap.

### Input data

Decisions use published word/question identity, selected answer, server-resolved correctness, question type, round, mode, diagnostic exposure, response time, and timestamps. BKT uses correctness and question type, not response time. SRS uses correctness, response time, and time since the previous graded review. Published assessment approval and validation determine whether a diagnostic response is eligible.

### Student × vocabulary state

The ledger stores replayable response evidence. The mastery cache stores probability, observations, correct/incorrect counts, last evidence, and question-type history. The SRS table stores repetitions, ease, interval, due time, and last review. An unobserved known word is `p=.20` and `UNASSESSED`. Eligible diagnostic exposures with the same item/exposure ID are deduplicated; weak-word learning rows are included in replay but are not diagnostic observations.

### Adaptive decision logic

After full coverage, candidates require at least 3 observations and `p<.95`; the bottom five are returned by default. Before unlock, the frontend surfaces any incorrectly answered word with `p<.95` as provisional review. Personalized practice picks a failed level first, then an unseen level, then the first bank item, one item per selected word. A successful response can immediately remove a word from the weak list. SRS due words are unioned with weak words, due-first, but are labeled separately.

### Weak-word definition

The current formal definition is low BKT probability plus minimum evidence, not “wrong last time.” The older recency/ability/time scorer in `weak_words.py` is implemented but has no active production caller. The strict threshold means `.95` is excluded and `.949999` is eligible; only selected bottom-K rows receive `NEEDS_REVIEW`.

### Personalized-practice logic

The learner can review all formal weak words, provisional misses, an individual word, or due words. Approved assessment items are reused, options are shuffled, and responses use stable concept IDs. There is no explicit maximum attempt count, stopping criterion, varied-evidence requirement, or delayed retention test.

### Review/scheduling logic

Only `weak_words` activity updates SM-2. The queue includes due observed words not already in the weak list and then BKT weak words. Manual weak practice can update the schedule once per 86400 seconds even when the scheduled due time has not arrived because `should_advance` checks elapsed time since the last grade rather than `is_due`.

### Treatment of elapsed time

Elapsed time does not change BKT. It only contributes to the 150-second tier 3 star cap and the SRS quality grade. Passing days alone never lowers mastery, so forgetting is not represented in the active mastery state.

### Example outputs

For distinct C/I/C observations, BKT produces `.600000`, `.312766`, `.721127`; the word is weak after unlock. C/C/C produces `.993786` and is mastered. I/I/I produces `.172355` and is weak. IIC followed by CCC produces `.998686` if all six are distinct accepted exposures. A live demo check found partial coverage: 287 response rows, 15 words with sufficient observations, 317 required words, and server lock still on.

### Major educational assumptions

The implementation assumes that three binary observations can estimate a single latent word state, that MCQ guess/slip rates can stand in for item quality, that typed pinyin deserves a different error model, and that targeted re-use of a failed bank level is useful practice. None of the serving defaults are human-rater calibrated.

### Potential problems

The probability can become overconfident quickly; it does not forget; Round 3 does not require production; coverage gating delays final weakness decisions; one personalized correct response can clear a word; and stars, BKT mastery, local progress, and SRS due status can disagree. The codebase also carries inactive alternative models whose educational role is not currently defined.

### Important open questions

Researchers should decide what “use” means, whether mastery should be dimension-specific, how much evidence is enough, whether repeated identical items count, whether forgetting belongs in the model or only the schedule, and what learner-facing terminology should represent the difference between round success, model mastery, weak review, and maintenance due status.

### Plain-language answer: Student A versus Student B

Removing all algorithm names, the system asks the same lesson words in three ways. Student A answers a word correctly in meaning, pinyin, and context, so the word quickly leaves the “needs review” group and the student can progress. Student B answers the meaning correctly, misses the pinyin, and answers the context question correctly. The system treats that word as less secure, records that pinyin was the failed kind, and puts a pinyin-level bank question into targeted practice once the lesson's full diagnostic coverage is complete. If Student B later answers that practice question correctly, the word may leave the weak list immediately. If either student has a word scheduled for maintenance, it can appear in “Due for review” even when it is not currently weak. The difference is therefore practical and concrete—Student B receives more practice on a particular word and failed task—but the system does not yet prove that Student A will retain the word longer, because time passing does not reduce its mastery estimate.
