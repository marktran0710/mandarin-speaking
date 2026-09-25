# Frontend architecture

## Layers (imports only go down)

```text
app/  →  features/  →  entities/  →  shared/
```

- `app/<role>/` — entrypoints, role apps, shells, navigation, and composition of features.
- `features/<name>/` — one user capability: `<Name>Page`, `components/`, `hooks/`, `model/`, and `<name>.css`.
- `entities/<name>/` — business concepts: `types.ts`, pure `model/` rules, `api.ts`, and optional small UI.
- `shared/` — no business words: the only primitive UI set, tokens/themes, API client, config, and generic hooks/lib.

## Where new code goes

Use the first matching answer:

1. Wiring, routing, shells, or composing several features → `app/<role>/`.
2. UI or state for one user capability → `features/<name>/`.
3. A business type, rule, or API needed by at least two features → `entities/<name>/`.
4. No business words → `shared/`.

Start inside the feature and move code down only when a second consumer appears. Move; do not copy.

## Import rules

- Never import upward. Features do not import other features.
- Cross-slice imports go through the slice's `index.ts` only.
- There are no cycles. Only `entities/*/api.ts` and `shared/api/` call `fetch`.
- Use `@app/`, `@features/`, `@entities/`, and `@shared/` aliases. Relative imports are for code inside one slice.

## Files and folders

- Folders are kebab-case.
- Components are one-per-file `PascalCase.tsx`; hooks use `useX.ts`; pure modules use `camelCase.ts`.
- Do not create `utils.*`, `helpers.*`, `misc.*`, or `common.*` files, or dotted pseudo-folders such as `X.Form.tsx`.
- Group into `components/`, `hooks/`, or `model/` only when there are at least three files of that kind.
- Split files with two responsibilities. Review at 250 lines (`tsx`) or 300 lines (`ts`); 500 lines is an error.
- Tests sit next to the file they test. Cross-feature tests live in `src/integration/`.

## UI and styles

- Keep one primitive set in `shared/ui`; add variants instead of new `XxxButton` components.
- Components use semantic tokens only: `--color-*`, `--space-*`, `--radius-*`, and `--font-*`.
- `shared/styles/themes/student.css` and `staff.css` assign the theme values.

## Legacy

Legacy compatibility shims are not allowed. Ownership changes update all
consumers in the same migration batch.

## Enforcement

Run `npm run check` from `frontend/` before merging. Dependency-cruiser runs
without an ignored-violation baseline.
