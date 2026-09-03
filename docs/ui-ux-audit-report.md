# UI/UX audit report

Date: 2026-08-27
Scope: React/Vite student app, speaking flow, shared UI and teacher management shell

## Outcome

The audit fixed the clear shared UI issues without changing quiz behavior, scoring, weak-word logic, pronunciation logic, API contracts or database schema. No P0/P1 UI regressions were found in the verified surfaces.

## Audit matrix

| Surface | Expected | Actual / fix | Result | Risk |
| --- | --- | --- | --- | --- |
| Student home | No overflow at 375–1440px; image cards keep their frame | `scrollWidth === clientWidth` at 375, 390, 768, 1024 and 1440; existing paper/ink layout preserved | PASS | Backend API requests are noisy when FastAPI is offline |
| Story practice image | Stable ratio, no distortion or accidental crop | Study and result image frames use a stable 4:3 ratio; images use `contain` and reserved space | PASS | Full recording workflow needs a running backend/media device |
| Speaking results | Content-driven height; footer does not jump with short/long steps | Removed result-column height forcing and CTA auto-margin; footer stays in normal flow | PASS (unit/build) | Browser result screenshot not possible without a completed recording |
| Pronunciation feedback modal | Scroll-safe, focus-safe, no background scroll/layout shift | Added focus trap, initial close focus, Escape, backdrop close, focus restore, body scroll lock and scrollbar compensation | PASS (unit) | Full visual modal pass needs real analysis payload |
| Shared modal | Same behavior as pronunciation modal | Added the same keyboard/focus/scroll guarantees while retaining existing props | PASS (4 tests) | None known |
| Teacher management shell | Consistent icons, responsive drawer, keyboard-safe controls | Replaced functional emoji icons with inline SVG; drawer focuses first item and restores menu focus on Escape; focus rings and touch targets added | PASS (unit + browser at 390/1440) | Backend data states were empty because API was offline |
| Teacher dashboard panels | Consistent headings/actions | Replaced heading emoji with SVG icons; action buttons have 44px target | PASS | None known |
| Admin analytics / practice debugger | Admin-only and responsive | No business logic changed; browser data-state verification blocked by unavailable authenticated backend | NOT FULLY VERIFIED | P2: run with seeded admin session/data |
| Login, voice-test, analyze | Preserve behavior and avoid layout regressions | No logic changes; build remains green | PARTIAL | P2: repeat browser workflow with backend available |

## Fidelity ledger

| Check | Baseline | After | Decision |
| --- | --- | --- | --- |
| Layout language | Chinese paper/ink student; green management | Preserved | PASS |
| Spacing / stable dimensions | Student homepage already fit viewport; speaking had height/auto-margin risk | Removed result height coupling; retained existing spacing tokens | PASS |
| Typography | Existing bilingual hierarchy | Preserved; no new small text introduced | PASS |
| Color / contrast | Existing clay/jade/gold palette | Preserved; focus rings use existing accent colors | PASS |
| Icon treatment | Management and speaking actions mixed emoji/symbols | One inline SVG outline family with `currentColor` | PASS |
| Image treatment | Some study/mobile rules could crop or change ratio | Stable 4:3 frame + `contain` | PASS |
| Modal behavior | Escape/backdrop existed; focus and scroll handling incomplete | Focus trap, restore, scroll lock and compensation | PASS |
| Responsive collapse | Existing breakpoints | Verified student at five widths and teacher at 390/1440 | PASS |
| Motion | Existing light transitions | Reduced-motion disables button transforms/transitions and existing screen/modal animation rules | PASS |

## Before / after evidence

- [Student mobile before](../output/playwright/student-mobile-390-before.png) → [after](../output/playwright/student-mobile-390-after.png)
- [Student desktop before](../output/playwright/student-desktop-1280-before.png) → [after](../output/playwright/student-desktop-1440-after.png)
- [Teacher mobile after](../output/playwright/teacher-mobile-390-after.png)
- [Teacher desktop after](../output/playwright/teacher-desktop-1440-after.png)

Browser measurements from Playwright:

```text
Student: 375/375, 390/390, 768/768, 1024/1024, 1440/1440
Teacher: 390/390, 1440/1440
```

The first number is `scrollWidth`; the second is `clientWidth`.

## Automated verification

- Targeted UI tests: 11 passed.
- Production build: passed.
- Full frontend suite: 536 passed, 10 skipped, 4 pre-existing failures.
  - Three failures are existing StoryVocabQuiz expectations for a `Continue to practice` action that is not rendered in those fixtures.
  - One failure is the existing `teacherStories` medium translation fixture.
- `typecheck:all`: one pre-existing fixture type error in `src/utils/storyLevelProgress.test.ts`.
- Browser/IAB was unavailable, so Playwright Chromium was used as the documented fallback.
- Console errors during browser QA were failed requests to the offline backend at `127.0.0.1:8000`, not frontend runtime exceptions.

## Files changed

- `frontend/src/shared/ui/Modal.tsx`, `shared-ui.test.tsx`, and new `shared/ui/Icon.tsx`.
- `frontend/src/components/management/ManagementShell.tsx/.css` and its focused keyboard test.
- Speaking results/modal layout and action icon surfaces.
- Scene image ratio/object-fit rules and reduced-motion button behavior.
- Teacher dashboard/audio/story overview icon consistency.

The existing user CSS work in `frontend/src/styles/components/story-recorder/08-insights-responsive.css` was preserved and the CSV file was not staged or modified.
