# Canonical Content Migration — Dependency Audit

**Status:** audit only (migration order step 1). No schema or runtime behavior has been
changed by this document. Written against `ui/student-mode-speaking-refresh` at commit
`6e9333d` (working tree clean at audit time).

## 0. What's already true before this audit — don't rebuild these

Significant consolidation work already landed on this branch, ahead of and independent of
this document. Verified by reading the actual code (not assumed):

- **`custom_stories.vocab_assessment` is already the sole canonical quiz/vocabulary bank**
  for modern content. `topicQuizEntries()` (frontend) and every backend BKT/mastery path
  read only from it. No code path anywhere still reads the old per-frame
  `vocabularyDistractors`/`vocabularyCloze`/`vocabularySynonym` fields — migration
  `0050_retire_legacy_quiz_material` dropped `quiz_exclusions`, `quiz_material_snapshot`,
  `quiz_approved_snapshot`, `quiz_pending_approvals` from `custom_stories` and stripped those
  three keys out of every `frames[]` entry. The Quiz Review pipeline built on those columns
  (`story_quiz_materials.py`, `story_quiz_pools.py`, most of `quiz_review.py`) is deleted, not
  just hidden.
- **The R1/R2/R3 = Know It/Say It/Use It round contract is enforced on the write path**, not
  just the read path. Fixed earlier this session (`de3a363`): Admin's quiz-vocabulary
  CRUD (`backend/routers/story_quiz_vocabulary.py`) used to silently rewrite Say It into an
  MCQ and Use It into free-text recall on every save. It now derives `questionType`/
  `answerFormat` from `CURRENT_QUESTION_TYPE_BY_LEVEL`/`CURRENT_ANSWER_FORMAT_BY_LEVEL`
  (`backend/domain/vocabulary/assessment.py`), matching what the live student quiz
  (`DIAGNOSTIC_ROUNDS`) and `import_question_bank_workbook.py` already assumed.
- **The former read-only content inventory diagnostic has been removed**. Content ownership
  and import validation now live in the Admin Content Bank and its canonical vocabulary,
  question, and audio workflows; no separate diagnostic route or CLI is maintained.
- **`backend/services/ai_feedback.py` is already a compatibility alias**, not a second
  implementation — it replaces its own module object in `sys.modules` with
  `services.speech.feedback.pipeline` at import time, so the two names are the same module.
  Section 22/31's concern (don't create a second AI feedback service) is already satisfied.
- **Production BKT/SRS and research BKT/SRS are already fully separated**, confirmed by
  direct grep, not by docstring claims alone: `student_vocab_mastery`/`student_vocab_srs`
  and `vocab_research_bkt_state`/`vocab_research_retention_state`/`_events` are written by
  disjoint functions (`analytics/bkt_mastery.py`+`analytics/srs_store.py` vs
  `application/research_retention.py`+`repositories/vocabulary_research.py`), both reusing
  the same pure math (`analytics/bkt.py`, `analytics/srs.py`) but never cross-writing state.
  The single routing decision is `apply_response_routing()` in
  `backend/application/vocabulary_research.py`.
- **The Story Speaking vocabulary preview already sources from the same quiz bank** —
  `speakingVocabularyItems()` → `topicQuizEntries()`, shown once as a dismissible overlay
  before Story Practice's scenes (this session, `9231771`/`ceab4f9`). No second preview bank
  exists.
- **`BKT_CONFIG` in `backend/analytics/bkt.py` (lines ~78-79) is explicitly still a TODO** —
  the module docstring and an inline comment both call it "engineering defaults... not
  research-validated," to be replaced with pilot-calibrated/frozen parameters before the main
  experiment. This is a known, already-tracked gap, not something this migration needs to fix.

## 1. Ownership map (current state)

| Data | Canonical owner (table/module) | Status vs. target architecture |
|---|---|---|
| Vocabulary + quiz questions | `custom_stories.vocab_assessment` | Canonical in practice; not yet a normalized `vocabulary_items`/`quiz_questions` table (target's Phase B, not started) |
| Story/scene authored content | `custom_stories.frames`, `.story_vocabulary`, `.story_phrases` | Still the compatibility aggregate; canonical vocabulary/question imports are managed in Admin Content Bank |
| Conversation | `custom_stories.conversation_turns` | Alternating-turn JSON; already the sole source (no second conversation DB) |
| Instructional media (images, scene/vocab/conversation audio) | URLs embedded in the `custom_stories` JSON | Ownership is implicit in the story/media persistence paths, not an explicit `MediaAsset` table yet |
| Student evidence (recordings) | `audio_records` | Stable; already excluded from the content/curriculum domain |
| Story submissions | `story_submissions` | Stable |
| Quiz attempts/responses | `vocab_quiz_attempts`, `vocab_quiz_responses` | Stable; `vocab_quiz_responses` is the actual source of truth BKT replays from |
| Production BKT state | `student_vocab_mastery` | **Write-only cache today** — `rebuild_student_vocabulary_mastery` writes it, but no production reader selects from it; `get_vocabulary_mastery` always replays live from `vocab_quiz_responses` instead. Worth knowing before anyone "optimizes" this table's schema — it's currently an audit artifact, not a read path. |
| Production SRS state | `student_vocab_srs`, `student_vocab_srs_events` | Stable, single writer (`analytics/srs_store.py`) |
| Research state (BKT/retention/probes/policy) | `vocab_research_*` (7 tables, migrations 0043-0049) | Fully isolated from production, confirmed by code inspection, not just docstrings |

## 2. Detailed writer/reader map

### 2.1 Vocabulary & quiz (`custom_stories.vocab_assessment`)

- **Writers**: `backend/routers/story_quiz_vocabulary.py` (admin CRUD, fixed this session to
  use the current round contract), `backend/scripts/import_question_bank_workbook.py`
  (bulk CSV import), `backend/routers/story_crud.py` (whole-story create/update, e.g. when a
  teacher authors a brand-new story with quiz content attached).
- **Readers**: `frontend/src/utils/topicQuiz.ts:topicQuizEntries()` (the single frontend
  entry point — used by the student quiz, the Speaking vocabulary preview, and Admin
  Vocabulary's `QuestionPreview.tsx`), `backend/analytics/bkt_mastery.py` (word metadata
  lookups for diagnostics).
- **Frontend pages**: `AdminVocabularyPage.tsx` (metadata + quiz CRUD),
  `StoryVocabQuiz.tsx`/`QuizQuestion.tsx` (student quiz), `SpeakingVocabularyPreview.tsx`.
- **Tests**: `backend/tests/test_quiz_vocab_crud.py`, `test_vocab_assessment.py`,
  `test_question_bank_workbook.py`, `frontend/src/utils/topicQuiz.test.ts`,
  `frontend/src/pages/AdminVocabularyPage.test.tsx`.
- **Migration compatibility**: none needed yet — this is already the canonical source; a
  future normalized `vocabulary_items`/`quiz_questions` table would need
  `serialize_vocab_assessment()` (target's Section 5 Phase C) to keep every one of the
  readers above unchanged during the transition.

### 2.2 Frame/story-level vocabulary duplication (`frames[].vocabulary*`, `story_vocabulary`)

- **Writers**: `StoryBuilderSection` (frontend, teacher authoring) → `story_crud.py`.
- **Readers**: legacy display paths for stories that predate `vocab_assessment` (a story
  with no canonical bank still needs *something* to show).
- **Live readers still exist** — do not delete these fields yet. The correct next step
  (target Section 30/36: "canonical vocabulary metadata is read-only here... provide
  `Manage vocabulary` navigation instead") is to stop *editing* metadata here, not to remove
  the fields, since older/legacy stories without a `vocab_assessment` entry still depend on
  them for display.

### 2.3 Story speaking media (`frames[].listenAudioUrl`, `.vocabularyAudioUrls`, `imageUrl`)

- **Writers**: `backend/services/media.py:persist_story_frame_audio()` (already the single
  audio-persistence implementation — do not build a second one, per the plan's own Section 5
  of the earlier Admin Content Management spec, already honored).
- **Readers**: `StoryRecorderRuntime.js` (scene playback — see 2.7 below on why this file is
  hands-off).

### 2.4 Conversation (`conversation_turns[].audioUrl`, `.targetAudioUrl`)

- **Writers**: `backend/services/media.py:persist_story_conversation_audio()` (this
  session's Dual Speaking Modes work, `ae38984`) — converts data-URI uploads to `/uploads/...`
  independently for character (`audioUrl`) vs student-model (`targetAudioUrl`) audio, never
  conflating the two roles.
- **Readers**: `SpeakingConversationFlow.tsx` (frontend playback),
  `verified_speaking.py:resolve_verified_speaking_target()` (resolves a conversation turn's
  target text server-side — never trusts client-submitted text, per Section 20's requirement,
  already implemented this session in `3eacb9f`).
- **Tests**: `backend/tests/test_custom_stories_conversation_audio_upload.py`,
  `test_verified_speaking_conversation.py`.

### 2.5 Student evidence (`audio_records`, `story_submissions`)

- Already isolated from curriculum content — confirmed both by this audit and by the
  earlier Performance Audit (`PERFORMANCE_AUDIT.md`) written this session, which measured
  real payload/query behavior on these tables. No canonical-content changes needed here;
  Section 39's "Admin → Records, separate from Content Library" is a UI-organization concern,
  not a data-ownership one — the data is already separate.

### 2.6 BKT / SRS / Research

See section 0 above for the separation confirmation. Full writer/reader/test map (gathered
this pass, not previously documented anywhere in the repo):

| Table | Sole writer | Key reader(s) |
|---|---|---|
| `vocab_quiz_attempts` | `routers/vocab_quiz_attempts.py:create_vocab_quiz_attempt` | `routers/students.py:get_student_overview`, `routers/admin.py:get_roster_overview`, `routers/vocab_quiz_analytics.py`, `routers/knowledge_analytics.py` |
| `vocab_quiz_responses` | `analytics/bkt_mastery.py:upsert_raw_responses` | `analytics/bkt_mastery.py` (diagnostic status, `get_vocabulary_mastery`, `seen_item_ids`) — this is the actual BKT replay source, not `student_vocab_mastery` |
| `student_vocab_mastery` | `analytics/bkt_mastery.py:rebuild_student_vocabulary_mastery` | none in production (write-only cache today — see 1. above) |
| `student_vocab_srs` / `_events` | `analytics/srs_store.py` (`upsert_srs_state`, `apply_srs_updates`, `record_srs_event`) | `analytics/review_queue.py:build_review_queue` → `routers/vocab_quiz_mastery.py:get_student_review_queue` |
| `vocab_research_bkt_state` | `repositories/vocabulary_research.py:upsert_research_bkt_state` | `routers/vocab_quiz_research.py:create_research_practice_session` |
| `vocab_research_retention_state`/`_events` | `application/research_retention.py` via `repositories/vocabulary_research.py` | `research_retention.py:build_review_session` → `routers/vocab_quiz_research.py:get_research_review_session` |

Routing chokepoint for both SRS and research retention:
`backend/application/vocabulary_research.py:apply_response_routing()`.

### 2.7 Generated/bundled runtime

`frontend/src/components/story-recorder/StoryRecorderRuntime.js` is a committed, minified,
`@ts-nocheck` bundle with **no separate editable source in this repo** — confirmed multiple
times this session (Dual Speaking Modes Epic 4, Vocabulary Preview Epic C). Every feature
built against it this session has worked *around* it (MutationObserver on its DOM output,
overlay composition) rather than editing inside it. This audit finds no new evidence of a
generation path; treat Section 43's guidance as already the established practice, not a new
constraint.

## 3. What this audit does NOT cover yet

Time-boxed for this pass. Not yet audited in the same writer/reader depth:

- Placement test's current frontend-side sampling (`frontend/src/utils/placementTestSampling.ts`)
  — relevant to Section 8's server-side projection ask, not yet mapped in detail.
- The full AI feedback pipeline's internal stages (quality gate, ASR, Praat, content
  matching) — Section 0 confirms there's one implementation, not two, but the pipeline's
  internal evidence contract wasn't re-audited here since nothing in this session's work
  touched it.
- Exact current alembic head vs. what's actually applied to the running dev database —
  worth a `alembic current` check before any schema-touching step.

## 4. Recommended next step

Continue consolidating authoring and imports through the Admin Content Bank. There is no
separate content-diagnostic route or CLI in the current architecture.

Everything past that (Section 5's repository abstraction, Section 7's XLSX import redesign,
Section 32-39's full Admin Content Hub shell) is a larger, separately-scoped effort — each
deserves its own go-ahead rather than being bundled into this audit's follow-up.
