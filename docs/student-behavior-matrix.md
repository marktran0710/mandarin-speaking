# Student behavior matrix

This matrix is the contract for the student-facing learning flow. It covers
normal behavior, recoverable user mistakes, unavailable browser capabilities,
and unsafe analysis responses. A numeric value from the API is never enough by
itself to make a student-facing claim: the quality gate and the evidence state
must allow it first.

## State contract

| State | Meaning | Student UI | Allowed action |
| --- | --- | --- | --- |
| `idle` | No attempt has been captured | Record/upload controls; no result data | Record or choose an audio file |
| `recording` | Microphone is active | Timer and stop control; no score | Stop recording or leave the page |
| `pending_audio` | Audio is converted and ready, but not submitted | Preview, filename, “Audio ready”, Analyze button | Listen, replace, analyze, change scene |
| `analyzing` | One request is in flight | Loading state; controls that would conflict are disabled | Wait, navigate away, or change scene |
| `complete` | Backend returned scoreable evidence | Transcript and only evidence-backed details | Review, practice, record again, continue |
| `retry` | Evidence is unsafe or incomplete | Clear retry notice; no misleading score/details | Record or upload again |
| `empty_history` | No saved student attempts | Honest empty state and path back to practice | Start a lesson |
| `in_progress_history` | A local or server attempt exists but is unfinished | Started/in-progress status | Resume/practice |

## Behavior cases

| ID | Student behavior | Expected result | Evidence |
| --- | --- | --- | --- |
| AUTH-01 | Open app without a session | Student login is shown; protected pages are not rendered | `StudentLoginPage.test.tsx`, `roleGuard.test.tsx` |
| AUTH-02 | Submit empty name/password | Inline validation; no network request | `StudentLoginPage.test.tsx` |
| AUTH-03 | Submit wrong password | Shared error; no session; no navigation | `StudentLoginPage.test.tsx`, `test_students_login.py` |
| AUTH-04 | Submit valid student credentials | Student session is stored and student mode opens | `StudentLoginPage.test.tsx`, `test_students_login.py` |
| AUTH-05 | Teacher session visits student app | Student mode is blocked; roles are not silently reassigned | `session.test.ts`, `roleGuard.test.tsx` |
| AUTH-06 | Malformed local storage | Treat as signed out; do not trust malformed identity | `session.test.ts` |
| NAV-01 | Open Home | Look / Speak / Improve flow and Start Learning are visible | `HomePage.test.tsx`, browser smoke |
| NAV-02 | Open My Stories with no attempts | Empty state is honest; no fake score or story | `MyStoriesPage.test.tsx` |
| NAV-03 | Open My Stories with an unfinished attempt | Started/in-progress state is shown; practice remains available | `MyStoriesPage.test.tsx` |
| AUDIO-01 | Start microphone recording | Recording state and timer appear; no request is sent | Page tests and recorder tests |
| AUDIO-02 | Microphone permission denied/unavailable | Friendly error; tracks/timer are cleaned up | Recorder/page implementation |
| AUDIO-03 | Stop recording | Audio is converted and staged; Analyze is still explicit | `StoryRecorder.gates.test.tsx`, page tests |
| AUDIO-04 | Upload supported audio | Preview, filename, and Analyze appear; no request yet | `ImageNarrationPage.test.tsx`, `ListenRetellPage.test.tsx`, `VoiceTestPage.test.tsx` |
| AUDIO-05 | Upload unsupported file | Error appears; no pending audio and no request | Page tests |
| AUDIO-06 | Replace pending audio | Old preview/result is cleared; only the latest file can be analyzed | Page implementation and upload tests |
| AUDIO-07 | Leave page during recording/conversion | Media tracks, timer, object URL, and stale conversion are cleaned up | Lifecycle implementation |
| AUDIO-08 | Change scene during recording stop | Old recording is discarded; it cannot appear under the new scene | `ImageNarrationPage.test.tsx` |
| AUDIO-09 | Change scene with pending audio | Pending audio/result/preview are cleared | `ListenRetellPage.test.tsx` |
| ANALYZE-01 | Click Analyze without audio | No-op/disabled; no request | Page tests and UI gate |
| ANALYZE-02 | Analyze image narration | Sends audio plus `scene_prompt`, `scene_vocabulary`, `scene_image_url` | `ImageNarrationPage.test.tsx` |
| ANALYZE-03 | Analyze listen-and-retell | Requires Listen first and sends `scene_target_text` from the script | `ListenRetellPage.test.tsx` |
| ANALYZE-04 | Analyze Voice Test WAV | Sends WAV and ASR model only when browser transcript is absent | `VoiceTestPage.test.tsx` |
| ANALYZE-05 | Backend returns 4xx/5xx | Error is shown; no success result is rendered | Page catch paths; backend API tests |
| ANALYZE-06 | Request times out or is aborted by navigation | Stale result is ignored; timeout is retryable | Abort-controller implementation |
| ANALYZE-07 | Backend returns malformed/partial numeric data | Missing/NaN/Infinity values are hidden, never rendered as a score | `narrationAnalysis.test.ts`, image page test |
| RESULT-01 | No transcript | Hide pronunciation/content score and detailed feedback; offer retry | `narrationAnalysis.test.ts` |
| RESULT-02 | `can_score_pronunciation=false` | Show retry gate; hide pronunciation score/details | `narrationAnalysis.test.ts`, page tests |
| RESULT-03 | `can_score_content=false` | Hide content score/details even if numeric fields exist | `narrationAnalysis.test.ts`, backend quality tests |
| RESULT-04 | `content_match=null` | Pronunciation may show; content match/details stay hidden | `narrationAnalysis.test.ts` |
| RESULT-05 | Verified content and reliable evidence | Show transcript, grounded scores, matched/missed details and practice prompt | Page tests and backend quality tests |
| RESULT-06 | Backend status is `retry` despite score-looking fields | Retry status wins; no score is shown | `narrationAnalysis.test.ts` |
| RESULT-07 | Voice evidence is sparse/unverified | Show reliability notice; do not count it as progress | `voiceFeedbackReliability.test.ts` |
| PROGRESS-01 | Self-check after accepted analysis | Self-check appears only after ready/accepted result | `SelfEvalStep.test.tsx`, `SpeakingResultsFlow` tests |
| PROGRESS-02 | Student skips self-check | Skip is allowed and continues to overview; no score is fabricated | `SelfEvalStep.test.tsx` |
| PROGRESS-03 | Pronunciation mastery not reached | Practice/re-record remains available; next progression stays gated | `StoryRecorder` and speaking flow tests |
| PROGRESS-04 | All practice parts pass | Whole-sentence re-record/next action becomes available | Speaking flow tests |
| RES-01 | Refresh/focus after server data failure | Student UI remains usable and falls back to honest local/empty state | App/page tests; runtime smoke |
| RES-02 | Retry analysis | Same staged audio can be submitted again without creating duplicate UI state | Page state implementation |
| RES-03 | Audio URL replacement/unmount | Previous object URL is revoked; no resource leak from preview lifecycle | Page lifecycle implementation |
| A11Y-01 | Use labels to fill login fields | Name/password controls are associated and discoverable by label | `StudentLoginPage.test.tsx` |
| A11Y-02 | Keyboard/button flow | Actions use real buttons and visible state changes | Page tests and browser smoke |

## Data visibility rules

The student UI follows these rules for every analysis page:

1. `pending_audio` is local staged data only. It must not be treated as an
   analyzed attempt until the student presses Analyze.
2. A transcript is required before pronunciation or content scoring can be
   shown.
3. `feedback_quality.can_score_pronunciation` and `can_score_content` are
   authoritative safety gates. Numeric fields cannot override a failed gate.
4. Content details require an explicit `content_match` value or
   `content_accuracy.judged === true`.
5. `status: retry`, missing evidence, and partial/malformed scores produce a
   retry/limited state, never a guessed score.
6. Self-check is a post-analysis reflection step, not a prerequisite for
   uploading or analysis, and it is skippable.
7. A scene change or unmount invalidates pending conversion and analysis
   generations so an old response cannot render in a new scene.

## Verification summary

- Student-focused frontend regression: **88 active tests passed** after the
  latest lifecycle additions.
- Backend student/audio contract subset: **38 tests passed** after migrating
  the isolated `mandarin_test` database.
- Production build: `npm run build` passes.
- Full frontend suite: **520 passed, 3 failed, 10 skipped**. The 3 failures
  are existing teacher-dashboard expectations and are outside this student
  scope; skipped tests include stale teacher/deep-link assumptions.
- Browser smoke: Home and student login render correctly on a clean Vite
  instance; runtime API smoke requires the deployed backend CORS allow-list to
  include the exact frontend origin.

The percentages above measure defined, automated behavior coverage—not every
possible microphone, browser, network, device, or production-provider failure.
