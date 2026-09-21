# Application composition

This directory owns the three runtime surfaces and their composition tests:

- `App.tsx` is the student application shell.
- `AdminApp.tsx`, `TeacherApp.tsx`, and `ManagementApp.tsx` compose staff surfaces.
- `entrypoints/` contains the thin Vite entry modules referenced by the HTML entry files.

Pages, components, services, and domain utilities remain in their own top-level
boundaries. The app files coordinate those boundaries; they do not own feature
implementation details.
