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
    "vocab_quiz_attempts",
    "vocab_quiz_irt_cache",
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
