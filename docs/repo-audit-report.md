# Repository audit and pilot-readiness report

Audit date: 2026-08-20
Scope: source code, build/test state, generated artifacts, database/storage path, and deployment configuration.

## Executive decision

The two-device development workflow is safe when each device runs
`docker-compose.laptop.yml` with its own `.env` and Docker volumes. The shared
`start.ps1 -Mode Laptop` workflow remains intentionally separate and should not
be used when device databases must be independent.

One stale root prototype, `demo.html`, had no build input or repository
references and was removed. Research, migration, seed, runtime, and authored
lesson files were retained.

The application can store pilot records in PostgreSQL when migrations have run, but it is not yet a complete production data-retention system until the deployment provides persistent object/file storage for uploaded audio and images. PostgreSQL persistence and uploaded-media persistence are separate concerns.

## Findings that required code changes

| Area | Evidence | Change | Status |
|---|---|---|---|
| Readiness | `/health` returned HTTP 200 even when the database was unavailable | Added `/health/ready`, which returns 503 unless database and upload storage are available; `/health` now reports both statuses | Fixed |
| Upload safety | The audio-record upload path did not apply the shared maximum-size limit and wrote directly to the final path | Enforced `MAX_AUDIO_BYTES` and switched to temp-write plus atomic replace | Fixed |
| Deployment privacy | `backend/Dockerfile` uses `COPY . .`; the previous `.dockerignore` did not exclude `private-data`, benchmarking outputs, or reports | Excluded these research/private directories from production images | Fixed |
| Render readiness | Deployment health probe used the permissive `/health` endpoint | Switched `render.yaml` to `/health/ready` and documented `UPLOAD_DIR` | Fixed |

## High-priority risks still requiring an infrastructure/product decision

1. **Uploaded audio/images can disappear on a container replacement.** The database rows survive PostgreSQL restart, but `/data/uploads` only survives if the hosting provider mounts persistent storage or the application is changed to use object storage. Do not call the pilot “data-safe” until this is verified with a restart/restore drill.
2. **API authorization is not a production security boundary.** Student login is a classroom friction gate, compares the stored password directly, and returns no session token. Several teacher/student data endpoints are callable without an authenticated server-side identity. This may be acceptable for a tightly controlled local pilot, but not for a public multi-class deployment.
3. **Research logs and measurement events have different stores.** Core attempts are in PostgreSQL. Measurement events now have a PostgreSQL append-only ingestion table (`learning_measurement_events`, migration `0012`) with localStorage retained only as a best-effort offline fallback. A production pilot should still monitor ingestion failures and periodically export the server data.
4. **Teacher analytics must be scoped by class/teacher before multi-class use.** Current records have student/story identifiers, but the audit did not find a complete tenant/class authorization layer.

## Keep — runtime and safety-critical files

- `backend/main.py`, `backend/database.py`, `backend/routers/`, `backend/migrations/`: runtime API, persistence, and schema history.
- `backend/tests/`, `src/**/*.test.*`: keep and repair failing tests; they are the regression contract.
- `backend/private-data/`: do not delete as part of cleanup. It contains research/audio/model inputs; archive under an approved data-retention policy instead. It is now excluded from production Docker images.
- `backend/migrations/versions/`: never delete an applied migration. Add a new migration for schema changes.
- `docker-compose.yml`, `render.yaml`, `.env.example`, `backend/.env.example`: deployment/configuration sources.
- `docs/build_*.mjs`, `docs/build_*.py`: keep if reproducible dashboard/document deliverables are required; otherwise archive them together with their outputs, not independently.

## Archive or review — not runtime, but not safe to delete blindly

| Path/pattern | Why it is likely non-runtime | Recommendation |
|---|---|---|
| `backend/benchmarking/` | Evaluation scripts, datasets, and result tables; `backend/main.py` imports `routers/benchmark.py`, which uses `benchmarking` at runtime, and the test suite imports research modules | Keep. Archive duplicate/stale runs only after confirming provenance and updating the benchmark/test references |
| `demo.html` | Initial static prototype; not a Vite input and no source/docs references | Removed after repository-reference audit |
| `backend/benchmarking/results/*STALE*` | Filename explicitly marks superseded snapshots | Candidate for deletion after confirming no report links to it |
| `backend/reports/` | Generated annotations, KPI reports, and audit outputs | Archive as research evidence; do not ship/deploy |
| `output/` | Generated WAVs, DOCX/XLSX, previews, and inspection files | Keep final deliverables; delete/regenerate scratch audio and inspection files after approval |
| `.codex/`, `.playwright-cli/`, `.superpowers/`, `.pytest_cache/` | Tool/session/cache artifacts | Regenerable; remove only after checking whether a current workflow needs them |
| `docs/node_modules/` junction/support directory | Tool support for spreadsheet generation, not application runtime | Keep while regenerating artifacts; remove from a clean checkout if it is not tracked/needed |

## Safe-to-regenerate candidates

These should not be committed as source artifacts and can normally be removed after checking local tooling: `dist/`, `.pytest_cache/`, Python `__pycache__/`, frontend `node_modules/`, and generated inspection previews. The existing `.gitignore` already covers most of these. `backend/mandarin_stories.db` is a legacy SQLite artifact excluded from the Docker image; verify it contains no unique data before removing it.

## Broken or stale code signals

- The production build passes, but the full frontend suite is not green: the old analysis-version-selector tests still expect a component intentionally removed by the product decision; `TeacherDashboardPage` has three unrelated failing scenarios around pitch-chart/materials/profile data. These should be fixed or explicitly quarantined before pilot sign-off.
- The repository has both legacy and newer pronunciation/assistive-feedback paths. Existing safety tests constrain the public E-family path, but a future cleanup must use import/call-graph evidence and tests; deleting files by filename would risk breaking dynamic imports and research reproducibility.
- The production bundle emits a warning for a 571 kB minified student chunk. This is not a correctness blocker, but code-splitting should be a post-pilot performance task.

## Pilot acceptance checklist

- [ ] Run `alembic upgrade head` against the pilot PostgreSQL database.
- [ ] Verify `GET /health/ready` is 200 with `database=ok` and `storage=ok`.
- [ ] Upload one audio and one image, restart/redeploy the backend, and verify both URLs still play.
- [ ] Take and restore a PostgreSQL backup; verify audio backup/restore separately.
- [ ] Decide whether the pilot is single-class/private or needs real authentication and class-level authorization.
- [ ] Monitor the server measurement-event ingestion and export it periodically for the study archive.
- [ ] Repair/quarantine the known failing frontend tests and run the pilot smoke flow end-to-end.
