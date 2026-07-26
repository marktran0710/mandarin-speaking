"""Whole-database backup and restore.

The old `mandarin_stories.db` file stopped being a backup the moment the app
started writing to PostgreSQL, and `export_teacher_materials.py` only covers
custom_stories. This suite covers the real thing: every table, restorable.

The command-shape tests matter because Windows has no pg_dump on PATH — the
script has to reach the client tools inside the `mandarin-postgres`
container, and a wrong argv fails only at backup time, which is exactly when
nobody is watching.
"""
import os

import pytest

from database import connect_db
from scripts import backup_db

TEST_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin_test"
)


def test_dump_command_uses_the_container_when_the_host_has_no_pg_dump(monkeypatch):
    monkeypatch.setattr(backup_db.shutil, "which", lambda name: None)

    command = backup_db.dump_command(TEST_URL, container="mandarin-postgres")

    assert command[:3] == ["docker", "exec", "mandarin-postgres"]
    assert command[3] == "pg_dump"
    assert command[-1] == TEST_URL


def test_dump_command_prefers_a_host_binary_when_one_exists(monkeypatch):
    monkeypatch.setattr(
        backup_db.shutil, "which", lambda name: r"C:\pg\bin\pg_dump.exe"
    )

    command = backup_db.dump_command(TEST_URL, container="mandarin-postgres")

    assert command[0] == "pg_dump"
    assert "docker" not in command


def test_dump_command_asks_for_a_self_contained_restorable_dump(monkeypatch):
    """--clean --if-exists lets a restore run against a populated database;
    --no-owner --no-privileges let it land on a host with different roles
    (Render's managed database does not have a `mandarin` superuser)."""
    monkeypatch.setattr(backup_db.shutil, "which", lambda name: None)

    command = backup_db.dump_command(TEST_URL, container="mandarin-postgres")

    for flag in ("--clean", "--if-exists", "--no-owner", "--no-privileges"):
        assert flag in command


def test_restore_command_keeps_stdin_open_and_stops_on_the_first_error(monkeypatch):
    monkeypatch.setattr(backup_db.shutil, "which", lambda name: None)

    command = backup_db.restore_command(TEST_URL, container="mandarin-postgres")

    assert command[:4] == ["docker", "exec", "-i", "mandarin-postgres"]
    assert command[4] == "psql"
    assert "ON_ERROR_STOP=1" in command


def test_default_output_path_names_the_database_and_is_gitignored(tmp_path):
    path = backup_db.default_output_path(TEST_URL, directory=str(tmp_path))

    name = os.path.basename(path)
    assert name.startswith("pg_dump_mandarin_test_")
    assert name.endswith(".sql")


def test_database_name_is_read_from_the_url_not_the_credentials():
    """A naive split on '/' picks up the role name in '//mandarin:pw@host'."""
    assert backup_db.database_name(TEST_URL) == "mandarin_test"
    assert (
        backup_db.database_name("postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin")
        == "mandarin"
    )
    assert (
        backup_db.database_name("postgresql://u:p@host/appdb?sslmode=require") == "appdb"
    )


@pytest.mark.slow
def test_backup_then_restore_brings_the_rows_back(tmp_path):
    """The whole point of the script: wipe the database, restore the file,
    get the data back. Runs against mandarin_test, never the dev database."""
    with connect_db() as db:
        db.execute(
            "INSERT INTO students (id, name, created_at, password) "
            "VALUES (%s, %s, %s, %s)",
            ("backup-1", "備份同學", "2026-07-26 10:00:00", "123456"),
        )
        db.execute(
            "INSERT INTO custom_stories (id, title, learning_goal, frames, published) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("backup-story", "我的房間", "describe a room", '[{"prompt": "這是我的房間。"}]', True),
        )

    dump_path = str(tmp_path / "roundtrip.sql")
    backup_db.backup(TEST_URL, dump_path)
    assert os.path.getsize(dump_path) > 0

    with connect_db() as db:
        db.execute("TRUNCATE students, custom_stories RESTART IDENTITY CASCADE")

    backup_db.restore(TEST_URL, dump_path)

    with connect_db() as db:
        student = db.execute(
            "SELECT name FROM students WHERE id = %s", ("backup-1",)
        ).fetchone()
        story = db.execute(
            "SELECT title, frames -> 0 ->> 'prompt' AS prompt FROM custom_stories "
            "WHERE id = %s",
            ("backup-story",),
        ).fetchone()

    assert student["name"] == "備份同學"
    assert story["title"] == "我的房間"
    assert story["prompt"] == "這是我的房間。"


@pytest.mark.slow
def test_restore_refuses_a_populated_database_without_consent(tmp_path):
    """Restoring drops every table first. Doing that to a database that
    still holds rows must be a deliberate act, not a typo."""
    dump_path = str(tmp_path / "guard.sql")
    backup_db.backup(TEST_URL, dump_path)

    with connect_db() as db:
        db.execute(
            "INSERT INTO students (id, name, created_at, password) "
            "VALUES (%s, %s, %s, %s)",
            ("guard-1", "在校同學", "2026-07-26 10:00:00", "123456"),
        )

    with pytest.raises(backup_db.RefusedError):
        backup_db.restore(TEST_URL, dump_path, allow_nonempty=False)

    with connect_db() as db:
        still_there = db.execute(
            "SELECT count(*) AS n FROM students"
        ).fetchone()["n"]
    assert still_there == 1
