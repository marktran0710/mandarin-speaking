# Lab server (Tailscale-shared backend)

This machine can run the backend as a **shared Lab server**, reachable by other
devices (laptops, phones) over Tailscale even when they're off the local
network. This doc exists because an agent killed the live Lab server by
mistake while looking for a free dev port — see "Before touching port 8000"
below.

## How it works

There is no special Tailscale config in this repo. Tailscale runs as an
always-on OS-level VPN service on this machine and already assigns it a
stable Tailscale IP (currently `100.67.229.122`, see `start.ps1`'s
`$LabBackendUrl` default). `start.ps1 -Mode Lab` just starts the backend bound
to `0.0.0.0:8000` (all interfaces, not just `127.0.0.1`) so anything already
reachable via that Tailscale IP - including port 8000 - can reach it. Nothing
needs to be configured or started on the Tailscale side itself.

## Starting / restarting the Lab server

```powershell
.\start.ps1 -Mode Lab
```

This is idempotent for the database (`docker compose up -d db` is a no-op if
already running) and opens two new PowerShell windows: one running the
backend (`uvicorn main:app --host 0.0.0.0 --reload --port 8000`), one running
the frontend (`npm run dev -- --host 0.0.0.0`). Closing those windows (or
Ctrl+C inside them) stops each half; there's no background service to manage
separately.

If you only need to confirm it's alive:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing
```

A laptop/remote client joins with:

```powershell
.\start.ps1 -Mode Laptop
```

which starts only the frontend, pointed at `$LabBackendUrl` (default
`http://100.67.229.122:8000`) instead of a local backend.

## Database port note (2026-08-19)

`docker-compose.yml` binds Postgres to host port **5433**, not the Postgres
default 5432 - another project's container (`vstep_postgres`) already holds
5432 on this shared machine. `backend/.env` sets `DATABASE_URL` /
`TEST_DATABASE_URL` to match. `database.py` and `tests/conftest.py` both call
`load_dotenv()` at their own top (before they read those env vars), so this
works automatically with plain `start.ps1 -Mode Lab` - no manual env
exporting needed. If this machine's port conflict is ever resolved and you
want to move back to 5432, update `docker-compose.yml`'s port mapping and
`backend/.env`'s two `DATABASE_URL`/`TEST_DATABASE_URL` lines together.

## Before touching port 8000

**Check for live remote connections before killing anything on this port.**
`netstat -ano | findstr :8000` (or `netstat -ano | grep :8000` in a POSIX
shell) - if you see `ESTABLISHED` connections from a Tailscale IP
(`100.67.229.122`, or `100.x.x.x` generally) or any non-localhost address,
that is very likely the live Lab server with a real remote client attached,
not a leftover dev process. Killing it drops whoever is connected mid-session.
When in doubt, ask before killing anything on 8000 - restarting it correctly
requires `start.ps1 -Mode Lab`'s exact CORS/env setup, which a quick manual
`uvicorn` relaunch will not reproduce.

For your own throwaway dev/testing needs, run a backend on a **different**
port (e.g. `--port 8001`) instead of reusing 8000.
