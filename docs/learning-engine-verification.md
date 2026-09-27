# Learning engine verification runbook

The repository contains one runner for the three production paths:

```powershell
cd backend
python scripts/verify_learning_engine.py --engine bkt
python scripts/verify_learning_engine.py --engine sm2
python scripts/verify_learning_engine.py --engine voice --provider groq --audio-dir .\verification_audio
python scripts/verify_learning_engine.py --engine all --provider groq --audio-dir .\verification_audio
# Live API smoke against a running backend and a real student account:
python scripts/manual_bkt_smoke.py --base-url http://127.0.0.1:8000 --student-id <id> --password <password>
```

## Algorithm Verifier v1

Admin -> Learning Engine -> Algorithm verifier reuses the existing Learning
Engine route and contains three tabs: BKT, SM-2, and Integration. The BKT and
SM-2 tabs compare production adapters with standard-library reference functions
that do not import production learner-model code. Every result includes the
explicit inputs, both traces, differences, tolerance, timestamp, and model
fingerprint. The pinned BKT golden fixtures retain their `1e-9` tolerance;
interactive BKT calculations use `0.001` by default.

The BKT verifier exposes the production defaults (`P(L0)=0.20`, `P(T)=0.15`,
MCQ `G/S=0.20/0.10`, typed `G/S=0.05/0.15`) as editable inputs. It shows the
posterior numerator and denominator, the learning transition, and explicit
clamping to `[0.000001, 0.999999]`. Presets cover single responses, format-aware
success sequences, recovery, and high-probability failures. Application mastery
is shown separately: the diagnostic gate still requires all three rounds, and a
failed dimension needs two targeted corrective successes before enrollment.

The SM-2 tab labels the implementation **Modified SM-2 behavior**. Student
grading maps correct to quality `4` and wrong to quality `2`; enrollment starts
at repetition `1`; intervals are `1`, `6`, then `round(previous interval *
previous ease)` using Python ties-to-even. The raw product is displayed, along
with exact timestamps, minimum ease `1.3`, due-cycle guards, and the development
day compression value.

The Integration tab is development-only and uses the published Lesson 8 reading
fixture resolved by lesson `8`, section `3`, and canonical word IDs. It requires
all seven words exactly once in each of `tier1`, `tier2`, and `tier3`. Focus words
are `C8-8-3-W203` (年輕), `W204` (老), and `W205` (皮包); supporting diagnostics
are `W206-W209`. The run submits real published question IDs through the normal
quiz resolver, records synthetic provenance server-side, captures partial then
completed persistence, and reports BKT, application mastery, SRS, and queue state
after every stage. The reserved student is
`test-stu-verifier-integration-001`; it is never enrolled in research studies.

Reset deletes only that student's owned rows and the verifier report, then writes
a clean `READY` run. A reserved ID without `is_test_account=true` blocks the
operation. Verifier writes require an authenticated Admin, development mode, an
active run, the exact reserved student selected by the server, and a monotonic
step header. Normal student requests remain unchanged. Verifier rows are tagged
`synthetic` and must be excluded from normal analytics, calibration, research
exports, participant counts, and study summaries.

The reproducible integration clock is `2026-08-01T00:00:00Z`; `D` is the active
development scheduling-day length. After diagnostics, 老 reaches approximately
`0.959495` but remains practice-required. Two correct meaning-practice answers
enroll it. A correct review of 年輕 at `base + D` produces repetition `2`,
interval `6`, and due time `base + 7D`; a wrong review at `base + 7D` resets the
schedule and reopens targeted meaning practice. Queue reports distinguish due
extras, weak entries, overlaps, exclusions, and ordering.

The runner loads `backend/.env`, creates a uniquely named PostgreSQL database,
applies Alembic to `head`, runs the focused API/ledger checks, and drops the
database unless `--keep-database` is supplied. It writes a Markdown and JSON
report to `backend/verification_reports` (or the directory passed with
`--output-dir`). Reports contain expected values, actual values and one of
`PASS`, `FAIL`, or `BLOCKED`; they never contain credentials. Exit codes are
0 for all pass, 1 for a failure, and 2 when an external prerequisite is
blocked. Migration and focused-test subprocesses have hard time limits; a
timeout is reported as `FAIL`, and the runner still attempts to drop its
temporary database.

For voice acceptance, use recordings made by a real Mandarin speaker. The
directory must contain a `manifest.json` like this:

```json
{
  "recordings": [
    {
      "file": "correct.wav",
      "target_text": "你好",
      "suggested_answer": "你好",
      "pinyin": "ni3 hao3",
      "context": "A greeting",
      "vocabulary": "你好",
      "speaker_confirmed_human": true,
      "human_rating": "passed"
    }
  ]
}
```

`human_rating` is `passed`, `needs_practice`, or `not_judged`. Without it,
technical analysis can still run, but the human-agreement result is
`BLOCKED`. If audio or a provider key is missing, no cloud call is made and
the report is `BLOCKED`.

What each engine proves:

* BKT uses a published assessment item, server-side answer resolution and
  persisted response ledger. It checks the independent posterior calculation
  (`P(L)=0.20` gives `0.60` after a correct MCQ and about `0.175758` after an
  incorrect one), three diagnostic rounds, duplicate protection, weak-word
  ranking and the question kind selected by the UI.
* SM-2 checks the modified binary mapping (`q=4`/`q=2`), intervals
  `1 -> 6 -> 15`, ease `2.5`, failure reset to repetitions `0`, interval `1`
  and ease `2.18`, exact due-time behavior, retry/idempotency, early-review
  blocking, persistence and the fact that personalized practice does not
  advance SRS.
* Voice invokes the real `_do_analyze` path with an empty transcript and
  `asr_model=auto`. Praat runs alongside ASR when a target is known. Cloud
  coaching is called only after the quality gate and acoustic result; the
  report verifies that the coaching trace contains the same tone, fluency,
  speech-rate and word-prosody values returned by Praat. `feedback_provenance`
  identifies the requested and executed provider, fallback and pronunciation
  source. Human agreement remains a separate calibration result.

The development-only `today=YYYY-MM-DD` query parameter and
`SRS_DAY_SECONDS` compression are accepted only when `APP_ENV=development`.
Production always uses the real clock and a 24-hour day. Refreshing the page,
logging in again or changing devices reads the same schedule from the server.

For browser verification, start the backend and frontend, then set the
student credentials and the published lesson name:

```powershell
$env:E2E_VERIFY_LEARNING_ENGINE = "1"
$env:E2E_STUDENT_NAME = "student@example.com"
$env:E2E_STUDENT_PASSWORD = "..."
$env:E2E_STORY_NAME = "..."
$env:E2E_EXPECTED_WEAK_WORD = "..."       # optional strict assertion
$env:E2E_EXPECTED_DUE_WORD = "..."        # optional strict assertion
$env:E2E_VOICE_AUDIO = "D:\recordings\correct.wav" # optional real WAV
cd frontend
npm run test:e2e -- learning-engine-verification.spec.ts
```

The browser flow opens the published lesson, observes the weak-word and
review-queue API responses, confirms the personalized question carries the
server-ranked word (`data-verification-word`), confirms the due-review word,
then records the supplied audio and checks provider/Praat provenance in the
voice feedback card. The spec is opt-in because it requires a real account,
published content and (for voice) a real human recording.

The equivalent manual acceptance flow is:

1. Complete all three diagnostic rounds, deliberately miss one published word,
   open “Practice weak words”, and verify that word and the failed question
   dimension are selected. Answer it correctly and refresh; the BKT mastery
   and priority order must change while a duplicate request adds no evidence.
2. Bring one word to `STRONG`, set a development `today` date, and complete
   maintenance reviews at the due dates. Confirm `1 -> 6 -> 15` day intervals
   at ease `2.5`; answer incorrectly and confirm reset to repetitions `0`, one
   day and ease `2.18`. Retry the same response, answer early and use
   personalized practice; none may add a second SRS event. Refresh, log in
   again and use another device to confirm the schedule is unchanged.
3. Submit a real human recording with the target sentence, one with missing
   words, one with a tone error, silence and noise. Check the processing trace
   in the API: `asr` and `praat` run, `quality_gate` decides whether the audio
   is judgeable, and only then does `feedback` run. Confirm the response's
   provider, fallback, acoustic-context and pronunciation-source provenance;
   silence/noise must be retry/not-judged with no cloud coaching.

Passing these checks proves technical integration and persistence. It does
not calibrate the scoring thresholds. Before launch, compare the same
recordings with a Mandarin-capable human rater and record disagreements;
engineering defaults remain marked unvalidated in every verdict. Existing
frontend dependency/structure checks also remain a separate repository
health issue and must not be described as product-quality calibration.
