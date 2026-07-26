"""Whole-database backup and restore for the PostgreSQL database.

Usage (from backend/):
    python -m scripts.backup_db                       # dump the dev database
    python -m scripts.backup_db --output before.sql
    python -m scripts.backup_db --restore before.sql  # restore into an empty db
    python -m scripts.backup_db --restore before.sql --yes   # ... or a full one

    # Point at any other database, including a managed one:
    python -m scripts.backup_db --url "$RENDER_DATABASE_URL"

Windows has no pg_dump on PATH, so by default both commands run through the
`mandarin-postgres` container, which ships the matching PostgreSQL 17 client
tools and can reach remote databases just as well as the local one. A host
pg_dump/psql is used instead when one is installed.

This replaces `mandarin_stories.db` as the project's backup: that file stopped
being current the moment the app moved to PostgreSQL, and
`export_teacher_materials.py` only covers custom_stories and their images.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402

DEFAULT_URL = os.getenv(
    "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
)
DEFAULT_CONTAINER = os.getenv("PG_CONTAINER", "mandarin-postgres")
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --clean --if-exists      restorable over a database that still has tables
# --no-owner --no-privileges   restorable onto a host with different roles,
#                              e.g. Render's managed database has no
#                              `mandarin` superuser
DUMP_FLAGS = ["--clean", "--if-exists", "--no-owner", "--no-privileges"]

# The application tables. alembic_version is deliberately excluded from the
# emptiness check — a freshly migrated database has one row in it and is still
# empty for our purposes.
APP_TABLES = (
    "audio_records",
    "custom_stories",
    "help_requests",
    "story_submissions",
    "students",
    "vocab_quiz_attempts",
)


class BackupError(RuntimeError):
    """pg_dump or psql exited non-zero."""


class RefusedError(RuntimeError):
    """A restore would have dropped tables that still hold rows."""


def database_name(url: str) -> str:
    """The database a connection string points at.

    Parsed rather than split on '/' — in
    `postgresql://mandarin:pw@host/mandarin_test` a naive split also matches
    the role name, and a trailing `?sslmode=require` would end up in the
    filename.
    """
    return urlparse(url).path.lstrip("/")


def default_output_path(url: str, directory: str | None = None) -> str:
    """`pg_dump_<database>_<timestamp>.sql` — .gitignore already covers
    `backend/pg_dump_*.sql`, so a stray dump never lands in a commit."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"pg_dump_{database_name(url)}_{stamp}.sql"
    return os.path.join(directory or BACKEND_DIR, name)


def dump_command(url: str, container: str = DEFAULT_CONTAINER) -> list[str]:
    if shutil.which("pg_dump"):
        return ["pg_dump", *DUMP_FLAGS, url]
    return ["docker", "exec", container, "pg_dump", *DUMP_FLAGS, url]


def restore_command(url: str, container: str = DEFAULT_CONTAINER) -> list[str]:
    # -i keeps stdin attached so the dump can be piped in. ON_ERROR_STOP=1
    # turns a half-applied restore into a loud failure instead of a database
    # that is silently missing three tables.
    flags = ["--set", "ON_ERROR_STOP=1", "--quiet", url]
    if shutil.which("psql"):
        return ["psql", *flags]
    return ["docker", "exec", "-i", container, "psql", *flags]


def _row_count(url: str) -> int:
    counts = " + ".join(f"(SELECT count(*) FROM {table})" for table in APP_TABLES)
    with psycopg.connect(url, connect_timeout=10) as connection:
        return connection.execute(f"SELECT {counts} AS n").fetchone()[0]


def backup(
    url: str = DEFAULT_URL,
    output_path: str | None = None,
    container: str = DEFAULT_CONTAINER,
) -> str:
    """Writes a plain-SQL dump of `url` and returns the file path."""
    output_path = output_path or default_output_path(url)
    command = dump_command(url, container)
    # Binary mode: pg_dump emits UTF-8, and letting Windows re-encode it
    # through the console codepage would corrupt every Chinese title.
    with open(output_path, "wb") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise BackupError(
            f"pg_dump failed ({result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return output_path


def restore(
    url: str,
    input_path: str,
    container: str = DEFAULT_CONTAINER,
    allow_nonempty: bool = False,
) -> None:
    """Applies a dump to `url`, dropping the existing tables first."""
    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)

    if not allow_nonempty:
        existing = _row_count(url)
        if existing:
            raise RefusedError(
                f"{database_name(url)} still holds {existing} rows — a restore "
                "drops every table first. Re-run with --yes to overwrite it."
            )

    command = restore_command(url, container)
    with open(input_path, "rb") as handle:
        result = subprocess.run(command, stdin=handle, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise BackupError(
            f"psql failed ({result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="connection string")
    parser.add_argument("--output", help="dump file to write")
    parser.add_argument("--restore", metavar="FILE", help="restore this dump instead")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="allow restoring over a database that still holds rows",
    )
    args = parser.parse_args()

    name = database_name(args.url)
    if args.restore:
        print(f"Restoring {args.restore} -> {name}")
        restore(args.url, args.restore, args.container, allow_nonempty=args.yes)
        print(f"Restored. {_row_count(args.url)} rows across {len(APP_TABLES)} tables.")
    else:
        path = backup(args.url, args.output, args.container)
        size_kb = os.path.getsize(path) / 1024
        print(f"Dumped {name} ({_row_count(args.url)} rows) -> {path} [{size_kb:.0f} KB]")


if __name__ == "__main__":
    main()
