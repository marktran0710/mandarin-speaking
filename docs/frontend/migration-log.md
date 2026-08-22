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
- Added keyboard tab navigation, quiz gate status, continue-learning summary,
  vocabulary preview and progress snapshot.
- Fixed workspace-to-activity scroll anchoring so the activity starts at
  `scrollY=0`.
- Browser-verified at 1440×1000 and 390×844 with no horizontal overflow.

## Next migration slices

1. Extract shared UI primitives and API adapters without changing contracts.
2. Split the student practice flow behind the same shell boundary.
3. Move teacher quiz review into feature-owned modules.
4. Move admin account/content sections into feature-owned modules.
5. Remove legacy paths only after browser and regression checks pass.

