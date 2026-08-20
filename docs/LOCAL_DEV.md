# Independent device development

This workflow runs a completely separate PostgreSQL database and upload volume
on one device. The backend and frontend run in Docker with source mounts, so
editing the repository still gives Vite and Uvicorn hot reloads. It does not
connect to the Lab machine or use the Lab database.

For two independent devices, repeat this setup separately on both devices.
Each device uses its own clone, `.env`, Docker volumes, database, uploads, and
login accounts. No device-to-device network connection is required.

## First setup

Install Docker Desktop with Compose, clone/pull the repository, then create the
backend environment file from the repository root:

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

For this local-only stack, the example values are usable. Replace
`JWT_SECRET_KEY` and `ADMIN_PASSWORD` if the database or containers will be
shared with anyone else.

## Start

Validate the Compose file, then build and start the stack. The wrapper performs
both checks automatically and also verifies that `backend/.env` exists:

```powershell
.\start.ps1 -Detached
```

The app is available at `http://127.0.0.1:5177`. The backend is available for
diagnostics at `http://127.0.0.1:8001`; normal browser requests go through the
Vite proxy so login cookies remain same-origin.

The backend runs `alembic upgrade head` before Uvicorn starts. If a migration
fails, the backend stays unhealthy instead of serving against a partial schema.

Verify the containers and migration:

```powershell
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml exec backend python -m alembic current
```

The expected migration is `0019 (head)` and the backend readiness endpoint
should return HTTP 200 with `database: "ok"` and `storage: "ok"`.

To run in the background:

```powershell
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml logs -f backend frontend
```

## Seed teaching data

Seeding is explicit and idempotent; it never runs automatically during startup:

```powershell
docker compose -f docker-compose.dev.yml exec backend python -m scripts.seed_dev
```

This restores the versioned materials and teaching images, creates the standard
lesson data, and creates the local demo accounts. Use `--overwrite` only when
intentionally replacing authored content. The seed does not replace unrelated
stories, students, recordings, or uploads.

## Stop, restart, and reset

Normal stop preserves the laptop database and uploads:

```powershell
docker compose -f docker-compose.dev.yml down
```

Restart after pulling code:

```powershell
git pull --ff-only
docker compose -f docker-compose.dev.yml up -d --build
```

To deliberately erase this laptop's database, uploads, and cached frontend
dependencies:

```powershell
docker compose -f docker-compose.dev.yml down -v
```

Never use `down -v` against a database containing work you want to keep.

## Run tests

The frontend tests can run in the frontend container:

```powershell
docker compose -f docker-compose.dev.yml exec frontend npm test -- --run
```

The backend container has the runtime dependencies and source mount. For the
full backend test suite, install the repository's Python test dependencies on
the laptop or add them to a development image; the normal runtime image keeps
test-only packages out.
