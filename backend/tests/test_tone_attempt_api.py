"""Study API tests for the canonical tone-confirmation route.

Drives the real application with study mode on: the canonical route mounted,
the legacy pronunciation routes blocked.

    pytest backend/tests/test_tone_attempt_api.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ["OMPAL_STUDY_MODE"] = "1"

from pronunciation.wav2vec_tone.study_pcm16k import build_study_wav  # noqa: E402

DATA_DIR = BACKEND / "pronunciation" / "wav2vec_tone" / "data"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
BUNDLE = DATA_DIR / "technical_verification" / "frozen_inference_bundle.npz"

PASS_MESSAGE = "Your tone sounds acceptable. You can continue."
RETRY_MESSAGE = ("I'm not confident enough to confirm this attempt. "
                 "Please try once more.")
TECHNICAL_MESSAGE = "The recording could not be processed. Please record again."
ALLOWED_MESSAGES = {PASS_MESSAGE, RETRY_MESSAGE, TECHNICAL_MESSAGE}

pytestmark = pytest.mark.skipif(
    not BUNDLE.exists(),
    reason="inference bundle not built; run deployment_inference --build-bundle")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main

    assert main.STUDY_MODE_ACTIVE, "study mode must be active for these tests"
    return TestClient(main.app)


@pytest.fixture(scope="module")
def tokens():
    rows = [r for r in csv.DictReader(MANIFEST.open(encoding="utf-8"))
            if r["split"] == "native_reference"]
    assert not any(r["split"] == "test" for r in rows), "TEST LOCK VIOLATION"
    chosen = {}
    for row in sorted(rows, key=lambda r: r["token_id"]):
        chosen.setdefault(row["expected_tone"], DATA_DIR / row["extracted_token_path"])
    return chosen


def post(client, path, tone, item_id="TEST"):
    with open(path, "rb") as handle:
        payload = handle.read()
    return client.post(
        "/api/pronunciation/tone-attempt",
        files={"audio": (Path(path).name, payload, "audio/wav")},
        data={"expected_tone": tone, "item_id": item_id})


# --- response contract -----------------------------------------------------

@pytest.mark.parametrize("tone", ["1", "2", "3", "4"])
def test_response_carries_only_allowed_fields(client, tokens, tone):
    response = post(client, tokens[tone], f"T{tone}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"decision", "message", "technical_retry"}
    assert body["decision"] in {"PASS", "RETRY"}
    assert body["message"] in ALLOWED_MESSAGES


def test_tone_one_never_passes_end_to_end(client, tokens):
    assert post(client, tokens["1"], "T1").json()["decision"] == "RETRY"


def test_no_response_contains_a_digit(client, tokens):
    for tone, path in tokens.items():
        body = json.dumps(post(client, path, f"T{tone}").json())
        assert not any(character.isdigit() for character in body)


def test_no_response_contains_a_forbidden_term(client, tokens):
    forbidden = ("wrong", "incorrect", "instead of", "%", "score", "probability",
                 "detected", "traceback", "coefficient", "threshold")
    for tone, path in tokens.items():
        body = json.dumps(post(client, path, f"T{tone}").json()).lower()
        assert not any(term in body for term in forbidden)


# --- failure paths ---------------------------------------------------------

@pytest.mark.parametrize("tone", ["", "T9", "banana", "0", "5", "2.0", "two"])
def test_invalid_tone_is_a_uniform_technical_retry(client, tokens, tone):
    """No 422: a pydantic error body would leak field paths to a participant."""
    response = post(client, tokens["2"], tone)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "RETRY"
    assert body["technical_retry"] is True
    assert body["message"] == TECHNICAL_MESSAGE


def test_silence_is_a_safe_retry(client, tmp_path):
    silence = tmp_path / "silence.wav"
    sf.write(silence, np.zeros(4000, dtype=np.float32), 16000)
    assert post(client, silence, "T2").json()["decision"] == "RETRY"


def test_unsupported_and_empty_payloads_are_safe_retries(client, tmp_path):
    junk = tmp_path / "note.txt"
    junk.write_text("not audio", encoding="utf-8")
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    for path in (junk, empty):
        body = post(client, path, "T2").json()
        assert body["decision"] == "RETRY"
        assert body["technical_retry"] is True


def test_off_contract_sample_rate_is_refused(client, tmp_path):
    """strict_native: a 48 kHz upload is not silently canonicalised."""
    loud = 0.3 * np.sin(2 * np.pi * 200 * np.arange(12000) / 48000)
    path = tmp_path / "offrate.wav"
    sf.write(path, loud.astype(np.float32), 48000)
    body = post(client, path, "T2").json()
    assert body["decision"] == "RETRY"
    assert body["technical_retry"] is True


def test_no_degraded_input_ever_passes(client, tokens, tmp_path):
    silence = tmp_path / "s.wav"
    sf.write(silence, np.zeros(4000, dtype=np.float32), 16000)
    junk = tmp_path / "j.txt"
    junk.write_text("x", encoding="utf-8")
    empty = tmp_path / "e.wav"
    empty.write_bytes(b"")
    for path, tone in ((silence, "T2"), (junk, "T2"), (empty, "T2"),
                       (tokens["2"], "T9")):
        assert post(client, path, tone).json()["decision"] != "PASS"


# --- study capture path ----------------------------------------------------

def test_study_converted_audio_is_accepted(client, tokens, tmp_path):
    """A 48 kHz capture converted by STUDY_PCM16K_v1 satisfies strict_native."""
    from math import gcd

    from scipy.signal import resample_poly

    audio, _ = sf.read(str(tokens["2"]), dtype="float64")
    divisor = gcd(48000, 16000)
    captured = resample_poly(audio, 48000 // divisor, 16000 // divisor)
    blob, metadata = build_study_wav(captured, 48000)
    path = tmp_path / "study.wav"
    path.write_bytes(blob)

    assert metadata["output_sample_rate"] == 16000
    assert abs(metadata["output_duration_ms"] - metadata["input_duration_ms"]) < 0.1

    body = post(client, path, "T2").json()
    assert body["decision"] in {"PASS", "RETRY"}
    assert body["technical_retry"] is False


def test_repeated_requests_are_deterministic(client, tokens):
    first = [post(client, tokens[t], f"T{t}").json() for t in ("1", "2", "3", "4")]
    second = [post(client, tokens[t], f"T{t}").json() for t in ("1", "2", "3", "4")]
    assert first == second


# --- one engine ------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/analyze", "/api/analyze/stream"])
def test_legacy_pronunciation_routes_are_disabled(client, path):
    response = client.post(path)
    assert response.status_code == 503
    body = json.dumps(response.json()).lower()
    assert "tone_accuracy" not in body
    assert "detected_tone" not in body


def test_only_one_pronunciation_engine_is_mounted():
    import main

    paths = sorted(r.path for r in main.app.routes
                   if hasattr(r, "path") and "pronunciation" in r.path)
    assert paths == ["/api/pronunciation/tone-attempt",
                     "/api/pronunciation/tone-attempt/health"]


def test_health_reports_the_frozen_identity(client):
    body = client.get("/api/pronunciation/tone-attempt/health").json()
    assert body["ready"] is True
    assert body["scientific_version"] == "OMPAL_R2_PASS_v1"
    assert body["deployment_version"] == "OMPAL_R2_PASS_v1.1"
    assert body["audio_contract_version"] == "OMPAL_AUDIO_CONTRACT_v1"
    assert body["fitted_model_sha256"] == (
        "0dcee1d87c69c5b2586fa9612b142a6ac5ef48cd37cd06dfac984a5d463c586c")
