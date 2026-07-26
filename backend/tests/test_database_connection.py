"""Confirms the app can reach the local PostgreSQL container.

This is the one test that talks to the *dev* database rather than the
isolated test database — it exists to catch "the container isn't running"
before every other DB test fails with a confusing error.
"""
import os

import psycopg
import pytest


def test_postgres_is_reachable():
    url = os.getenv(
        "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
    )
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            version = conn.execute("SELECT version()").fetchone()[0]
    except psycopg.OperationalError as exc:
        pytest.fail(f"Cannot reach PostgreSQL at {url} — is `docker compose up -d db` running? {exc}")
    assert "PostgreSQL 17" in version


def test_test_database_exists():
    url = os.getenv(
        "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
    )
    # Swap only the trailing database name, not every "mandarin" substring —
    # a naive str.replace("/mandarin", ...) also corrupts the "mandarin" in
    # the username/password portion of the URL.
    base, _, _ = url.rpartition("/")
    url = f"{base}/mandarin_test"
    with psycopg.connect(url, connect_timeout=5) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
    assert name == "mandarin_test"
