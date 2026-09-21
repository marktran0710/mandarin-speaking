# Frontend component architecture

The `components` tree is organized by ownership, not by the order in which a
component was added. Route pages compose these groups; they do not own a second
copy of a shared primitive.

```text
components/
├── ui/                         # app-wide visual primitives and error boundary
├── navigation/                 # global navigation and student shell primitives
├── content/                    # lesson/topic content selection and content diff
│   └── topic-selector/          # topic selector domain types
├── student/                    # reusable student-facing feedback and controls
├── analytics/                  # teacher/admin measurement and progress panels
├── student-workspace/           # student shell, sidebar, page shell, workspace layout
├── student-question-flow/      # reusable question-flow behavior and geometry
├── story-recorder/              # story recording workflow
├── story-vocab-quiz/            # vocabulary quiz workflow
├── speaking-flow-card/          # speaking practice and results workflow
├── pronunciation-breakdown/     # pronunciation result model and presentation
├── pitch/                       # pitch visualizations
├── tone/                        # tone marks and tone-field controls
├── journey/                     # learning journey presentation
├── teacher/                     # teacher-only workflow components
└── management/                  # shared teacher/admin management shell
```

## Rules

1. New reusable primitives belong in `ui/`, not at the `components/` root.
2. A domain folder owns its implementation, colocated styles, tests, and small
   domain helpers. Move a whole slice together rather than leaving CSS/tests at
   the root.
3. A folder `index.ts` is the public boundary for the grouped components. Pages
   may use a direct file import only when they need a domain-internal module.
4. `pages/` owns route composition and data orchestration. Components do not
   reach across domains through duplicated UI files.
5. `features/` owns feature-level composition and contracts. It may re-export
   a component group while a migration is in progress, but it is not a second
   component home.
6. The root-level `AppButton.tsx`, `BiLabel.tsx`, `BiLabel.css`, and
   `StudentHelpPanel.tsx` are temporary compatibility bridges for the checked-in
   legacy `StoryRecorderRuntime.js` bundle. New code must import from `ui/` or
   `student/`; remove these bridges when that bundle is rebuilt and its import
   paths are updated.

This structure is intentionally incremental: existing workflow folders already
have clear ownership and are not flattened or renamed merely for symmetry.
