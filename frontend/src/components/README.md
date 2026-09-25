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
│   └── student-layout/          # shared page body, stack, grid, row, action primitives
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

1. New reusable primitives belong in `shared/ui`; `components/` owns domain
   presentations only.
2. A domain folder owns its implementation, colocated styles, tests, and small
   domain helpers. Move a whole slice together rather than leaving CSS/tests at
   the root.
3. A folder `index.ts` is the public boundary for the grouped components. Pages
   may use a direct file import only when they need a domain-internal module.
4. `app/` owns route composition and data orchestration. Components do not
   reach across features through duplicated UI files.
5. `features/` owns feature-level composition and contracts. It is the home
   for workflow UI; `components/` is not a second page tree.
6. There are no compatibility bridge files in this tree. Reusable UI imports
   come from `@shared/ui` or `@shared/ui/student`.

7. Student Mode pages use `student-workspace/student-layout` for page bodies,
   sibling rhythm, repeated grids, rows, and action groups. Feature CSS may
   style content inside those primitives, but must not create a second page
   rail, outer surface, or scroll container.

This structure is intentionally incremental: existing workflow folders already
have clear ownership and are not flattened or renamed merely for symmetry.
