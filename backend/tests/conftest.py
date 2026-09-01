"""Shared pytest fixtures for ASR tests."""
import os
import sys
import pytest
from dotenv import load_dotenv
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Must run before TEST_DATABASE_URL's os.getenv below - conftest.py is always
# collected before any test module (and before database.py's own
# load_dotenv() would otherwise run), so without this a .env override is
# silently ignored and the hardcoded default port wins instead.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env.local"))

# Tests must be runnable in a clean checkout where the developer-only
# backend/.env file is absent.  This key is intentionally scoped to pytest;
# production imports still fail fast when JWT_SECRET_KEY is not configured.
if len(os.getenv("JWT_SECRET_KEY", "")) < 16:
    os.environ["JWT_SECRET_KEY"] = "pytest-only-jwt-secret-not-for-production-7f3a"

from fixtures import SILENT_WAV, SHORT_WAV, LONG_WAV  # noqa: F401


# ── Environment fixtures ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_asr_globals():
    """Reset lazy-loaded model globals between tests."""
    import main
    original_funasr   = main._funasr_model
    original_ctwhisp  = main._ct_whisper_model
    original_vibevoice = main._vibevoice_asr_model
    original_vv_error  = main._vibevoice_load_error

    yield

    main._funasr_model       = original_funasr
    main._ct_whisper_model   = original_ctwhisp
    main._vibevoice_asr_model = original_vibevoice
    main._vibevoice_load_error = original_vv_error


@pytest.fixture()
def with_openai_key(monkeypatch):
    monkeypatch.setattr("main.OPENAI_API_KEY", "sk-test-openai-key")


@pytest.fixture()
def with_gemini_key(monkeypatch):
    monkeypatch.setattr("main.GEMINI_API_KEY", "test-gemini-key")


@pytest.fixture()
def no_openai_key(monkeypatch):
    monkeypatch.setattr("main.OPENAI_API_KEY", None)


@pytest.fixture()
def no_gemini_key(monkeypatch):
    monkeypatch.setattr("main.GEMINI_API_KEY", None)


@pytest.fixture()
def with_groq_key(monkeypatch):
    monkeypatch.setattr("main.GROQ_API_KEY", "gsk-test-groq-key")


@pytest.fixture()
def no_groq_key(monkeypatch):
    monkeypatch.setattr("main.GROQ_API_KEY", None)


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
    "speaking_progress",
    "story_submissions",
    "students",
    "teacher_pronunciation_ratings",
    "teachers",
    "vocab_quiz_attempts",
    "vocab_quiz_irt_cache",
    "vocab_quiz_responses",
    "student_vocab_mastery",
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
def client(use_test_database):
    from fastapi.testclient import TestClient
    import main
    import uuid
    with TestClient(main.app) as c:
        # Normal API tests operate as an authenticated staff member now that
        # roster/content endpoints are no longer anonymous. Tests that verify
        # the public boundary should use anonymous_client instead.
        staff_name = f"__test_staff__{uuid.uuid4()}"
        _insert_teacher_row(staff_name, "test-staff-password")
        c.post(
            "/api/teachers/login",
            json={"name": staff_name, "password": "test-staff-password"},
        )
        yield c


@pytest.fixture()
def anonymous_client(use_test_database):
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    """The shared test client with an admin session for provisioning tests."""
    import auth

    # ``client`` starts logged in as a staff teacher. Clear that session before
    # promoting this fixture to admin so httpx does not retain duplicate
    # compatibility cookies with the same name.
    client.cookies.clear()
    client.headers.pop(auth.CLIENT_ROLE_HEADER, None)
    client.cookies.set(
        auth.COOKIE_NAME,
        auth.issue_token("admin", "admin"),
        domain="testserver.local",
        path="/",
    )
    return client


@pytest.fixture()
def logged_in_student(admin_client):
    """A logged-in student: (client, student). The client's cookie jar
    carries its session, so requests through it act as this student -
    used by any test that needs to write/read student-scoped data."""
    password = "student-password"
    client = admin_client
    student = client.post(
        "/api/students", json={"name": "Test Student", "password": password}
    ).json()
    client.post(
        "/api/students/login",
        json={"studentId": student["id"], "password": password},
    )
    # admin_client intentionally starts with an admin cookie for provisioning.
    # Select the newly-created student session explicitly so the compatibility
    # cookie cannot make student-scoped requests resolve as admin.
    import auth
    client.headers[auth.CLIENT_ROLE_HEADER] = "student"
    return client, student


def _insert_teacher_row(name: str, password: str) -> dict:
    """Creates a teacher row directly in the DB, bypassing POST
    /api/teachers (which now requires an admin identity) - test setup
    needs a teacher to exist before it can log in as one, same problem
    a real admin-only signup flow has for its own tests."""
    import uuid

    import database

    with database.connect_db() as db:
        import auth

        row = db.execute(
            "INSERT INTO teachers (id, name, password) VALUES (%s, %s, %s) RETURNING *",
            (str(uuid.uuid4()), name, auth.hash_password(password)),
        ).fetchone()
    return database.row_to_teacher(row)


@pytest.fixture()
def logged_in_teacher(use_test_database):
    """A logged-in teacher: (client, teacher)."""
    import auth
    from fastapi.testclient import TestClient
    import main

    teacher = _insert_teacher_row("Test Teacher", "teach123")
    with TestClient(main.app) as client:
        client.post(
            "/api/teachers/login",
            json={"name": "Test Teacher", "password": "teach123"},
        )
        client.headers[auth.CLIENT_ROLE_HEADER] = "teacher"
        yield client, teacher


def login_new_client(stack, name, role, password="123456"):
    """A fresh TestClient (its own cookie jar), entered via an ExitStack
    the caller owns, logged in as a brand-new student or teacher - lets a
    test act as several independent identities at once. Returns
    (client, created_row)."""
    from fastapi.testclient import TestClient
    import main

    new_client = stack.enter_context(TestClient(main.app))
    if role == "student":
        import uuid
        import auth
        import database

        with database.connect_db() as db:
            created = db.execute(
                "INSERT INTO students (id, name, password) VALUES (%s, %s, %s) RETURNING *",
                (str(uuid.uuid4()), name, auth.hash_password(password)),
            ).fetchone()
        new_client.post(
            "/api/students/login",
            json={"studentId": created["id"], "password": password},
        )
    else:
        created = _insert_teacher_row(name, password)
        new_client.post(
            "/api/teachers/login", json={"name": name, "password": password}
        )
    return new_client, created
