# PostgreSQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all 6 tables out of the embedded SQLite file into a local PostgreSQL 17 container, rewrite every backend query against psycopg3, and rebuild the materials (`custom_stories`) CRUD on JSONB.

**Architecture:** PostgreSQL runs as a Docker Compose service with a named volume. `backend/database.py` keeps its existing `connect_db()` context-manager shape — psycopg3's `Connection.execute()` returns a cursor, so the ~40 `db.execute(...).fetchall()` call sites keep working — but swaps the driver, the row factory (`dict_row`), and the placeholder style (`?` → `%s`). Schema stops being created by the hand-rolled `ensure_column()` at startup and moves to Alembic. The six JSON `TEXT` columns become `JSONB`, so `row_to_*()` helpers stop calling `json.loads` and writes pass `Jsonb(...)`. SQLite support is removed entirely; the existing `.db` file stays on disk untouched as a backup.

**Tech Stack:** PostgreSQL 17 (Docker), psycopg 3 + psycopg_pool, Alembic, FastAPI, pytest.

## Global Constraints

- **Postgres version:** 17 (`postgres:17-alpine`). Container name `mandarin-postgres`, host port `5432`.
- **Databases:** `mandarin` (dev) and `mandarin_test` (pytest). Same role `mandarin` / password `mandarin`. Local trusted LAN only — matches the project's existing plaintext-password posture; do not add secret management.
- **Connection string env var:** `DATABASE_URL`, default `postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin`. The old `DATABASE_PATH` env var is deleted everywhere.
- **Placeholders:** psycopg3 accepts **only** `%s`. Every `?` in SQL becomes `%s`. Any literal `%` inside SQL must be doubled to `%%`.
- **Row access stays dict-style:** `row["column_name"]`, and `"col" in row.keys()` guards keep working because `dict_row` returns real dicts. Do not switch to tuple indexing.
- **API response shapes must not change.** The frontend (`src/services/database.ts`, `src/utils/teacherStories.ts`) is not modified by this plan. In particular:
  - `created_at` / `timestamp` / `submitted_at` / `completed_at` / `createdAt` stay **TEXT**, not `timestamptz`. DB-generated defaults must produce the byte-identical SQLite format `YYYY-MM-DD HH:MM:SS` so `ORDER BY created_at DESC` still sorts correctly across migrated and new rows.
  - Nested JSON-**strings**-inside-JSON stay strings. `frame["vocabularyDistractors"]`, `vocabularyCloze`, `vocabularySynonym`, `vocabularyLookalike` are `json.dumps`-ed strings *inside* the frames array, because the frontend does `JSON.parse(frame.vocabularyDistractors)`. Only the **outer** column becomes JSONB. Do not "helpfully" unwrap them.
- **No ORM.** Raw SQL, same style as the current code.
- **`frames` stays one JSONB column.** No `story_frames` table.
- **Commit after every task.** Branch: work on the current `story/lesson-05-book-mode` branch unless told otherwise.

## Two pre-existing bugs this migration fixes (do not treat as regressions)

1. **`INSERT OR REPLACE` silently wipes columns.** In SQLite it is DELETE+INSERT. `routers/stories.py:40` lists only 9 of `custom_stories`' 11 columns, so **every teacher re-save of a story wipes `quiz_exclusions` and resets `created_at`** (which also reshuffles the list order). `ON CONFLICT (id) DO UPDATE SET` only touches the listed columns, so this stops happening. Task 5 has an explicit regression test.
2. **Tests write to the real dev database.** Only `test_quiz_exclusions.py` and `test_students_login.py` point `DATABASE_PATH` at a tmp file; every other test hits `backend/mandarin_stories.db`. There are **29 junk test rows** in `vocab_quiz_attempts` right now. Task 3 adds an autouse fixture that routes all tests at `mandarin_test` and truncates between tests.

---

### Task 1: PostgreSQL container + connection config

**Files:**
- Create: `docker-compose.yml` (repo root)
- Create: `backend/db_init/01-create-test-db.sql`
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`
- Modify: `.gitignore`
- Test: `backend/tests/test_database_connection.py`

**Interfaces:**
- Produces: env var `DATABASE_URL`; a running Postgres on `127.0.0.1:5432` with databases `mandarin` and `mandarin_test`.

- [ ] **Step 1: Write `docker-compose.yml` at the repo root**

```yaml
# Local PostgreSQL for the mandarin-speaking backend.
#   docker compose up -d db      -> start
#   docker compose down          -> stop (data survives in the named volume)
#   docker compose down -v       -> stop AND wipe all data
services:
  db:
    image: postgres:17-alpine
    container_name: mandarin-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: mandarin
      POSTGRES_PASSWORD: mandarin
      POSTGRES_DB: mandarin
      # Deterministic collation so ORDER BY on Chinese/ASCII text behaves the
      # same on every machine regardless of the host locale.
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"
    ports:
      - "5432:5432"
    volumes:
      - mandarin_pgdata:/var/lib/postgresql/data
      # Scripts in this directory run once, on first initialisation of an
      # empty data volume.
      - ./backend/db_init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mandarin -d mandarin"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  mandarin_pgdata:
```

- [ ] **Step 2: Write the test-database bootstrap script**

Create `backend/db_init/01-create-test-db.sql`:

```sql
-- pytest runs against its own database so tests can TRUNCATE freely without
-- touching development data. See backend/tests/conftest.py.
CREATE DATABASE mandarin_test OWNER mandarin;
```

- [ ] **Step 3: Add the driver dependencies**

In `backend/requirements.txt`, add these three lines directly after `python-dotenv==1.0.0`:

```
psycopg[binary]==3.2.3
psycopg-pool==3.2.4
alembic==1.14.0
```

- [ ] **Step 4: Document the connection string**

Append to `backend/.env.example`:

```
# Local PostgreSQL (docker compose up -d db). Override in .env if your
# container maps a different port.
DATABASE_URL=postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin
```

Append to `.gitignore`, directly after the `backend/*.db.bak*` line:

```
backend/pg_dump_*.sql
```

- [ ] **Step 5: Start the container and verify it is healthy**

```bash
docker compose up -d db
docker compose ps
```

Expected: service `db` shows state `running (healthy)` within ~15 seconds. If it shows `unhealthy`, run `docker compose logs db` before continuing.

- [ ] **Step 6: Write the failing connection test**

Create `backend/tests/test_database_connection.py`:

```python
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
    # Swap only the trailing database name. A plain str.replace of
    # "/mandarin" would also rewrite the username in "//mandarin:...".
    head, _, _ = url.rpartition("/")
    url = f"{head}/mandarin_test"
    with psycopg.connect(url, connect_timeout=5) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
    assert name == "mandarin_test"
```

- [ ] **Step 7: Install deps and run the test**

```bash
cd backend && pip install -r requirements.txt
python -m pytest tests/test_database_connection.py -v
```

Expected: both tests PASS. (They pass immediately — this task is infrastructure, and the test is the verification that the infrastructure is real.)

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml backend/db_init/01-create-test-db.sql backend/requirements.txt backend/.env.example .gitignore backend/tests/test_database_connection.py
git commit -m "chore(db): add local PostgreSQL 17 container and psycopg3 deps"
```

---

### Task 2: Alembic schema (initial migration)

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/migrations/versions/0001_initial_schema.py`
- Test: `backend/tests/test_schema.py`

**Interfaces:**
- Consumes: `DATABASE_URL` from Task 1.
- Produces: 6 tables in both `mandarin` and `mandarin_test`. Column types later tasks rely on:
  - `custom_stories(id text pk, title text, learning_goal text, frames jsonb, published boolean, created_at text, linear boolean, lesson_number integer, narrative_mode text, first_frame_is_example boolean, quiz_exclusions jsonb)`
  - `audio_records(..., praat_metrics jsonb, created_at text)`
  - `story_submissions(..., scenes jsonb, concatenated_audio_url text, story_feedback jsonb, created_at text)`
  - `vocab_quiz_attempts(..., question_results jsonb, mode text, student_id text, created_at text)`
  - `students(id text pk, name text unique, created_at text, password text)`
  - `help_requests(id text pk, student_name text, message text, status text, created_at text, resolved_at text)`
- Produces: `alembic upgrade head` / `alembic downgrade base` as the only schema mechanism.

- [ ] **Step 1: Scaffold Alembic**

```bash
cd backend && python -m alembic init migrations
```

This writes `backend/alembic.ini`, `backend/migrations/env.py`, and `backend/migrations/script.py.mako`. Delete the generated `backend/migrations/versions/` contents if any exist.

- [ ] **Step 2: Point Alembic at `DATABASE_URL`**

In `backend/alembic.ini`, replace the generated `sqlalchemy.url = driver://user:pass@localhost/dbname` line with an empty value (the URL comes from the environment instead):

```ini
sqlalchemy.url =
```

Then replace the whole body of `backend/migrations/env.py` with:

```python
"""Alembic environment — reads DATABASE_URL from the environment so the same
migrations run against the dev database and the pytest database."""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
)
# SQLAlchemy (used by Alembic only, not by the app) needs the +psycopg driver
# tag to pick psycopg3 over the absent psycopg2.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1))

# No ORM models in this project — migrations are hand-written SQL/ops.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Add `sqlalchemy>=2.0` to `backend/requirements.txt` (Alembic requires it even though the app does not use it), then `pip install -r requirements.txt`.

- [ ] **Step 3: Write the initial migration**

Create `backend/migrations/versions/0001_initial_schema.py`:

```python
"""Initial schema — the six tables migrated off SQLite.

Design notes:
  * Timestamp-ish columns stay TEXT. Most are client-supplied ISO strings
    already; the DB-generated created_at defaults reproduce SQLite's exact
    'YYYY-MM-DD HH:MM:SS' format so ORDER BY created_at DESC keeps sorting
    migrated rows and new rows in one consistent sequence.
  * The JSON columns become JSONB (validated on write, indexable, and
    directly updatable with jsonb_set).
  * published/linear/first_frame_is_example become real BOOLEANs; the
    row_to_* helpers already wrap them in bool() so the API shape is
    unchanged.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Byte-identical to SQLite's CURRENT_TIMESTAMP output.
SQLITE_STYLE_NOW = sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


def upgrade() -> None:
    op.create_table(
        "audio_records",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("duration", sa.Integer, nullable=False),
        sa.Column("transcription", sa.Text, nullable=False, server_default=""),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("topic_id", sa.Text),
        sa.Column("image_url", sa.Text),
        sa.Column("image_index", sa.Integer),
        sa.Column("audio_url", sa.Text),
        sa.Column("praat_metrics", postgresql.JSONB),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
    )
    op.create_index("ix_audio_records_created_at", "audio_records", [sa.text("created_at DESC")])

    op.create_table(
        "custom_stories",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("learning_goal", sa.Text, nullable=False),
        sa.Column("frames", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        sa.Column("linear", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("lesson_number", sa.Integer),
        sa.Column("narrative_mode", sa.Text, nullable=False, server_default="story"),
        sa.Column("first_frame_is_example", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("quiz_exclusions", postgresql.JSONB),
    )
    # The student topic list filters on published, then groups by lesson.
    op.create_index(
        "ix_custom_stories_published_lesson",
        "custom_stories",
        ["published", "lesson_number"],
    )
    # Lets analytics reach into frames (e.g. which stories contain a word)
    # without deserialising every 34 KB blob in Python.
    op.create_index(
        "ix_custom_stories_frames_gin",
        "custom_stories",
        ["frames"],
        postgresql_using="gin",
    )

    op.create_table(
        "help_requests",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("student_name", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("resolved_at", sa.Text),
    )

    op.create_table(
        "story_submissions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("story_id", sa.Text, nullable=False),
        sa.Column("story_title", sa.Text, nullable=False),
        sa.Column("student_name", sa.Text, nullable=False),
        sa.Column("submitted_at", sa.Text, nullable=False),
        sa.Column("scenes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        sa.Column("concatenated_audio_url", sa.Text),
        sa.Column("story_feedback", postgresql.JSONB),
    )
    op.create_index("ix_story_submissions_story_id", "story_submissions", ["story_id"])

    op.create_table(
        "vocab_quiz_attempts",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("story_id", sa.Text, nullable=False),
        sa.Column("student_name", sa.Text, nullable=False),
        sa.Column("completed_at", sa.Text, nullable=False),
        sa.Column("total_questions", sa.Integer, nullable=False),
        sa.Column("correct_count", sa.Integer, nullable=False),
        sa.Column("total_time_ms", sa.Integer, nullable=False),
        sa.Column("question_results", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        sa.Column("mode", sa.Text),
        # Deliberately NOT a foreign key to students.id: legacy attempts
        # recorded before the roster existed carry NULL or a stale id, and a
        # constraint would reject the historical data this app still analyses.
        sa.Column("student_id", sa.Text),
    )
    op.create_index(
        "ix_vocab_quiz_attempts_story_student",
        "vocab_quiz_attempts",
        ["story_id", "student_id"],
    )

    op.create_table(
        "students",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        # Plaintext by design — a classroom friction gate, not a security
        # boundary. Carried over verbatim from the SQLite schema.
        sa.Column("password", sa.Text, nullable=False, server_default="123456"),
    )
    # The roster lookup is case-insensitive (SQLite used COLLATE NOCASE);
    # Postgres has no such collation, so queries use lower(name) and this
    # index makes them cheap.
    op.create_index("ix_students_lower_name", "students", [sa.text("lower(name)")])


def downgrade() -> None:
    op.drop_table("students")
    op.drop_table("vocab_quiz_attempts")
    op.drop_table("story_submissions")
    op.drop_table("help_requests")
    op.drop_table("custom_stories")
    op.drop_table("audio_records")
```

- [ ] **Step 4: Apply the migration to both databases**

```bash
cd backend
python -m alembic upgrade head
DATABASE_URL=postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin_test python -m alembic upgrade head
```

Expected: `Running upgrade  -> 0001, Initial schema` twice, no errors.

On Windows PowerShell the second line is:

```powershell
$env:DATABASE_URL="postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin_test"; python -m alembic upgrade head; $env:DATABASE_URL=$null
```

- [ ] **Step 5: Write the schema assertion test**

Create `backend/tests/test_schema.py`:

```python
"""Locks the migrated schema: table set, the JSONB columns the row_to_*
helpers depend on, and the boolean columns the API wraps in bool()."""
import os

import psycopg
import pytest

TEST_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin_test"
)

EXPECTED_TABLES = {
    "audio_records",
    "custom_stories",
    "help_requests",
    "story_submissions",
    "students",
    "vocab_quiz_attempts",
}

JSONB_COLUMNS = [
    ("custom_stories", "frames"),
    ("custom_stories", "quiz_exclusions"),
    ("story_submissions", "scenes"),
    ("story_submissions", "story_feedback"),
    ("vocab_quiz_attempts", "question_results"),
    ("audio_records", "praat_metrics"),
]

BOOLEAN_COLUMNS = [
    ("custom_stories", "published"),
    ("custom_stories", "linear"),
    ("custom_stories", "first_frame_is_example"),
]


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(TEST_URL) as connection:
        yield connection


def test_all_tables_exist(conn):
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    names = {row[0] for row in rows}
    assert EXPECTED_TABLES <= names


@pytest.mark.parametrize("table,column", JSONB_COLUMNS)
def test_json_columns_are_jsonb(conn, table, column):
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    assert row is not None, f"{table}.{column} is missing"
    assert row[0] == "jsonb"


@pytest.mark.parametrize("table,column", BOOLEAN_COLUMNS)
def test_flag_columns_are_boolean(conn, table, column):
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    assert row is not None, f"{table}.{column} is missing"
    assert row[0] == "boolean"


def test_created_at_default_matches_sqlite_format(conn):
    """ORDER BY created_at DESC is lexicographic on TEXT — new rows must use
    the same 'YYYY-MM-DD HH:MM:SS' shape as the rows migrated from SQLite."""
    value = conn.execute(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'custom_stories' AND column_name = 'created_at'"
    ).fetchone()[0]
    assert "YYYY-MM-DD HH24:MI:SS" in value
```

- [ ] **Step 6: Run the schema test**

```bash
cd backend && python -m pytest tests/test_schema.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic.ini backend/migrations backend/requirements.txt backend/tests/test_schema.py
git commit -m "feat(db): add Alembic with the initial PostgreSQL schema"
```

---

### Task 3: Rewrite `database.py` for psycopg3 + isolate the test database

**Files:**
- Modify: `backend/database.py` (full rewrite)
- Modify: `backend/tests/conftest.py:62-69`
- Modify: `backend/tests/test_quiz_exclusions.py:16-17`
- Modify: `backend/tests/test_students_login.py:18-19`
- Test: `backend/tests/test_row_mappers.py`

**Interfaces:**
- Consumes: the schema from Task 2.
- Produces:
  - `connect_db()` — context manager yielding a `psycopg.Connection` with `dict_row`; commits on clean exit, rolls back on exception. `db.execute(sql, params)` returns a cursor, so `.fetchone()` / `.fetchall()` keep working.
  - `init_db()` — now only opens the connection pool and verifies connectivity. It no longer creates tables.
  - `close_db()` — closes the pool (called on FastAPI shutdown).
  - `row_to_audio_record`, `row_to_custom_story`, `row_to_story_submission`, `row_to_help_request`, `row_to_vocab_quiz_attempt`, `row_to_student` — unchanged signatures `(row: dict) -> dict`, unchanged output shape, but they no longer call `json.loads` on the JSONB columns.
  - `ensure_column` and `ensure_column_dropped` are **deleted** (Alembic owns schema now).
  - pytest fixture `db_url` and autouse fixture `clean_database` in `conftest.py`.

- [ ] **Step 1: Write the failing row-mapper test**

Create `backend/tests/test_row_mappers.py`:

```python
"""The row_to_* helpers used to json.loads() TEXT columns. With JSONB,
psycopg hands back already-parsed Python objects — these tests pin that the
helpers pass them through instead of double-parsing (which raises TypeError
on a dict), and that the API-facing shape is unchanged."""
import pytest

import database


def test_row_to_custom_story_passes_through_parsed_jsonb():
    row = {
        "id": "s1",
        "title": "我的房間",
        "learning_goal": "describe a room",
        "frames": [{"prompt": "這是我的房間。", "vocabulary": "房間"}],
        "published": True,
        "linear": False,
        "lesson_number": 5,
        "narrative_mode": "story",
        "first_frame_is_example": False,
        "quiz_exclusions": [{"word": "房間", "kind": "cloze"}],
    }
    result = database.row_to_custom_story(row)
    assert result["frames"] == [{"prompt": "這是我的房間。", "vocabulary": "房間"}]
    assert result["published"] is True
    assert result["linear"] is False
    assert result["lessonNumber"] == 5
    assert result["quizExclusions"] == [{"word": "房間", "kind": "cloze"}]


def test_row_to_custom_story_handles_null_jsonb():
    row = {
        "id": "s2",
        "title": "t",
        "learning_goal": "g",
        "frames": None,
        "published": False,
        "linear": False,
        "lesson_number": None,
        "narrative_mode": "story",
        "first_frame_is_example": False,
        "quiz_exclusions": None,
    }
    result = database.row_to_custom_story(row)
    assert result["frames"] == []
    assert result["quizExclusions"] == []


def test_row_to_story_submission_shape():
    row = {
        "id": "sub1",
        "story_id": "teacher-s1",
        "story_title": "我的房間",
        "student_name": "Mai",
        "submitted_at": "2026-07-26T08:00:00Z",
        "scenes": [{"sceneIndex": 0, "transcription": "你好"}],
        "concatenated_audio_url": "/uploads/story_audio/sub1.wav",
        "story_feedback": {"overall": 7},
    }
    result = database.row_to_story_submission(row)
    assert result["scenes"] == [{"sceneIndex": 0, "transcription": "你好"}]
    assert result["storyFeedback"] == {"overall": 7}
    assert result["concatenatedAudioUrl"] == "/uploads/story_audio/sub1.wav"


def test_row_to_vocab_quiz_attempt_shape():
    row = {
        "id": "a1",
        "story_id": "teacher-s1",
        "student_name": "Mai",
        "student_id": "stu-1",
        "mode": "tier2",
        "completed_at": "2026-07-26T08:00:00Z",
        "total_questions": 10,
        "correct_count": 8,
        "total_time_ms": 42000,
        "question_results": [{"word": "房間", "correct": True, "timeMs": 1200}],
    }
    result = database.row_to_vocab_quiz_attempt(row)
    assert result["questionResults"] == [{"word": "房間", "correct": True, "timeMs": 1200}]
    assert result["totalQuestions"] == 10


def test_row_to_audio_record_shape():
    row = {
        "id": "r1",
        "timestamp": "2026-07-26T08:00:00Z",
        "duration": 3000,
        "transcription": "你好",
        "model": "whisper",
        "topic_id": "teacher-s1",
        "image_url": "/uploads/images/a.png",
        "image_index": 0,
        "audio_url": "/uploads/audio/r1.wav",
        "praat_metrics": {"toneAccuracy": 0.8},
    }
    result = database.row_to_audio_record(row)
    assert result["praatMetrics"] == {"toneAccuracy": 0.8}
    assert result["topicId"] == "teacher-s1"


def test_ensure_column_helpers_are_gone():
    """Alembic owns the schema now — a leftover ensure_column() would create
    a second, silent migration path that Alembic doesn't know about."""
    assert not hasattr(database, "ensure_column")
    assert not hasattr(database, "ensure_column_dropped")
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
cd backend && python -m pytest tests/test_row_mappers.py -v
```

Expected: FAIL — `row_to_custom_story` raises `TypeError: the JSON object must be str, bytes or bytearray, not list`, and `test_ensure_column_helpers_are_gone` fails because the helpers still exist.

- [ ] **Step 3: Replace `backend/database.py` entirely**

```python
import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
)

_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
_DB_TIMEOUT = float(os.getenv("DB_TIMEOUT_SECONDS", "10"))

# open=False so importing this module never blocks on a database that isn't
# up yet — init_db() opens it at FastAPI startup, and tests re-point it at
# the test database before opening.
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=_POOL_MIN,
            max_size=_POOL_MAX,
            timeout=_DB_TIMEOUT,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        _pool.open()
    return _pool


@contextmanager
def connect_db() -> Iterator[psycopg.Connection]:
    """Hands out a pooled connection inside a transaction.

    psycopg3's Connection.execute() creates a cursor and runs the statement,
    so call sites keep the `db.execute(sql, params).fetchall()` shape they
    had under sqlite3. The pool's context manager commits on a clean exit and
    rolls back if the body raises.
    """
    with _get_pool().connection() as connection:
        yield connection


def init_db() -> None:
    """Opens the pool and fails loudly if the database is unreachable.

    Schema creation lives in Alembic (`python -m alembic upgrade head`) —
    this function no longer creates or alters tables.
    """
    with connect_db() as db:
        db.execute("SELECT 1").fetchone()


def close_db() -> None:
    """Closes the pool on application shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def reset_pool_for_tests(database_url: str) -> None:
    """Re-points the pool at another database (the pytest database).

    Tests must never share a connection pool with the development database —
    the suite truncates every table between tests.
    """
    global DATABASE_URL
    close_db()
    DATABASE_URL = database_url


def row_to_audio_record(row: dict) -> dict:
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "duration": row["duration"],
        "transcription": row["transcription"],
        "model": row["model"],
        "topicId": row["topic_id"],
        "imageUrl": row["image_url"],
        "imageIndex": row["image_index"],
        "audioUrl": row["audio_url"],
        # JSONB: psycopg already parsed this.
        "praatMetrics": row["praat_metrics"],
    }


def row_to_story_submission(row: dict) -> dict:
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "storyTitle": row["story_title"],
        "studentName": row["student_name"],
        "submittedAt": row["submitted_at"],
        "scenes": row["scenes"] or [],
        "concatenatedAudioUrl": row.get("concatenated_audio_url"),
        "storyFeedback": row.get("story_feedback"),
    }


def row_to_custom_story(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "learningGoal": row["learning_goal"],
        "frames": row["frames"] or [],
        "published": bool(row["published"]),
        "linear": bool(row["linear"]),
        "lessonNumber": row["lesson_number"],
        "narrativeMode": row["narrative_mode"],
        "firstFrameIsExample": bool(row["first_frame_is_example"]),
        "quizExclusions": row.get("quiz_exclusions") or [],
    }


def row_to_help_request(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentName": row["student_name"],
        "message": row["message"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "resolvedAt": row["resolved_at"],
    }


def row_to_vocab_quiz_attempt(row: dict) -> dict:
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "studentName": row["student_name"],
        "studentId": row.get("student_id"),
        "mode": row.get("mode"),
        "completedAt": row["completed_at"],
        "totalQuestions": row["total_questions"],
        "correctCount": row["correct_count"],
        "totalTimeMs": row["total_time_ms"],
        "questionResults": row["question_results"] or [],
    }


def row_to_student(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "createdAt": row["created_at"],
    }
```

- [ ] **Step 4: Run the row-mapper test**

```bash
cd backend && python -m pytest tests/test_row_mappers.py -v
```

Expected: all PASS.

- [ ] **Step 5: Route the whole test suite at the test database**

In `backend/tests/conftest.py`, replace the `client` fixture block (lines 62-69) with:

```python
# ── Database isolation ─────────────────────────────────────────────────────
#
# Before this existed, most tests wrote straight into the development
# database (backend/mandarin_stories.db) and left rows behind — the roster
# analytics were polluted with 29 junk quiz attempts. Every test now runs
# against the separate `mandarin_test` database, truncated between tests.

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin_test"
)

TRUNCATED_TABLES = (
    "audio_records",
    "custom_stories",
    "help_requests",
    "story_submissions",
    "students",
    "vocab_quiz_attempts",
)


@pytest.fixture(scope="session", autouse=True)
def use_test_database():
    import database

    database.reset_pool_for_tests(TEST_DATABASE_URL)
    yield
    database.close_db()


@pytest.fixture(autouse=True)
def clean_database(use_test_database):
    import database

    with database.connect_db() as db:
        db.execute(f"TRUNCATE {', '.join(TRUNCATED_TABLES)} RESTART IDENTITY CASCADE")
    yield


# ── FastAPI test client ────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as c:
        yield c
```

- [ ] **Step 6: Remove the two hand-rolled DB fixtures that are now redundant**

In `backend/tests/test_quiz_exclusions.py`, delete these two lines (16-17):

```python
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "test.db"))
    database.init_db()
```

If removing them leaves the enclosing fixture empty, delete the fixture and its usages — the autouse `clean_database` fixture now does the job. Apply the identical change to `backend/tests/test_students_login.py` (lines 18-19).

- [ ] **Step 7: Wire pool shutdown into the app**

In `backend/main.py`, find the import block at line 35 and add `close_db` next to `init_db`. Then, directly after the existing `@app.on_event("startup")` handler that calls `init_db()` (around line 78-80), add:

```python
@app.on_event("shutdown")
async def shutdown_database():
    close_db()
```

- [ ] **Step 8: Verify the mappers and schema still pass; other suites will still fail**

```bash
cd backend && python -m pytest tests/test_row_mappers.py tests/test_schema.py tests/test_database_connection.py -v
```

Expected: PASS. The router tests (`test_custom_stories_*`, `test_vocab_quiz_*`, etc.) are expected to FAIL at this point — their SQL still uses `?` placeholders. Tasks 5-9 fix them one router at a time. Record the current failure count for comparison:

```bash
cd backend && python -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 9: Commit**

```bash
git add backend/database.py backend/tests/conftest.py backend/tests/test_row_mappers.py backend/tests/test_quiz_exclusions.py backend/tests/test_students_login.py backend/main.py
git commit -m "feat(db): swap database.py to psycopg3 pool and isolate the test database"
```

---

### Task 4: One-shot data migration SQLite → PostgreSQL

**Files:**
- Create: `backend/scripts/migrate_sqlite_to_postgres.py`
- Test: `backend/tests/test_sqlite_migration.py`

**Interfaces:**
- Consumes: `connect_db()` from Task 3, the schema from Task 2.
- Produces:
  - `TABLES: dict[str, tuple[list[str], set[str], set[str]]]` — table name → (columns, JSON columns, boolean columns)
  - `migrate_table(sqlite_conn: sqlite3.Connection, table: str) -> int` — rows copied
  - `migrate_all(sqlite_path: str = DEFAULT_SQLITE_PATH) -> dict[str, int]` — table name → row count

- [ ] **Step 1: Write the failing migration test**

Create `backend/tests/test_sqlite_migration.py`:

```python
"""Verifies the one-shot SQLite -> PostgreSQL copy: TEXT JSON becomes real
JSONB, 0/1 flags become booleans, and Chinese text survives the round trip."""
import json
import sqlite3

import pytest

from database import connect_db
from scripts.migrate_sqlite_to_postgres import migrate_all


@pytest.fixture()
def legacy_db(tmp_path):
    """A miniature copy of the old SQLite schema with one row per table."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE custom_stories (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, learning_goal TEXT NOT NULL,
            frames TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            linear INTEGER NOT NULL DEFAULT 0, lesson_number INTEGER,
            narrative_mode TEXT NOT NULL DEFAULT 'story',
            first_frame_is_example INTEGER NOT NULL DEFAULT 0,
            quiz_exclusions TEXT);
        CREATE TABLE audio_records (
            id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, duration INTEGER NOT NULL,
            transcription TEXT NOT NULL DEFAULT '', model TEXT NOT NULL, topic_id TEXT,
            image_url TEXT, image_index INTEGER, audio_url TEXT, praat_metrics TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE help_requests (
            id TEXT PRIMARY KEY, student_name TEXT NOT NULL, message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, resolved_at TEXT);
        CREATE TABLE story_submissions (
            id TEXT PRIMARY KEY, story_id TEXT NOT NULL, story_title TEXT NOT NULL,
            student_name TEXT NOT NULL, submitted_at TEXT NOT NULL, scenes TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            concatenated_audio_url TEXT, story_feedback TEXT);
        CREATE TABLE vocab_quiz_attempts (
            id TEXT PRIMARY KEY, story_id TEXT NOT NULL, student_name TEXT NOT NULL,
            completed_at TEXT NOT NULL, total_questions INTEGER NOT NULL,
            correct_count INTEGER NOT NULL, total_time_ms INTEGER NOT NULL,
            question_results TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, mode TEXT, student_id TEXT);
        CREATE TABLE students (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            password TEXT NOT NULL DEFAULT '123456');
        """
    )
    frames = json.dumps(
        [{"prompt": "這是我的房間。", "vocabulary": "房間",
          "vocabularyDistractors": json.dumps([["廚房", "客廳"]])}],
        ensure_ascii=False,
    )
    conn.execute(
        "INSERT INTO custom_stories (id, title, learning_goal, frames, published, "
        "created_at, linear, lesson_number, narrative_mode, first_frame_is_example, quiz_exclusions) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("s1", "我的房間", "describe a room", frames, 1,
         "2026-07-20 10:00:00", 0, 5, "story", 0,
         json.dumps([{"word": "房間", "kind": "cloze"}], ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO students (id, name, created_at, password) VALUES (?,?,?,?)",
        ("stu-1", "Mai", "2026-07-20 10:00:00", "123456"),
    )
    conn.execute(
        "INSERT INTO vocab_quiz_attempts (id, story_id, student_name, completed_at, "
        "total_questions, correct_count, total_time_ms, question_results, created_at, mode, student_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("a1", "teacher-s1", "Mai", "2026-07-21T09:00:00Z", 10, 8, 42000,
         json.dumps([{"word": "房間", "correct": True, "timeMs": 1200}], ensure_ascii=False),
         "2026-07-21 09:00:00", "tier2", "stu-1"),
    )
    conn.commit()
    conn.close()
    return str(path)


def test_migrate_all_copies_every_table(legacy_db):
    counts = migrate_all(legacy_db)
    assert counts["custom_stories"] == 1
    assert counts["students"] == 1
    assert counts["vocab_quiz_attempts"] == 1


def test_json_text_becomes_queryable_jsonb(legacy_db):
    migrate_all(legacy_db)
    with connect_db() as db:
        row = db.execute(
            "SELECT frames -> 0 ->> 'prompt' AS prompt, "
            "       jsonb_array_length(frames) AS n "
            "FROM custom_stories WHERE id = %s",
            ("s1",),
        ).fetchone()
    assert row["prompt"] == "這是我的房間。"
    assert row["n"] == 1


def test_nested_json_strings_stay_strings(legacy_db):
    """vocabularyDistractors is a JSON *string* inside frames — the frontend
    does JSON.parse() on it, so the migration must not unwrap it."""
    migrate_all(legacy_db)
    with connect_db() as db:
        row = db.execute(
            "SELECT frames -> 0 ->> 'vocabularyDistractors' AS raw FROM custom_stories WHERE id = %s",
            ("s1",),
        ).fetchone()
    assert json.loads(row["raw"]) == [["廚房", "客廳"]]


def test_integer_flags_become_booleans(legacy_db):
    migrate_all(legacy_db)
    with connect_db() as db:
        row = db.execute(
            "SELECT published, linear FROM custom_stories WHERE id = %s", ("s1",)
        ).fetchone()
    assert row["published"] is True
    assert row["linear"] is False


def test_migration_is_rerunnable(legacy_db):
    """Re-running must not duplicate or error — it upserts by primary key."""
    migrate_all(legacy_db)
    counts = migrate_all(legacy_db)
    assert counts["custom_stories"] == 1
    with connect_db() as db:
        total = db.execute("SELECT count(*) AS n FROM custom_stories").fetchone()["n"]
    assert total == 1
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_sqlite_migration.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.migrate_sqlite_to_postgres'`.

- [ ] **Step 3: Write the migration script**

Create `backend/scripts/migrate_sqlite_to_postgres.py`:

```python
"""One-shot copy of the legacy SQLite database into PostgreSQL.

Usage (from backend/):
    python -m scripts.migrate_sqlite_to_postgres
    python -m scripts.migrate_sqlite_to_postgres --sqlite mandarin_stories.db

Safe to re-run: every table upserts on its primary key, so a partial run can
just be repeated. The SQLite file is only ever read.
"""
import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from database import connect_db  # noqa: E402

DEFAULT_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mandarin_stories.db"
)

# table -> (columns, json columns, boolean columns)
TABLES = {
    "custom_stories": (
        ["id", "title", "learning_goal", "frames", "published", "created_at",
         "linear", "lesson_number", "narrative_mode", "first_frame_is_example",
         "quiz_exclusions"],
        {"frames", "quiz_exclusions"},
        {"published", "linear", "first_frame_is_example"},
    ),
    "audio_records": (
        ["id", "timestamp", "duration", "transcription", "model", "topic_id",
         "image_url", "image_index", "audio_url", "praat_metrics", "created_at"],
        {"praat_metrics"},
        set(),
    ),
    "help_requests": (
        ["id", "student_name", "message", "status", "created_at", "resolved_at"],
        set(),
        set(),
    ),
    "story_submissions": (
        ["id", "story_id", "story_title", "student_name", "submitted_at", "scenes",
         "created_at", "concatenated_audio_url", "story_feedback"],
        {"scenes", "story_feedback"},
        set(),
    ),
    "vocab_quiz_attempts": (
        ["id", "story_id", "student_name", "completed_at", "total_questions",
         "correct_count", "total_time_ms", "question_results", "created_at",
         "mode", "student_id"],
        {"question_results"},
        set(),
    ),
    "students": (
        ["id", "name", "created_at", "password"],
        set(),
        set(),
    ),
}


def _convert(column: str, value, json_columns: set, bool_columns: set):
    if column in json_columns:
        if value in (None, ""):
            return None
        try:
            return Jsonb(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            # A row whose JSON never parsed under SQLite either — keep the
            # raw text so nothing is silently dropped, wrapped as a JSON
            # string so the column type still accepts it.
            return Jsonb(value)
    if column in bool_columns:
        return bool(value)
    return value


def migrate_table(sqlite_conn: sqlite3.Connection, table: str) -> int:
    columns, json_columns, bool_columns = TABLES[table]
    available = {row[1] for row in sqlite_conn.execute(f"PRAGMA table_info({table})")}
    if not available:
        print(f"  {table}: not present in the SQLite file, skipped")
        return 0
    columns = [c for c in columns if c in available]

    rows = sqlite_conn.execute(
        f"SELECT {', '.join(columns)} FROM {table}"
    ).fetchall()
    if not rows:
        return 0

    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != "id")
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )

    with connect_db() as db:
        for row in rows:
            db.execute(
                sql,
                tuple(
                    _convert(column, row[index], json_columns, bool_columns)
                    for index, column in enumerate(columns)
                ),
            )
    return len(rows)


def migrate_all(sqlite_path: str = DEFAULT_SQLITE_PATH) -> dict:
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"No SQLite database at {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    try:
        # students first: nothing enforces it today, but copying the roster
        # before the rows that reference student_id keeps the data sensible
        # if a foreign key is ever added.
        order = ["students", "custom_stories", "audio_records", "help_requests",
                 "story_submissions", "vocab_quiz_attempts"]
        counts = {}
        for table in order:
            counts[table] = migrate_table(sqlite_conn, table)
            print(f"  {table}: {counts[table]} rows")
        return counts
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=DEFAULT_SQLITE_PATH)
    args = parser.parse_args()
    print(f"Migrating {args.sqlite} -> PostgreSQL")
    counts = migrate_all(args.sqlite)
    print(f"Done. {sum(counts.values())} rows copied.")
```

Create `backend/scripts/__init__.py` (empty file) if it does not already exist, so `python -m scripts.migrate_sqlite_to_postgres` and the test's `from scripts.migrate_sqlite_to_postgres import ...` both resolve.

- [ ] **Step 4: Run the migration test**

```bash
cd backend && python -m pytest tests/test_sqlite_migration.py -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Migrate the real development data**

```bash
cd backend && python -m scripts.migrate_sqlite_to_postgres
```

Expected output (counts must match the SQLite source):

```
  students: 4 rows
  custom_stories: 7 rows
  audio_records: 326 rows
  help_requests: 4 rows
  story_submissions: 12 rows
  vocab_quiz_attempts: 90 rows
Done. 443 rows copied.
```

- [ ] **Step 6: Spot-check the migrated materials by hand**

```bash
docker exec -it mandarin-postgres psql -U mandarin -d mandarin -c "SELECT id, title, lesson_number, published, jsonb_array_length(frames) AS frames FROM custom_stories ORDER BY created_at DESC;"
```

Expected: 7 rows, readable Traditional Chinese titles (not mojibake), frame counts between 1 and ~12. If titles are garbled, stop — the SQLite file was read with the wrong text factory.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/migrate_sqlite_to_postgres.py backend/scripts/__init__.py backend/tests/test_sqlite_migration.py
git commit -m "feat(db): add re-runnable SQLite to PostgreSQL data migration"
```

---

### Task 5: Materials CRUD — `routers/stories.py` list/create/delete

**Files:**
- Modify: `backend/routers/stories.py:19-75`
- Modify: `backend/main.py:698-740` (`persist_story_frame_images`, `persist_story_frame_audio`)
- Test: `backend/tests/test_custom_stories_crud.py`

**Interfaces:**
- Consumes: `connect_db()`, `row_to_custom_story()` from Task 3.
- Produces: unchanged HTTP contract —
  - `GET /api/custom-stories?limit&skip` → `list[CustomStory]`
  - `POST /api/custom-stories` → the saved story with `/uploads/...` frame URLs
  - `DELETE /api/custom-stories/{story_id}` → `{"ok": True}`

- [ ] **Step 1: Write the failing CRUD test**

Create `backend/tests/test_custom_stories_crud.py`:

```python
"""Materials CRUD against PostgreSQL.

The upsert test is the important one: SQLite's INSERT OR REPLACE is a
DELETE+INSERT, so re-saving a story used to wipe quiz_exclusions (never
listed in the INSERT) and reset created_at, silently reshuffling the
teacher's story list. ON CONFLICT DO UPDATE only touches listed columns.
"""

STORY = {
    "id": "crud-story-1",
    "title": "我的房間",
    "learningGoal": "describe a room",
    "frames": [
        {"imageUrl": "", "prompt": "這是我的房間。", "vocabulary": "房間, 桌子"},
        {"imageUrl": "", "prompt": "房間裡有一張床。", "vocabulary": "床"},
    ],
    "published": True,
    "linear": True,
    "lessonNumber": 5,
    "narrativeMode": "story",
    "firstFrameIsExample": False,
}


def test_create_then_list_round_trips(client):
    assert client.post("/api/custom-stories", json=STORY).status_code == 200

    stories = client.get("/api/custom-stories").json()
    saved = next(s for s in stories if s["id"] == "crud-story-1")
    assert saved["title"] == "我的房間"
    assert saved["published"] is True
    assert saved["linear"] is True
    assert saved["lessonNumber"] == 5
    assert saved["firstFrameIsExample"] is False
    assert len(saved["frames"]) == 2
    assert saved["frames"][1]["prompt"] == "房間裡有一張床。"
    assert saved["quizExclusions"] == []


def test_resave_preserves_quiz_exclusions(client):
    client.post("/api/custom-stories", json=STORY)
    client.put(
        "/api/custom-stories/crud-story-1/quiz-exclusions",
        json={"exclusions": [{"word": "房間", "kind": "cloze"}]},
    )

    # Teacher edits the title and saves again.
    client.post("/api/custom-stories", json={**STORY, "title": "我的新房間"})

    saved = next(
        s for s in client.get("/api/custom-stories").json() if s["id"] == "crud-story-1"
    )
    assert saved["title"] == "我的新房間"
    assert saved["quizExclusions"] == [{"word": "房間", "kind": "cloze"}]


def test_resave_preserves_created_at(client):
    """Under INSERT OR REPLACE a re-save reset created_at, so an edited
    story jumped to the top of the teacher's list. created_at isn't in the
    API payload, so assert it directly against the database."""
    from database import connect_db

    client.post("/api/custom-stories", json=STORY)
    with connect_db() as db:
        before = db.execute(
            "SELECT created_at FROM custom_stories WHERE id = %s", ("crud-story-1",)
        ).fetchone()["created_at"]

    client.post("/api/custom-stories", json={**STORY, "title": "changed"})
    with connect_db() as db:
        after = db.execute(
            "SELECT created_at FROM custom_stories WHERE id = %s", ("crud-story-1",)
        ).fetchone()["created_at"]

    assert after == before


def test_delete_removes_the_story(client):
    client.post("/api/custom-stories", json=STORY)
    assert client.delete("/api/custom-stories/crud-story-1").json() == {"ok": True}
    ids = [s["id"] for s in client.get("/api/custom-stories").json()]
    assert "crud-story-1" not in ids


def test_delete_is_idempotent_for_a_missing_story(client):
    assert client.delete("/api/custom-stories/never-existed").json() == {"ok": True}


def test_list_pagination(client):
    for index in range(3):
        client.post("/api/custom-stories", json={**STORY, "id": f"page-{index}"})
    page = client.get("/api/custom-stories", params={"limit": 2, "skip": 0}).json()
    assert len(page) == 2
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_custom_stories_crud.py -v
```

Expected: FAIL — psycopg raises `ProgrammingError` on the `?` placeholders in the existing SQL.

- [ ] **Step 3: Rewrite the three CRUD endpoints**

In `backend/routers/stories.py`, add `from psycopg.types.json import Jsonb` to the imports, then replace lines 19-75 with:

```python
@router.get("/api/custom-stories")
async def list_custom_stories(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM custom_stories ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, skip),
        ).fetchall()
    return [row_to_custom_story(row) for row in rows]


@router.post("/api/custom-stories")
async def create_custom_story(story: CustomStoryRequest):
    frames = [frame.model_dump() for frame in story.frames]
    stored_frames = main.persist_story_frame_images(story.id, frames)
    stored_frames = main.persist_story_frame_audio(story.id, stored_frames)
    with connect_db() as db:
        # ON CONFLICT DO UPDATE, not the old INSERT OR REPLACE: SQLite's
        # replace was a DELETE+INSERT, so every re-save wiped the two columns
        # missing from this list (quiz_exclusions, created_at). Updating only
        # the listed columns keeps a teacher's quiz-review work and the
        # story's original position in the list.
        db.execute(
            """
            INSERT INTO custom_stories (
                id, title, learning_goal, frames, published, linear,
                lesson_number, narrative_mode, first_frame_is_example
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                learning_goal = EXCLUDED.learning_goal,
                frames = EXCLUDED.frames,
                published = EXCLUDED.published,
                linear = EXCLUDED.linear,
                lesson_number = EXCLUDED.lesson_number,
                narrative_mode = EXCLUDED.narrative_mode,
                first_frame_is_example = EXCLUDED.first_frame_is_example
            """,
            (
                story.id,
                story.title,
                story.learningGoal,
                Jsonb(stored_frames),
                story.published,
                story.linear,
                story.lessonNumber,
                story.narrativeMode,
                story.firstFrameIsExample,
            ),
        )
    return {
        **story.model_dump(),
        "frames": stored_frames,
    }


@router.delete("/api/custom-stories/{story_id}")
async def delete_custom_story(story_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s",
            (story_id,),
        ).fetchone()
        db.execute("DELETE FROM custom_stories WHERE id = %s", (story_id,))
    if row:
        for frame in row["frames"] or []:
            main.remove_uploaded_file(frame.get("imageUrl", ""))
            main.remove_uploaded_file(frame.get("listenAudioUrl", ""))
    return {"ok": True}
```

- [ ] **Step 4: Fix the two frame-persistence helpers in `main.py`**

In `backend/main.py`, inside `persist_story_frame_images` (around line 698), replace:

```python
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = ?", (story_id,)
        ).fetchone()
    old_frames = json.loads(row["frames"] or "[]") if row else []
```

with:

```python
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
        ).fetchone()
    old_frames = (row["frames"] or []) if row else []
```

Apply the identical replacement inside `persist_story_frame_audio` (around line 720).

- [ ] **Step 5: Run the CRUD test**

```bash
cd backend && python -m pytest tests/test_custom_stories_crud.py -v
```

Expected: all 6 PASS. `test_resave_preserves_quiz_exclusions` depends on the `PUT /quiz-exclusions` endpoint, which Task 6 converts — if it still fails on that call, run it again at the end of Task 6.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/stories.py backend/main.py backend/tests/test_custom_stories_crud.py
git commit -m "feat(materials): move custom-stories CRUD to PostgreSQL upserts"
```

---

### Task 6: Materials quiz-pool endpoints — in-place `jsonb_set` writes

**Files:**
- Modify: `backend/routers/stories.py:78-311` (5 endpoints)
- Test: `backend/tests/test_custom_stories_pool_updates.py`

**Interfaces:**
- Consumes: `connect_db()`, `Jsonb`.
- Produces: three shared private helpers in `routers/stories.py`, used by all five endpoints:
  - `_load_frames(db, story_id: str) -> list` — the story's parsed JSONB frames, raising 404 if absent
  - `_existing_pool(frame: dict, field: str) -> list` — one frame field's per-word pool, `[]` when missing or malformed
  - `_write_frame_field(db, story_id: str, frame_index: int, field: str, value_json: str) -> None` — writes one frame's one field with `jsonb_set` instead of rewriting the whole `frames` array
- Unchanged HTTP contract for `PATCH .../vocabulary-{distractors,lookalike,cloze,synonym}` → `{"ok": True}`, and `PUT .../quiz-exclusions` → `{"id", "quizExclusions"}`.

- [ ] **Step 1: Write the failing pool-update test**

Create `backend/tests/test_custom_stories_pool_updates.py`:

```python
"""The four quiz-pool PATCH endpoints grow per-word pools over time. Under
SQLite each call rewrote the entire 34 KB frames blob, so two concurrent
PATCHes on different frames could lose one another's write. jsonb_set
updates only the touched path."""

STORY = {
    "id": "pool-story",
    "title": "我的房間",
    "learningGoal": "g",
    "frames": [
        {"imageUrl": "", "prompt": "這是我的房間。", "vocabulary": "房間, 桌子"},
        {"imageUrl": "", "prompt": "房間裡有一張床。", "vocabulary": "床"},
    ],
    "narrativeMode": "story",
}


def _make_story(client):
    assert client.post("/api/custom-stories", json=STORY).status_code == 200


def _frames(client):
    story = next(
        s for s in client.get("/api/custom-stories").json() if s["id"] == "pool-story"
    )
    return story["frames"]


def test_distractors_are_stored_as_a_json_string_per_word(client):
    import json

    _make_story(client)
    response = client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["廚房", "客廳"]}]},
    )
    assert response.json() == {"ok": True}

    raw = _frames(client)[0]["vocabularyDistractors"]
    # The frontend does JSON.parse() on this field — it must stay a string.
    assert isinstance(raw, str)
    assert json.loads(raw)[0] == ["廚房", "客廳"]


def test_distractors_merge_instead_of_replacing(client):
    import json

    _make_story(client)
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["廚房"]}]},
    )
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["客廳", "廚房"]}]},
    )
    pool = json.loads(_frames(client)[0]["vocabularyDistractors"])
    assert pool[0] == ["廚房", "客廳"]  # deduped, order preserved


def test_patching_one_frame_leaves_the_other_untouched(client):
    import json

    _make_story(client)
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 1, "wordIndex": 0, "distractors": ["椅子"]}]},
    )
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-lookalike",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "lookalikes": ["房閒"]}]},
    )
    frames = _frames(client)
    assert json.loads(frames[1]["vocabularyDistractors"])[0] == ["椅子"]
    assert json.loads(frames[0]["vocabularyLookalike"])[0] == ["房閒"]
    assert frames[0]["prompt"] == "這是我的房間。"
    assert frames[1]["prompt"] == "房間裡有一張床。"


def test_cloze_candidates_dedupe_by_sentence(client):
    import json

    _make_story(client)
    payload = {
        "updates": [
            {
                "frameIndex": 0,
                "wordIndex": 0,
                "candidates": [
                    {"sentence": "這是我的＿＿。", "distractors": ["廚房"]},
                    {"sentence": "這是我的＿＿。", "distractors": ["客廳"]},
                ],
            }
        ]
    }
    client.patch("/api/custom-stories/pool-story/vocabulary-cloze", json=payload)
    pool = json.loads(_frames(client)[0]["vocabularyCloze"])
    assert len(pool[0]) == 1


def test_synonym_candidates_round_trip(client):
    import json

    _make_story(client)
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-synonym",
        json={
            "updates": [
                {"frameIndex": 0, "wordIndex": 1, "candidates": [
                    {"synonym": "書桌", "distractors": ["椅子", "床"]}
                ]}
            ]
        },
    )
    pool = json.loads(_frames(client)[0]["vocabularySynonym"])
    assert pool[0] == []          # word 0 untouched
    assert pool[1][0]["synonym"] == "書桌"


def test_pool_patch_on_missing_story_is_404(client):
    response = client.patch(
        "/api/custom-stories/nope/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["x"]}]},
    )
    assert response.status_code == 404


def test_quiz_exclusions_replace_wholesale(client):
    _make_story(client)
    first = client.put(
        "/api/custom-stories/pool-story/quiz-exclusions",
        json={"exclusions": [{"word": "房間", "kind": "cloze"}, {"word": "床", "kind": "synonym"}]},
    )
    assert first.json()["quizExclusions"] == [
        {"word": "房間", "kind": "cloze"},
        {"word": "床", "kind": "synonym"},
    ]
    second = client.put(
        "/api/custom-stories/pool-story/quiz-exclusions",
        json={"exclusions": [{"word": "桌子", "kind": "cloze"}]},
    )
    assert second.json()["quizExclusions"] == [{"word": "桌子", "kind": "cloze"}]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_custom_stories_pool_updates.py -v
```

Expected: FAIL on the `?` placeholders.

- [ ] **Step 3: Add the shared frame-path helper**

In `backend/routers/stories.py`, insert directly after `router = APIRouter()`:

```python
def _load_frames(db, story_id: str) -> list:
    """Reads a story's frames (already-parsed JSONB), 404-ing if it's gone."""
    row = db.execute(
        "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Story not found.")
    return row["frames"] or []


def _write_frame_field(db, story_id: str, frame_index: int, field: str, value_json: str) -> None:
    """Writes one field of one frame in place.

    jsonb_set targets `frames -> frame_index -> field` instead of rewriting
    the whole frames array, so two PATCHes touching different frames (or
    different fields of the same frame) can't clobber each other's work.

    `value_json` is a JSON *string* — the pools are stored serialised inside
    the frame because the frontend does JSON.parse() on them, so to_jsonb()
    of the text is exactly the right value.
    """
    db.execute(
        "UPDATE custom_stories "
        "SET frames = jsonb_set(frames, ARRAY[%s, %s], to_jsonb(%s::text), true) "
        "WHERE id = %s",
        (str(frame_index), field, value_json, story_id),
    )


def _existing_pool(frame: dict, field: str) -> list:
    """The per-word pool for a frame field, as a Python list.

    Stored as a JSON string inside the frame; a malformed or missing value
    is treated as an empty pool rather than failing the request.
    """
    try:
        pool = json.loads(frame.get(field) or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return pool if isinstance(pool, list) else []
```

- [ ] **Step 4: Rewrite `update_vocabulary_distractors`**

Replace the body of `update_vocabulary_distractors` (everything after its docstring) with:

```python
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularyDistractors")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {d.strip().lower() for d in existing}
            merged = list(existing)
            for distractor in update.distractors:
                distractor = distractor.strip()
                key = distractor.lower()
                if (
                    not distractor
                    or key in seen
                    or len(merged) >= main.MAX_VOCAB_DISTRACTORS_PER_WORD
                ):
                    continue
                seen.add(key)
                merged.append(distractor)
            pool[update.wordIndex] = merged
            # Keep the local copy in sync so several updates to the same
            # frame in one request build on each other.
            frame["vocabularyDistractors"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularyDistractors",
                frame["vocabularyDistractors"],
            )
    return {"ok": True}
```

- [ ] **Step 5: Rewrite `update_vocabulary_lookalike`**

Replace its body after the docstring with:

```python
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularyLookalike")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {c.strip() for c in existing}
            merged = list(existing)
            for lookalike in update.lookalikes:
                lookalike = lookalike.strip()
                if (
                    not lookalike
                    or lookalike in seen
                    or len(merged) >= main.MAX_VOCAB_LOOKALIKE_PER_WORD
                ):
                    continue
                seen.add(lookalike)
                merged.append(lookalike)
            pool[update.wordIndex] = merged
            frame["vocabularyLookalike"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularyLookalike",
                frame["vocabularyLookalike"],
            )
    return {"ok": True}
```

- [ ] **Step 6: Rewrite `update_vocabulary_cloze`**

Replace its body after the docstring with:

```python
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularyCloze")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {c.get("sentence", "").strip() for c in existing if isinstance(c, dict)}
            merged = list(existing)
            for candidate in update.candidates:
                sentence = candidate.sentence.strip()
                if (
                    not sentence
                    or sentence in seen
                    or len(merged) >= main.MAX_VOCAB_CLOZE_PER_WORD
                ):
                    continue
                seen.add(sentence)
                merged.append({"sentence": sentence, "distractors": candidate.distractors})
            pool[update.wordIndex] = merged
            frame["vocabularyCloze"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularyCloze",
                frame["vocabularyCloze"],
            )
    return {"ok": True}
```

- [ ] **Step 7: Rewrite `update_vocabulary_synonym`**

Replace its body after the docstring with:

```python
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularySynonym")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {c.get("synonym", "").strip() for c in existing if isinstance(c, dict)}
            merged = list(existing)
            for candidate in update.candidates:
                synonym = candidate.synonym.strip()
                if (
                    not synonym
                    or synonym in seen
                    or len(merged) >= main.MAX_VOCAB_SYNONYM_PER_WORD
                ):
                    continue
                seen.add(synonym)
                merged.append({"synonym": synonym, "distractors": candidate.distractors})
            pool[update.wordIndex] = merged
            frame["vocabularySynonym"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularySynonym",
                frame["vocabularySynonym"],
            )
    return {"ok": True}
```

- [ ] **Step 8: Rewrite `update_quiz_exclusions`**

Replace its body after the docstring with:

```python
    exclusions = [exclusion.model_dump(exclude_none=True) for exclusion in request.exclusions]
    with connect_db() as db:
        row = db.execute(
            "UPDATE custom_stories SET quiz_exclusions = %s WHERE id = %s RETURNING id",
            (Jsonb(exclusions), story_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Story not found.")
    return {"id": story_id, "quizExclusions": exclusions}
```

Note this collapses the previous SELECT-then-UPDATE into one statement via `RETURNING`.

- [ ] **Step 9: Run the pool tests plus the Task 5 CRUD tests and the existing story suites**

```bash
cd backend && python -m pytest tests/test_custom_stories_pool_updates.py tests/test_custom_stories_crud.py tests/test_quiz_exclusions.py tests/test_custom_stories_vocabulary_distractors.py tests/test_custom_stories_vocabulary_lookalike.py tests/test_custom_stories_vocabulary_cloze.py tests/test_custom_stories_vocabulary_synonym.py tests/test_custom_stories_vocab_fields.py tests/test_custom_stories_phrases_fields.py tests/test_custom_stories_level_tiers.py -v
```

Expected: all PASS. The pre-existing `test_custom_stories_*` suites must pass unmodified — they are the proof the HTTP contract is unchanged.

- [ ] **Step 10: Commit**

```bash
git add backend/routers/stories.py backend/tests/test_custom_stories_pool_updates.py
git commit -m "feat(materials): update quiz pools in place with jsonb_set"
```

---

### Task 7: `students` and `help_requests` routers

**Files:**
- Modify: `backend/routers/students.py` (whole file)
- Modify: `backend/routers/help_requests.py` (whole file)
- Test: `backend/tests/test_students_crud.py`

**Interfaces:**
- Consumes: `connect_db()`, `row_to_student()`, `row_to_help_request()`.
- Produces: unchanged contracts for `GET/POST /api/students`, `POST /api/students/login`, `DELETE /api/students/{id}`, `GET/POST /api/help-requests`, `POST /api/help-requests/{id}/resolve`.

**Note:** PostgreSQL has no `COLLATE NOCASE`. Every case-insensitive name comparison becomes `lower(name) = lower(%s)`, and the roster ordering becomes `ORDER BY lower(name)`. Task 2 created `ix_students_lower_name` for exactly this.

- [ ] **Step 1: Write the failing roster test**

Create `backend/tests/test_students_crud.py`:

```python
"""Roster CRUD, with the case-insensitive behaviour SQLite got from
COLLATE NOCASE and Postgres has to get from lower()."""


def test_create_and_list_students(client):
    client.post("/api/students", json={"name": "Mai"})
    client.post("/api/students", json={"name": "an"})
    client.post("/api/students", json={"name": "Bảo"})
    names = [s["name"] for s in client.get("/api/students").json()]
    # Case-insensitive alphabetical: an, Bảo, Mai
    assert names == ["an", "Bảo", "Mai"]


def test_create_is_idempotent_case_insensitively(client):
    first = client.post("/api/students", json={"name": "Mai"}).json()
    second = client.post("/api/students", json={"name": "MAI"}).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/students").json()) == 1


def test_blank_name_is_rejected(client):
    assert client.post("/api/students", json={"name": "   "}).status_code == 400


def test_login_by_name_is_case_insensitive(client):
    created = client.post("/api/students", json={"name": "Mai"}).json()
    response = client.post(
        "/api/students/login", json={"name": "mai", "password": "123456"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_login_with_wrong_password_is_401(client):
    client.post("/api/students", json={"name": "Mai"})
    response = client.post(
        "/api/students/login", json={"name": "Mai", "password": "nope"}
    )
    assert response.status_code == 401


def test_login_for_unknown_student_is_404(client):
    response = client.post(
        "/api/students/login", json={"name": "Ghost", "password": "123456"}
    )
    assert response.status_code == 404


def test_delete_student(client):
    created = client.post("/api/students", json={"name": "Mai"}).json()
    assert client.delete(f"/api/students/{created['id']}").json()["deleted"] is True
    assert client.get("/api/students").json() == []


def test_help_requests_sort_open_first(client):
    client.post("/api/help-requests", json={
        "id": "h1", "studentName": "Mai", "message": "help me",
        "status": "open", "createdAt": "2026-07-20T08:00:00Z"})
    client.post("/api/help-requests", json={
        "id": "h2", "studentName": "An", "message": "also help",
        "status": "open", "createdAt": "2026-07-21T08:00:00Z"})
    client.post("/api/help-requests/h2/resolve")

    requests = client.get("/api/help-requests").json()
    assert [r["id"] for r in requests] == ["h1", "h2"]
    assert requests[1]["status"] == "resolved"
    assert requests[1]["resolvedAt"] is not None


def test_resolving_a_missing_help_request_is_404(client):
    assert client.post("/api/help-requests/nope/resolve").status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_students_crud.py -v
```

Expected: FAIL — `syntax error at or near "COLLATE"` / placeholder errors.

- [ ] **Step 3: Rewrite `routers/students.py`**

Replace the three SQL-bearing endpoints:

```python
@router.get("/api/students")
async def list_students():
    with connect_db() as db:
        # Postgres has no COLLATE NOCASE; lower() reproduces SQLite's
        # case-insensitive roster ordering (backed by ix_students_lower_name).
        rows = db.execute("SELECT * FROM students ORDER BY lower(name)").fetchall()
    return [row_to_student(row) for row in rows]


@router.post("/api/students")
async def create_student(request: StudentCreateRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provide a student name.")

    with connect_db() as db:
        existing = db.execute(
            "SELECT * FROM students WHERE lower(name) = lower(%s)",
            (name,),
        ).fetchone()
        if existing is not None:
            # Idempotent: re-adding a name already on the roster just hands
            # back its existing id instead of erroring, so a teacher can
            # re-submit the roster form without worrying about duplicates.
            return row_to_student(existing)

        student_id = str(uuid.uuid4())
        created = db.execute(
            "INSERT INTO students (id, name) VALUES (%s, %s) RETURNING *",
            (student_id, name),
        ).fetchone()
    return row_to_student(created)


@router.post("/api/students/login")
async def login_student(request: StudentLoginRequest):
    """Password check for the student login page (default 123456).

    A classroom friction gate, not real auth: plaintext comparison, no
    tokens — success just hands back the roster record the frontend
    stores in its localStorage session, same as before passwords existed.
    """
    if not (request.studentId or (request.name and request.name.strip())):
        raise HTTPException(status_code=400, detail="Provide a student id or name.")

    with connect_db() as db:
        if request.studentId:
            row = db.execute(
                "SELECT * FROM students WHERE id = %s", (request.studentId,)
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM students WHERE lower(name) = lower(%s)",
                (request.name.strip(),),
            ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if request.password != (row.get("password") or "123456"):
        raise HTTPException(status_code=401, detail="Wrong password")
    return row_to_student(row)


@router.delete("/api/students/{student_id}")
async def delete_student(student_id: str):
    with connect_db() as db:
        row = db.execute(
            "DELETE FROM students WHERE id = %s RETURNING id", (student_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Student not found")
    return {"id": student_id, "deleted": True}
```

- [ ] **Step 4: Rewrite `routers/help_requests.py`**

Replace the three endpoints' SQL:

```python
@router.get("/api/help-requests")
async def list_help_requests(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM help_requests
            ORDER BY
                CASE status WHEN 'open' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, skip),
        ).fetchall()
    return [row_to_help_request(row) for row in rows]


@router.post("/api/help-requests")
async def create_help_request(request: HelpRequest):
    student_name = request.studentName.strip() or "Student"
    message = request.message.strip() or "I need teacher help."
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO help_requests (
                id, student_name, message, status, created_at, resolved_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                student_name = EXCLUDED.student_name,
                message = EXCLUDED.message,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                resolved_at = EXCLUDED.resolved_at
            """,
            (
                request.id,
                student_name,
                message,
                "open",
                request.createdAt,
                None,
            ),
        )
    return {
        **request.model_dump(),
        "studentName": student_name,
        "message": message,
        "status": "open",
        "resolvedAt": None,
    }


@router.post("/api/help-requests/{request_id}/resolve")
async def resolve_help_request(request_id: str):
    resolved_at = datetime.datetime.utcnow().isoformat() + "Z"
    with connect_db() as db:
        updated = db.execute(
            """
            UPDATE help_requests
            SET status = 'resolved', resolved_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (resolved_at, request_id),
        ).fetchone()
        if updated is None:
            raise HTTPException(status_code=404, detail="Help request not found")
    return row_to_help_request(updated)
```

- [ ] **Step 5: Run the roster and login tests**

```bash
cd backend && python -m pytest tests/test_students_crud.py tests/test_students_login.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/students.py backend/routers/help_requests.py backend/tests/test_students_crud.py
git commit -m "feat(db): port students and help-requests routers to PostgreSQL"
```

---

### Task 8: `audio_records` and `story_submissions`

**Files:**
- Modify: `backend/routers/audio.py:16-54`
- Modify: `backend/main.py:597-620` (`save_audio_record`)
- Modify: `backend/routers/submissions.py:17-45` and the closing `UPDATE` block
- Test: `backend/tests/test_audio_and_submissions_db.py`

**Interfaces:**
- Consumes: `connect_db()`, `row_to_audio_record()`, `row_to_story_submission()`, `Jsonb`.
- Produces: unchanged contracts for `GET/POST/DELETE /api/audio-records` and `GET/POST /api/story-submissions`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_audio_and_submissions_db.py`:

```python
"""Audio records and story submissions round-tripping through PostgreSQL,
including the JSONB praat_metrics / scenes / story_feedback columns."""

AUDIO_RECORD = {
    "id": "rec-1",
    "timestamp": "2026-07-26T08:00:00Z",
    "duration": 3200,
    "transcription": "這是我的房間。",
    "model": "whisper",
    "topicId": "teacher-story-1",
    "imageUrl": "/uploads/images/a.png",
    "imageIndex": 0,
    "audioUrl": None,
    "praatMetrics": {"toneAccuracy": 0.82, "pauseCount": 3},
}


def test_audio_record_round_trips_with_praat_metrics(client):
    assert client.post("/api/audio-records", json=AUDIO_RECORD).status_code == 200
    records = client.get("/api/audio-records").json()
    saved = next(r for r in records if r["id"] == "rec-1")
    assert saved["transcription"] == "這是我的房間。"
    assert saved["praatMetrics"] == {"toneAccuracy": 0.82, "pauseCount": 3}


def test_audio_record_resave_updates_in_place(client):
    client.post("/api/audio-records", json=AUDIO_RECORD)
    client.post("/api/audio-records", json={**AUDIO_RECORD, "transcription": "改過了"})
    matching = [r for r in client.get("/api/audio-records").json() if r["id"] == "rec-1"]
    assert len(matching) == 1
    assert matching[0]["transcription"] == "改過了"


def test_delete_audio_record(client):
    client.post("/api/audio-records", json=AUDIO_RECORD)
    assert client.delete("/api/audio-records/rec-1").json() == {"ok": True}
    assert [r for r in client.get("/api/audio-records").json() if r["id"] == "rec-1"] == []


def test_story_submission_round_trips_with_scenes(client):
    submission = {
        "id": "sub-1",
        "storyId": "teacher-story-1",
        "storyTitle": "我的房間",
        "studentName": "Mai",
        "submittedAt": "2026-07-26T08:00:00Z",
        "scenes": [
            {"sceneIndex": 1, "transcription": "房間裡有一張床。", "audioUrl": "",
             "toneAccuracy": 70.0, "fluencyScore": 60.0, "pronScore": 65.0,
             "pauseCount": 2, "longestPause": 900, "utteranceCount": 2,
             "choppyPauseCount": 0, "articulationRate": 3.1},
            {"sceneIndex": 0, "transcription": "這是我的房間。", "audioUrl": "",
             "toneAccuracy": 80.0, "fluencyScore": 70.0, "pronScore": 75.0,
             "pauseCount": 1, "longestPause": 400, "utteranceCount": 1,
             "choppyPauseCount": 0, "articulationRate": 3.4},
        ],
    }
    response = client.post("/api/story-submissions", json=submission)
    assert response.status_code == 200
    # Scenes are stored sorted by sceneIndex regardless of submitted order.
    assert [s["sceneIndex"] for s in response.json()["scenes"]] == [0, 1]

    listed = client.get("/api/story-submissions", params={"story_id": "teacher-story-1"}).json()
    saved = next(s for s in listed if s["id"] == "sub-1")
    assert [s["sceneIndex"] for s in saved["scenes"]] == [0, 1]
    assert saved["scenes"][0]["transcription"] == "這是我的房間。"


def test_story_submissions_filter_by_story_id(client):
    assert client.get("/api/story-submissions", params={"story_id": "nothing"}).json() == []
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_audio_and_submissions_db.py -v
```

Expected: FAIL on placeholders.

- [ ] **Step 3: Fix `save_audio_record` in `main.py`**

Replace the function body (around line 597) with:

```python
def save_audio_record(record: AudioRecordRequest):
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO audio_records (
                id, timestamp, duration, transcription, model, topic_id,
                image_url, image_index, audio_url, praat_metrics
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                duration = EXCLUDED.duration,
                transcription = EXCLUDED.transcription,
                model = EXCLUDED.model,
                topic_id = EXCLUDED.topic_id,
                image_url = EXCLUDED.image_url,
                image_index = EXCLUDED.image_index,
                audio_url = EXCLUDED.audio_url,
                praat_metrics = EXCLUDED.praat_metrics
            """,
            (
                record.id,
                record.timestamp,
                record.duration,
                record.transcription,
                record.model,
                record.topicId,
                record.imageUrl,
                record.imageIndex,
                record.audioUrl,
                Jsonb(record.praatMetrics),
            ),
        )
```

Add `from psycopg.types.json import Jsonb` to `main.py`'s imports.

- [ ] **Step 4: Fix `routers/audio.py`**

Replace the two SQL statements:

```python
        rows = db.execute(
            "SELECT * FROM audio_records ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, skip),
        ).fetchall()
```

and, in `delete_audio_record`:

```python
    with connect_db() as db:
        row = db.execute(
            "DELETE FROM audio_records WHERE id = %s RETURNING audio_url",
            (record_id,),
        ).fetchone()
    if row and row["audio_url"]:
        main.remove_uploaded_file(row["audio_url"])
    return {"ok": True}
```

- [ ] **Step 5: Fix `routers/submissions.py`**

Add `from psycopg.types.json import Jsonb` to the imports. Then replace the list query:

```python
        if story_id:
            rows = db.execute(
                "SELECT * FROM story_submissions WHERE story_id = %s ORDER BY submitted_at DESC",
                (story_id,),
            ).fetchall()
```

the insert:

```python
        db.execute(
            """
            INSERT INTO story_submissions
                (id, story_id, story_title, student_name, submitted_at, scenes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                story_id = EXCLUDED.story_id,
                story_title = EXCLUDED.story_title,
                student_name = EXCLUDED.student_name,
                submitted_at = EXCLUDED.submitted_at,
                scenes = EXCLUDED.scenes
            """,
            (
                submission.id,
                submission.storyId,
                submission.storyTitle,
                submission.studentName,
                submission.submittedAt,
                Jsonb([s.model_dump() for s in scenes_sorted]),
            ),
        )
```

and the closing update:

```python
    with connect_db() as db:
        db.execute(
            "UPDATE story_submissions SET concatenated_audio_url = %s, story_feedback = %s WHERE id = %s",
            (
                concatenated_audio_url,
                Jsonb(story_feedback) if story_feedback else None,
                submission.id,
            ),
        )
```

- [ ] **Step 6: Run the test**

```bash
cd backend && python -m pytest tests/test_audio_and_submissions_db.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/routers/audio.py backend/routers/submissions.py backend/main.py backend/tests/test_audio_and_submissions_db.py
git commit -m "feat(db): port audio records and story submissions to PostgreSQL"
```

---

### Task 9: `vocab_quiz` and `vocab_quiz_analytics`

**Files:**
- Modify: `backend/routers/vocab_quiz.py:27-116`
- Modify: `backend/routers/vocab_quiz_analytics.py:1-60`
- Test: `backend/tests/test_vocab_quiz_db.py`

**Interfaces:**
- Consumes: `connect_db()`, `row_to_vocab_quiz_attempt()`, `Jsonb`.
- Produces: unchanged contracts for `GET /api/vocab-quiz-attempts`, `GET /api/vocab-quiz-attempts/weak-words`, `POST /api/vocab-quiz-attempts`, and the analytics endpoints. `_load_attempts()` return type changes from `List[sqlite3.Row]` to `List[dict]`; the `import sqlite3` at the top of the analytics router is deleted.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_vocab_quiz_db.py`:

```python
"""Quiz attempts and the weak-words query against PostgreSQL JSONB."""


def _attempt(attempt_id: str, completed_at: str, results: list, **overrides) -> dict:
    payload = {
        "id": attempt_id,
        "storyId": "teacher-story-1",
        "studentName": "Mai",
        "studentId": "stu-1",
        "mode": "tier2",
        "completedAt": completed_at,
        "totalQuestions": len(results),
        "correctCount": sum(1 for r in results if r["correct"]),
        "totalTimeMs": sum(r["timeMs"] for r in results),
        "questionResults": results,
    }
    payload.update(overrides)
    return payload


def test_attempt_round_trips_with_question_results(client):
    attempt = _attempt("att-1", "2026-07-26T08:00:00Z", [
        {"word": "房間", "correct": True, "timeMs": 1200},
        {"word": "桌子", "correct": False, "timeMs": 3400},
    ])
    assert client.post("/api/vocab-quiz-attempts", json=attempt).status_code == 200

    saved = client.get("/api/vocab-quiz-attempts", params={"story_id": "teacher-story-1"}).json()
    assert len(saved) == 1
    assert saved[0]["questionResults"][0]["word"] == "房間"
    assert saved[0]["correctCount"] == 1
    assert saved[0]["mode"] == "tier2"


def test_attempts_filter_by_student_id(client):
    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-1", "2026-07-26T08:00:00Z",
        [{"word": "房間", "correct": True, "timeMs": 1000}]))
    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-2", "2026-07-26T09:00:00Z",
        [{"word": "床", "correct": True, "timeMs": 1000}],
        studentId="stu-2", studentName="An"))

    mine = client.get("/api/vocab-quiz-attempts", params={"student_id": "stu-1"}).json()
    assert [a["id"] for a in mine] == ["att-1"]


def test_weak_words_uses_the_most_recent_answer(client):
    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-old", "2026-07-25T08:00:00Z", [
            {"word": "房間", "correct": False, "timeMs": 4000},
            {"word": "桌子", "correct": False, "timeMs": 4000},
        ]))
    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-new", "2026-07-26T08:00:00Z", [
            {"word": "房間", "correct": True, "timeMs": 1100},
        ]))

    weak = client.get("/api/vocab-quiz-attempts/weak-words", params={
        "story_id": "teacher-story-1", "student_id": "stu-1"}).json()
    # 房間 was fixed in the newer attempt; 桌子 is still wrong.
    assert weak["words"] == ["桌子"]


def test_weak_words_requires_a_student_identifier(client):
    response = client.get("/api/vocab-quiz-attempts/weak-words", params={
        "story_id": "teacher-story-1"})
    assert response.status_code == 400


def test_frex_analytics_reads_question_results_from_jsonb(client):
    """The analytics loaders stopped calling json.loads — this proves they
    still see the per-question data, end to end through the real endpoint."""
    client.post("/api/students", json={"name": "Mai"})
    roster = client.get("/api/students").json()
    mai_id = roster[0]["id"]

    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-1", "2026-07-26T08:00:00Z", [
            {"word": "房間", "correct": False, "timeMs": 4000},
            {"word": "桌子", "correct": True, "timeMs": 1100},
        ], studentId=mai_id))

    response = client.get("/api/analytics/vocab-quiz/frex", params={"top": 5})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["studentId"] == mai_id
    assert rows[0]["name"] == "Mai"
    assert "房間" in [w["word"] for w in rows[0]["words"]]


def test_frex_analytics_on_an_empty_database(client):
    """The Insights tab blanks out entirely on a non-200, so no data must
    still be a well-formed empty response, not a 500."""
    response = client.get("/api/analytics/vocab-quiz/frex")
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_vocab_quiz_db.py -v
```

Expected: FAIL on placeholders.

- [ ] **Step 3: Port `routers/vocab_quiz.py`**

Add `from psycopg.types.json import Jsonb` to the imports. Replace the three query builders:

```python
    query = "SELECT * FROM vocab_quiz_attempts WHERE 1=1"
    params: list = []
    if story_id:
        query += " AND story_id = %s"
        params.append(story_id)
    if student_name:
        query += " AND student_name = %s"
        params.append(student_name)
    if student_id:
        query += " AND student_id = %s"
        params.append(student_id)
    query += " ORDER BY completed_at DESC"
```

```python
    query = "SELECT question_results FROM vocab_quiz_attempts WHERE story_id = %s"
    params: list = [story_id]
    if student_id:
        query += " AND student_id = %s"
        params.append(student_id)
    else:
        query += " AND student_name = %s"
        params.append(student_name)
    query += " ORDER BY completed_at DESC"
```

In the same endpoint, `question_results` is now JSONB — replace the parse:

```python
    resolved: dict[str, bool] = {}
    for row in rows:
        results = row["question_results"] or []
        for result in reversed(results):
```

And the insert:

```python
        db.execute(
            """
            INSERT INTO vocab_quiz_attempts
                (id, story_id, student_name, student_id, mode, completed_at,
                 total_questions, correct_count, total_time_ms, question_results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                story_id = EXCLUDED.story_id,
                student_name = EXCLUDED.student_name,
                student_id = EXCLUDED.student_id,
                mode = EXCLUDED.mode,
                completed_at = EXCLUDED.completed_at,
                total_questions = EXCLUDED.total_questions,
                correct_count = EXCLUDED.correct_count,
                total_time_ms = EXCLUDED.total_time_ms,
                question_results = EXCLUDED.question_results
            """,
            (
                attempt.id,
                attempt.storyId,
                attempt.studentName,
                attempt.studentId,
                attempt.mode,
                attempt.completedAt,
                attempt.totalQuestions,
                attempt.correctCount,
                attempt.totalTimeMs,
                Jsonb([r.model_dump() for r in attempt.questionResults]),
            ),
        )
```

Remove the now-unused `import json` from this file if nothing else uses it (check with `grep -n "json\." backend/routers/vocab_quiz.py`).

- [ ] **Step 4: Port `routers/vocab_quiz_analytics.py`**

Delete the `import sqlite3` line and change the two loaders:

```python
def _load_attempts(story_id: Optional[str] = None) -> List[dict]:
    query = "SELECT student_id, mode, question_results FROM vocab_quiz_attempts WHERE student_id IS NOT NULL"
    params: list = []
    if story_id:
        query += " AND story_id = %s"
        params.append(story_id)
    with connect_db() as db:
        return db.execute(query, params).fetchall()
```

Then, in `_accuracy_responses` and `_timed_responses`, replace both instances of:

```python
        for q in json.loads(row["question_results"] or "[]"):
```

with:

```python
        for q in row["question_results"] or []:
```

Remove `import json` if `grep -n "json\." backend/routers/vocab_quiz_analytics.py` returns nothing.

- [ ] **Step 5: Run the quiz tests and the whole existing quiz suite**

```bash
cd backend && python -m pytest tests/test_vocab_quiz_db.py tests/test_vocab_quiz_attempts.py tests/test_vocab_quiz_cloze.py tests/test_vocab_quiz_distractors.py tests/test_vocab_quiz_lookalike.py tests/test_vocab_quiz_synonym.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run the full backend suite**

```bash
cd backend && python -m pytest tests/ -q
```

Expected: every previously-passing test passes. Compare against the baseline recorded in Task 3 Step 8 — the only acceptable remaining failures are ones that were already failing before this migration started (the pre-existing failures noted in project memory). Write the exact failure list into the commit message if any remain.

- [ ] **Step 7: Commit**

```bash
git add backend/routers/vocab_quiz.py backend/routers/vocab_quiz_analytics.py backend/tests/test_vocab_quiz_db.py
git commit -m "feat(db): port vocab quiz attempts and analytics to PostgreSQL"
```

---

### Task 10: Scripts, deployment config, docs, and SQLite removal

**Files:**
- Modify: `backend/scripts/import_teacher_materials.py`
- Modify: `backend/scripts/export_teacher_materials.py`
- Modify: `backend/scripts/seed_grammar_lesson.py`, `seed_listen_retell_lesson.py`, `seed_vv_kan_lesson.py`
- Modify: `backend/Dockerfile`
- Modify: `render.yaml`
- Modify: `README.md`
- Modify: `start.ps1`
- Test: `backend/tests/test_no_sqlite_remains.py`

**Interfaces:**
- Consumes: everything from Tasks 1-9.
- Produces: no `sqlite3` import anywhere in `backend/` except `scripts/migrate_sqlite_to_postgres.py` (which reads the legacy file by design).

- [ ] **Step 1: Write the failing guard test**

Create `backend/tests/test_no_sqlite_remains.py`:

```python
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
```

- [ ] **Step 2: Run it to see which files still need porting**

```bash
cd backend && python -m pytest tests/test_no_sqlite_remains.py -v
```

Expected: FAIL, listing the five `scripts/*.py` files.

- [ ] **Step 3: Port `scripts/import_teacher_materials.py`**

Replace its direct `sqlite3.connect` usage with the shared pool. The column-detection at line 35 and the insert at line 86 become:

```python
from database import connect_db
from psycopg.types.json import Jsonb


def _story_columns() -> set:
    with connect_db() as db:
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'custom_stories'"
        ).fetchall()
    return {row["column_name"] for row in rows}
```

and

```python
        db.execute(
            """
            INSERT INTO custom_stories
                (id, title, learning_goal, frames, published, linear,
                 lesson_number, narrative_mode, first_frame_is_example)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                learning_goal = EXCLUDED.learning_goal,
                frames = EXCLUDED.frames,
                published = EXCLUDED.published,
                linear = EXCLUDED.linear,
                lesson_number = EXCLUDED.lesson_number,
                narrative_mode = EXCLUDED.narrative_mode,
                first_frame_is_example = EXCLUDED.first_frame_is_example
            """,
            (story_id, title, learning_goal, Jsonb(frames), published, linear,
             lesson_number, narrative_mode, first_frame_is_example),
        )
```

Read the file first — variable names differ from these placeholders; keep the file's own names and only change the connection, the placeholders, the `Jsonb()` wrapping of `frames`, and `INSERT OR REPLACE` → `ON CONFLICT`.

- [ ] **Step 4: Port `export_teacher_materials.py` and the three seed scripts**

Apply the same three mechanical changes to each: `sqlite3.connect(...)` → `connect_db()`, `?` → `%s`, `INSERT OR REPLACE INTO custom_stories (...)` → the `ON CONFLICT (id) DO UPDATE SET ...` form from Step 3, and `json.dumps(frames)` → `Jsonb(frames)`. In the export script, `row["frames"]` is now a parsed list — where it previously did `json.loads(row["frames"])`, use `row["frames"]` directly, and where it writes the value into the export zip, wrap it back with `json.dumps(row["frames"], ensure_ascii=False)`.

- [ ] **Step 5: Verify a seed script still works end to end**

```bash
cd backend && python scripts/seed_grammar_lesson.py
docker exec -it mandarin-postgres psql -U mandarin -d mandarin -c "SELECT id, title FROM custom_stories ORDER BY created_at DESC LIMIT 3;"
```

Expected: the seeded story appears with readable Chinese text.

- [ ] **Step 6: Update the Dockerfile**

In `backend/Dockerfile`, remove the SQLite line from the ENV block:

```dockerfile
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UPLOAD_DIR=/data/uploads
```

and update the comment above it:

```dockerfile
# - PYTHONUNBUFFERED: stream logs straight to stdout (no buffering)
# - PYTHONDONTWRITEBYTECODE: no .pyc clutter
# - data dir for uploaded audio/images (mount a volume here so they survive
#   container restarts). The database now lives in PostgreSQL — set
#   DATABASE_URL at run time.
```

Change the startup command so migrations run before the server, since the schema is no longer created by the app:

```dockerfile
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
```

- [ ] **Step 7: Update `render.yaml`**

Add a managed Postgres and wire its URL in:

```yaml
databases:
  - name: mandarin-postgres
    plan: free
    databaseName: mandarin
    user: mandarin

services:
  - type: web
    name: mandarin-speaking-backend
    env: docker
    rootDir: backend
    dockerfilePath: ./Dockerfile
    plan: free
    healthCheckPath: /health
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: mandarin-postgres
          property: connectionString
      - key: CORS_ORIGINS
        value: http://localhost:5173,http://127.0.0.1:5173,https://marktran0710.github.io
      - key: OPENAI_FEEDBACK_MODEL
        value: gpt-4o-mini
      - key: GEMINI_FEEDBACK_MODEL
        value: gemini-2.0-flash
```

- [ ] **Step 8: Update the local start script and README**

In `start.ps1`, add a line before the backend launch:

```powershell
docker compose up -d db
```

In `README.md`, find the section describing the SQLite database and replace it with:

```markdown
### Database

The backend uses PostgreSQL 17, run locally through Docker Compose:

```bash
docker compose up -d db          # start (data lives in the mandarin_pgdata volume)
cd backend && python -m alembic upgrade head   # apply schema migrations
```

The connection string comes from `DATABASE_URL` (default
`postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin`). Tests run against a
separate `mandarin_test` database and truncate every table between tests.

Schema changes are Alembic migrations in `backend/migrations/versions/` — the
app no longer creates or alters tables at startup.

The pre-migration SQLite file (`backend/mandarin_stories.db`) is kept on disk
as a backup. To re-import it:

```bash
cd backend && python -m scripts.migrate_sqlite_to_postgres
```
```

- [ ] **Step 9: Run the guard test and the full suite**

```bash
cd backend && python -m pytest tests/test_no_sqlite_remains.py -v && python -m pytest tests/ -q
```

Expected: guard test PASSES; the full suite matches the Task 9 Step 6 result with no new failures.

- [ ] **Step 10: Verify the running app end to end**

```bash
cd backend && python -m uvicorn main:app --port 8000
```

In another terminal:

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/api/custom-stories?limit=3"
```

Expected: `/health` returns `{"status":"ok",...,"database":"ok"}`, and the stories endpoint returns real migrated stories with readable Chinese titles. Then start the frontend (`npm run dev`), log in as a student, open a published story, and confirm the picture, vocabulary, and quiz all load.

- [ ] **Step 11: Commit**

```bash
git add backend/scripts backend/Dockerfile render.yaml README.md start.ps1 backend/tests/test_no_sqlite_remains.py
git commit -m "chore(db): finish the PostgreSQL cut-over and remove SQLite code paths"
```

---

## Why PostgreSQL rather than MySQL

Recorded here so the choice is auditable later. Based on the actual data (443 rows, 5.5 MB, 6 tables, 6 JSON columns):

1. **JSONB is the whole ballgame.** Five of six tables carry a JSON column, and `custom_stories.frames` reaches 34 KB per row. Postgres stores JSONB parsed and binary, indexes it with GIN, and updates a single path with `jsonb_set` — which is exactly what the four quiz-pool PATCH endpoints do all day. MySQL's JSON type has no GIN equivalent (only functional indexes on extracted scalars) and its partial-update path is narrower.
2. **The analytics workload is relational-analytical.** `vocab_quiz_analytics.py` runs Rasch/IRT and FREX over `question_results`. Postgres can expand that array into rows with `jsonb_array_elements` and aggregate with `percentile_cont`, `FILTER (WHERE ...)`, and LATERAL joins — the sibling `quiz-analytics-api` project wants the same shapes. MySQL forces most of it back into Python.
3. **`INSERT OR REPLACE` maps cleanly onto `ON CONFLICT DO UPDATE`,** which also fixes the column-wiping bug described at the top of this plan. MySQL's `ON DUPLICATE KEY UPDATE` works but requires restating every column.
4. **Unicode.** Everything user-facing is Traditional Chinese. Postgres is UTF-8 end to end; MySQL still carries the `utf8` vs `utf8mb4` trap and index-prefix limits on text keys.
5. **Transactional DDL.** Postgres runs `ALTER TABLE` inside a transaction, so a failed Alembic migration rolls back whole. MySQL auto-commits DDL and leaves a half-applied schema.

Honest counterpoint: at 443 rows, SQLite is not the bottleneck — nothing here is slow. The reasons to move are the single-writer limit under WAL, the lack of schema-change discipline (`ensure_column` at startup), and the analytics ambitions. If those three did not matter, staying on SQLite would be defensible.

## Out of scope

- **Frontend changes.** `src/services/database.ts` and the `teacherCustomStories` localStorage mirror stay exactly as they are; every API contract in this plan is unchanged.
- **Normalising `frames` into tables.** Explicitly chosen against — the frontend's `CustomStoryFrame` shape is the storage shape.
- **Moving `backend/uploads/` (166 MB) into the database.** Files stay on disk; the DB keeps `/uploads/...` URLs.
- **Authentication.** The plaintext student password and the absent teacher password are unchanged; see the role-separation decision in project memory.
- **Merging with the `quiz-analytics-api` project's database.** Separate repo, separate database.
