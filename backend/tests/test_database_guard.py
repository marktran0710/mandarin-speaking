"""The suite TRUNCATEs its database between tests, so it must only ever run
against one that is unmistakably a test database, named on purpose."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from database_guard import UnsafeTestDatabase, require_test_database_url, verify_connected_database


def _url(name: str, host: str = "127.0.0.1:5433") -> str:
    return f"postgresql://mandarin:mandarin@{host}/{name}"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_unset_test_database_url_is_refused_with_instructions(value):
    with pytest.raises(UnsafeTestDatabase, match="TEST_DATABASE_URL is not set"):
        require_test_database_url(value)


@pytest.mark.parametrize("name", ["mandarin", "postgres", "contest", "mandarin_testing", ""])
def test_a_database_not_named_as_a_test_database_is_refused(name):
    with pytest.raises(UnsafeTestDatabase, match="not named as a test database"):
        require_test_database_url(_url(name))


@pytest.mark.parametrize("host", ["127.0.0.1:5433", "127.0.0.1:5432", "db:5432", "localhost"])
@pytest.mark.parametrize("name", ["mandarin_test", "mandarin_test_perf", "test", "mandarin_verify_3b284ffe53c783f8"])
def test_a_test_database_is_accepted_on_any_host_and_port(host, name):
    # Where Postgres listens is the environment's business (5433 on a dev
    # machine, db:5432 inside Docker); only the database name is judged.
    url = _url(name, host)
    assert require_test_database_url(url) == url


def test_a_query_string_cannot_hide_the_database_name():
    with pytest.raises(UnsafeTestDatabase):
        require_test_database_url(_url("mandarin") + "?options=-csearch_path=mandarin_test")
    assert require_test_database_url(_url("mandarin_test") + "?sslmode=disable")


class _Connection:
    """Stands in for the pooled connection the TRUNCATE would run on."""

    def __init__(self, reached: str):
        self.reached = reached

    def execute(self, sql):
        assert "current_database()" in sql
        return self

    def fetchone(self):
        return {"name": self.reached}


def test_the_database_actually_reached_must_match_the_url():
    # A URL that reads like a test database proves nothing if the pool landed elsewhere.
    with pytest.raises(UnsafeTestDatabase, match="mandarin"):
        verify_connected_database(_Connection("mandarin"), _url("mandarin_test"))


def test_the_database_actually_reached_must_itself_be_a_test_database():
    with pytest.raises(UnsafeTestDatabase, match="not named as a test database"):
        verify_connected_database(_Connection("mandarin"), _url("mandarin"))


def test_a_connection_to_the_named_test_database_passes():
    verify_connected_database(_Connection("mandarin_test"), _url("mandarin_test"))


def test_the_suite_stops_before_any_test_when_pointed_at_a_non_test_database():
    """End to end through conftest, with a URL that cannot connect anywhere:
    if the guard were missing the run would fail on the connection instead."""
    env = {**os.environ, "TEST_DATABASE_URL": _url("mandarin", "127.0.0.1:1")}
    backend = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_database_guard.py", "-k", "accepted_on_any_host",
         "-p", "no:cacheprovider", "-q"],
        cwd=backend, env=env, capture_output=True, text=True, timeout=180,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 2, output
    assert "Refusing to run the suite" in output and "not named as a test database" in output
    assert "passed" not in output
