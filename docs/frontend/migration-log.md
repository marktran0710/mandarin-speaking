# Frontend migration log

## 2026-08-22 — Phase 0 and Learner Workspace v1

- Baseline: commit `b091de0` on `main`.
- Refactor branch: `codex/frontend-refactor`.
- Baseline build passed.
- Baseline test result: 68 files passed, 2 files failed with 4 existing
  failures in teacher dashboard/story summary tests.
- Added the feature-flagged learner workspace shell and overview components.
- Reused the existing topic selector, story recorder, progress and picture-talk
  flows.
- Added keyboard tab navigation and a compact quick-start band with the quiz
  gate. Removed the new progress, continuation and vocabulary cards because
  those details already exist in the Practice/Progress destinations.
- Fixed workspace-to-activity scroll anchoring so the activity starts at
  `scrollY=0`.
- Browser-verified at 1440×1000 and 390×844 with no horizontal overflow.
- Added shared UI primitives with keyboard/focus and responsive layering rules.
- Added domain API adapters and moved the student composition root to the
  learning adapter without changing backend endpoints.
- Added shared primitive tests: 6 targeted tests pass.
- Added the first feature entry point and centralized workspace feature flag;
  legacy and migrated workspace implementations can now coexist cleanly.

## Next migration slices

1. Split the student practice flow behind the same shell boundary.
2. Move teacher quiz review into feature-owned modules.
3. Move admin account/content sections into feature-owned modules.
4. Remove legacy paths only after browser and regression checks pass.
