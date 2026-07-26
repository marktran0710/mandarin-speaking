"""Guards the cut-over: a stray sqlite3 import means a code path is still
writing to the old file, where nobody will ever see the data again."""
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The one legitimate reader of the legacy file.
ALLOWED = {os.path.join("scripts", "migrate_sqlite_to_postgres.py")}

SKIP_DIRS = {"__pycache__", ".pytest_cache", "migrations", "tests", ".venv", "uploads"}


def _python_files():
    for root, dirs, files in os.walk(BACKEND_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                yield path, os.path.relpath(path, BACKEND_DIR)


def test_no_sqlite3_imports_outside_the_migration_script():
    offenders = []
    for path, relative in _python_files():
        if relative.replace("\\", "/") in {a.replace("\\", "/") for a in ALLOWED}:
            continue
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        if "import sqlite3" in source:
            offenders.append(relative)
    assert offenders == [], f"sqlite3 still imported in: {offenders}"


def test_no_database_path_env_var_remains():
    offenders = []
    for path, relative in _python_files():
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        if "DATABASE_PATH" in source:
            offenders.append(relative)
    assert offenders == [], f"DATABASE_PATH still referenced in: {offenders}"


def test_no_question_mark_placeholders_remain():
    """psycopg3 accepts only %s — a leftover ? placeholder is a runtime
    ProgrammingError on a code path no test happens to cover."""
    import re

    pattern = re.compile(r"(VALUES\s*\([^)]*\?)|(=\s*\?)|(LIMIT \? OFFSET \?)")
    offenders = []
    for path, relative in _python_files():
        if relative.replace("\\", "/") in {a.replace("\\", "/") for a in ALLOWED}:
            continue
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        if pattern.search(source):
            offenders.append(relative)
    assert offenders == [], f"SQLite-style ? placeholders remain in: {offenders}"
