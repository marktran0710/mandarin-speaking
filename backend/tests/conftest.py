"""Shared pytest fixtures for ASR tests."""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fixtures import SILENT_WAV, SHORT_WAV, LONG_WAV  # noqa: F401


# ── Environment fixtures ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_asr_globals():
    """Reset lazy-loaded model globals between tests."""
    import services.asr as asr
    original_funasr    = asr._funasr_model
    original_ctwhisp   = asr._ct_whisper_model
    original_vibevoice = asr._vibevoice_asr_model
    original_vv_error  = asr._vibevoice_load_error

    yield

    asr._funasr_model        = original_funasr
    asr._ct_whisper_model    = original_ctwhisp
    asr._vibevoice_asr_model = original_vibevoice
    asr._vibevoice_load_error = original_vv_error


@pytest.fixture()
def with_openai_key(monkeypatch):
    monkeypatch.setattr("services.asr.OPENAI_API_KEY", "sk-test-openai-key")


@pytest.fixture()
def with_gemini_key(monkeypatch):
    monkeypatch.setattr("services.asr.GEMINI_API_KEY", "test-gemini-key")


@pytest.fixture()
def no_openai_key(monkeypatch):
    monkeypatch.setattr("services.asr.OPENAI_API_KEY", None)


@pytest.fixture()
def no_gemini_key(monkeypatch):
    monkeypatch.setattr("services.asr.GEMINI_API_KEY", None)


# ── FastAPI test client ────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as c:
        yield c
