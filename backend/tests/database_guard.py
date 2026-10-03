"""Refuse to run the suite against a database it should not wipe.

conftest.py TRUNCATEs every application table between tests, so the target
must be named on purpose and be unmistakably a test database. Nothing here
depends on where Postgres listens: 5433 on a dev machine, ``db:5432`` inside
Docker, whatever CI provides. Only the database name is judged.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

ENV_VAR = "TEST_DATABASE_URL"

# `mandarin_test`, `mandarin_test_perf` and `test`; not `mandarin`, `contest`
# or `mandarin_testing`.
_TEST_NAME = re.compile(r"(^|[_-])test($|[_-])")
# scripts/verify_learning_engine.py creates, migrates and drops one of these
# itself, then points this suite at it.
_THROWAWAY_PREFIX = "mandarin_verify_"


class UnsafeTestDatabase(RuntimeError):
    """The configured database is not one the suite may truncate."""


def is_test_database_name(name: str) -> bool:
    return bool(_TEST_NAME.search(name)) or name.startswith(_THROWAWAY_PREFIX)


def _database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def require_test_database_url(url: str | None) -> str:
    """Return ``url`` if it names a test database, else say how to fix it."""
    if not url or not url.strip():
        raise UnsafeTestDatabase(
            f"{ENV_VAR} is not set. The suite truncates every table, so it takes no default. "
            f"Set it to a dedicated test database, e.g. postgresql://mandarin:mandarin@127.0.0.1:5433/mandarin_test "
            "(host and port are wherever your Postgres listens), in backend/.env or the environment."
        )
    url = url.strip()
    name = _database_name(url)
    if not is_test_database_name(name):
        raise UnsafeTestDatabase(
            f"{ENV_VAR} points at database {name!r}, which is not named as a test database "
            "(it needs a `test` word in its name, such as mandarin_test). The suite truncates every table."
        )
    return url


def verify_connected_database(conn: Any, url: str) -> None:
    """Check what the pool actually reached, not just what the URL says."""
    expected = _database_name(url)
    actual = conn.execute("SELECT current_database() AS name").fetchone()["name"]
    if actual != expected:
        raise UnsafeTestDatabase(
            f"{ENV_VAR} names database {expected!r} but the connection reached {actual!r}."
        )
    if not is_test_database_name(actual):
        raise UnsafeTestDatabase(f"Connected database {actual!r} is not named as a test database.")
