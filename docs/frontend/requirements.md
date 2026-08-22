# Frontend requirements

## Product boundary

The frontend is a React 18 + Vite application with separate Vite entries for
student, teacher and admin surfaces. The FastAPI backend remains the source of
truth for accounts, stories, quiz material and pronunciation analysis.

## Learner Workspace v1

- Preserve the current ivory/paper/ink visual identity and bilingual copy style.
- Keep Practice, Progress and Picture talk as the visible workspace areas.
- Show current progress, today's goal, quiz vocabulary count and continuation
  status without inventing server-side results.
- Show an explicit quiz gate before speaking practice.
- If a quiz is required, `Take quiz to begin` opens the existing vocabulary quiz.
- If the quiz is complete, `Start activity` opens the existing story overview.
- Starting from a scrolled workspace must reset the activity to the top.
- Preserve the legacy shell behind `VITE_STUDENT_WORKSPACE_SHELL=legacy`.

## Non-goals for this phase

- No Next.js migration.
- No backend endpoint or database schema changes.
- No pronunciation threshold, verdict or tone-scoring changes.
- No new server-state dependency until the API modules are split and measured.

