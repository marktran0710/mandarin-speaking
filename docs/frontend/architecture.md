# Frontend architecture

## Current runtime

React 18 + Vite is retained. `frontend/src/App.tsx` is the student composition
root, while `teacher-main.tsx` and `admin-main.tsx` keep teacher/admin sessions
independent through separate Vite entries.

## Migration target

The frontend is moving incrementally toward feature ownership:

```text
app/          entries, providers, shells and routing boundaries
shared/       API adapters, UI primitives, design tokens and utilities
entities/     auth, student, teacher, story, quiz, pronunciation and account
features/     workspace, practice, quiz, story builder, review and analytics
widgets/      student, teacher and admin shells
pages/        thin route-level compositions
```

The first migration keeps the existing page contracts and puts the new learner
workspace shell around the existing `CreateStoryPage`, `MyStoriesPage` and
`ImageNarrationPage`. Legacy rendering remains available through the feature
flag until the browser flow and regression tests are stable.

## Data ownership

- Local UI state belongs to the feature component.
- Student identity remains in the existing session utilities.
- Quiz completion remains scoped through the existing vocabulary quiz storage.
- Backend reads/writes remain in `services/database.ts` until domain adapters are
  extracted in a later phase.

## Shared foundation status

- `shared/ui` now owns the first reusable primitives: action button, card, badge,
  tabs, progress bar, modal, data table and empty/loading/error state panel.
- `shared/api` provides thin learning, quiz, story and account boundaries. They
  currently delegate to `services/database.ts`, so endpoint contracts and local
  fallbacks do not change during migration.
- New feature code should import from these boundaries; the legacy service is
  retained until each domain has browser coverage and can be moved safely.
