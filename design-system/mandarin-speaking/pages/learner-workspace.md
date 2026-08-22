# Learner Workspace override

The current product visual language is the source of truth for this page. The
generated global recommendation is intentionally overridden here because the
learner already uses the established Chinese paper/ink identity.

## Visual rules

- Canvas: `--clay-canvas` ivory with the existing gold/jade radial accents.
- Surfaces: `--clay-surface-card` white cards with the existing hairline border.
- Ink: `--clay-ink` for Chinese headings, `--clay-body` for supporting text.
- Actions: jade for the active/ready path; gold for progress and quiz attention.
- Typography: keep `--font-display` for Chinese display headings and the existing
  body font stack for UI labels.
- Motion: subtle 150–250ms transitions, with reduced-motion support.

## Layout rules

- Keep the existing page header, username identity pill and stacked mobile tabs.
- Use one overview band followed by three compact cards; avoid a dashboard bento
  grid or extra navigation layers.
- The activity CTA must expose the quiz gate before speaking practice.
- The activity view owns the full-width session layout and hides the workspace
  chrome while recording.
- Validate at 390px, 768px and 1440px; no horizontal overflow and no fixed-nav
  overlap.

## Component families

- `StudentWorkspaceHeader`
- `WorkspaceAreaTabs`
- `LearningOverview`
- `ProgressSnapshot`
- `ContinueLearningCard`
- `VocabularyPreview`
- `QuizGateStatus`

