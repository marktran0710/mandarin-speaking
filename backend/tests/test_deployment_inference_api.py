"""Deployment-equivalent API tests for the frozen tone confirmer.

These exercise the real request path -- upload, decode, canonicalise, score,
respond -- without mounting the router on the public app. The router is
deliberately not registered in main.py; registering it is the act that exposes
the frozen system to users, and that waits for the human-validation gate.

    pytest backend/tests/test_deployment_inference_api.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from pronunciation.wav2vec_tone import deployment_api  # noqa: E402
from pronunciation.wav2vec_tone.deployment_inference import (  # noqa: E402
    CONTRACT_SAMPLE_RATE, PASS_MESSAGE, RETRY_MESSAGE, FrozenInferenceBundle,
    infer_tone_attempt, validate_expected_tone,
)

DATA_DIR = BACKEND / "pronunciation" / "wav2vec_tone" / "data"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "technical_verification" / "frozen_inference_bundle.npz").exists(),
    reason="inference bundle not built; run deployment_inference --build-bundle")


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(deployment_api.router)
    return TestClient(app)


@pytest.fixture(scope="module")
def tokens():
    """One non-Test native-reference token per tone."""
    rows = [r for r in csv.DictReader(MANIFEST.open(encoding="utf-8"))
            if r["split"] == "native_reference"]
    assert not any(r["split"] == "test" for r in rows), "TEST LOCK VIOLATION"
    chosen = {}
    for row in sorted(rows, key=lambda r: r["token_id"]):
        chosen.setdefault(row["expected_tone"], DATA_DIR / row["extracted_token_path"])
    return chosen


def post(client, path, tone, filename=None):
    with open(path, "rb") as handle:
        return client.post(
            "/api/tone-confirm/attempt",
            files={"audio": (filename or Path(path).name, handle.read(),
                             "application/octet-stream")},
            data={"expected_tone": tone, "item_id": "TEST"})


# --- response shape --------------------------------------------------------

@pytest.mark.parametrize("tone", ["1", "2", "3", "4"])
def test_valid_audio_returns_only_status_and_message(client, tokens, tone):
    response = post(client, tokens[tone], f"T{tone}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "message"}
    assert body["status"] in {"PASS", "RETRY"}
    assert body["message"] in {PASS_MESSAGE, RETRY_MESSAGE}


def test_tone_one_can_never_pass(client, tokens):
    """The frozen policy disables automatic PASS for T1 regardless of acoustics."""
    assert post(client, tokens["1"], "T1").json()["status"] == "RETRY"


# --- failure paths all degrade to RETRY ------------------------------------

@pytest.mark.parametrize("tone", ["5", "banana", "T9", "0", "two", "-1"])
def test_invalid_expected_tone_is_a_safe_retry(client, tokens, tone):
    """Over HTTP every label arrives as a string, so these are the reachable
    invalid values. Non-string types are covered by the validator unit tests."""
    response = post(client, tokens["2"], tone)
    assert response.status_code == 200
    assert response.json()["status"] == "RETRY"


@pytest.mark.parametrize("tone", ["", None])
def test_missing_expected_tone_is_rejected_or_retried(client, tokens, tone):
    """An absent field may be refused by request validation (422) or reach the
    validator (200 + RETRY). Both are safe; PASS is not."""
    response = post(client, tokens["2"], "" if tone is None else tone)
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        assert response.json()["status"] == "RETRY"


def test_trajectory_failure_is_a_safe_retry(client, tmp_path):
    silence = tmp_path / "silence.wav"
    sf.write(silence, np.zeros(int(0.25 * CONTRACT_SAMPLE_RATE), dtype=np.float32),
             CONTRACT_SAMPLE_RATE)
    assert post(client, silence, "T2").json()["status"] == "RETRY"


def test_unsupported_file_is_a_safe_retry(client, tmp_path):
    junk = tmp_path / "note.txt"
    junk.write_text("not audio", encoding="utf-8")
    assert post(client, junk, "T2").json()["status"] == "RETRY"


def test_empty_upload_is_a_safe_retry(client, tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    assert post(client, empty, "T2").json()["status"] == "RETRY"


def test_corrupted_audio_is_a_safe_retry(client, tmp_path):
    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"RIFF" + bytes(range(256)) * 8)
    assert post(client, corrupt, "T2").json()["status"] == "RETRY"


def test_no_failure_path_ever_returns_pass(client, tokens, tmp_path):
    """The safety invariant: unprocessable input must never be confirmed."""
    silence = tmp_path / "s.wav"
    sf.write(silence, np.zeros(int(0.2 * CONTRACT_SAMPLE_RATE), dtype=np.float32),
             CONTRACT_SAMPLE_RATE)
    junk = tmp_path / "j.txt"
    junk.write_text("x", encoding="utf-8")
    for path, tone in ((silence, "T2"), (junk, "T2"), (tokens["2"], "nonsense")):
        assert post(client, path, tone).json()["status"] != "PASS"


# --- browser-style ingest --------------------------------------------------

def test_48khz_browser_style_upload_is_read_not_discarded(client, tokens, tmp_path):
    """Opus at 48 kHz: the codec MediaRecorder uses, in a container we decode.

    The API runs the strict profile, so this is refused -- but the log proves
    the declared rate was read, which is the TV-F1 defect being regressed.
    """
    from math import gcd

    from scipy.signal import resample_poly

    audio, _ = sf.read(str(tokens["4"]), dtype="float32")
    divisor = gcd(48000, CONTRACT_SAMPLE_RATE)
    upsampled = resample_poly(audio, 48000 // divisor,
                              CONTRACT_SAMPLE_RATE // divisor).astype(np.float32)
    fixture = tmp_path / "browser.ogg"
    sf.write(fixture, upsampled, 48000, format="OGG", subtype="OPUS")

    response = post(client, fixture, "T4")
    assert response.status_code == 200
    assert response.json()["status"] == "RETRY"
    log = deployment_api.last_research_log()
    assert log["source_sample_rate"] == 48000
    assert log["failure_code"] == "sample_rate_not_native"


def _resample_to_file(audio, rate, path):
    from math import gcd

    from scipy.signal import resample_poly

    divisor = gcd(rate, CONTRACT_SAMPLE_RATE)
    resampled = resample_poly(audio, rate // divisor,
                              CONTRACT_SAMPLE_RATE // divisor).astype(np.float32)
    sf.write(path, resampled, rate)
    return path


@pytest.mark.parametrize("rate", [44100, 48000])
def test_strict_profile_refuses_non_native_rates(tokens, tmp_path, rate):
    """TV-F1 regression. The frozen model only ever saw natively-16 kHz audio,
    so the strict profile refuses resampled input instead of absorbing it."""
    bundle = FrozenInferenceBundle.load()
    audio, _ = sf.read(str(tokens["4"]), dtype="float32")
    path = _resample_to_file(audio, rate, tmp_path / f"r{rate}.wav")
    got = infer_tone_attempt(audio_path=path, expected_tone="T4", bundle=bundle)
    assert got["decision"] == "RETRY"
    assert got["failure_code"] == "sample_rate_not_native"


@pytest.mark.parametrize("rate", [44100, 48000])
def test_permissive_profile_canonicalises_and_flags(tokens, tmp_path, rate):
    """The permissive profile still reads the rate rather than discarding it --
    the actual TV-F1 defect -- and records that resampling happened."""
    bundle = FrozenInferenceBundle.load()
    audio, _ = sf.read(str(tokens["4"]), dtype="float32")
    path = _resample_to_file(audio, rate, tmp_path / f"r{rate}.wav")
    got = infer_tone_attempt(audio_path=path, expected_tone="T4", bundle=bundle,
                             require_native_rate=False)
    assert got["source_sample_rate"] == rate
    assert got["resampled"] is True
    assert got["rate_profile"] == "permissive_resample"
    assert got["decision"] in {"PASS", "RETRY"}


def test_native_16k_is_unaffected_by_the_rate_gate(tokens):
    bundle = FrozenInferenceBundle.load()
    for tone, path in tokens.items():
        got = infer_tone_attempt(audio_path=path, expected_tone=f"T{tone}",
                                 bundle=bundle)
        assert got["failure_code"] != "sample_rate_not_native"
        assert got["resampled"] is False


def test_below_contract_sample_rate_is_refused(tokens, tmp_path):
    """8 kHz is below anything the frozen model was fitted on. Upsampling it
    was measured to flip a near-threshold verdict, so it is refused instead."""
    bundle = FrozenInferenceBundle.load()
    audio, _ = sf.read(str(tokens["4"]), dtype="float32")
    path = _resample_to_file(audio, 8000, tmp_path / "r8000.wav")
    got = infer_tone_attempt(audio_path=path, expected_tone="T4", bundle=bundle)
    assert got["decision"] == "RETRY"
    assert got["failure_code"] == "sample_rate_below_contract"


# --- privacy ---------------------------------------------------------------

def test_response_never_leaks_score_or_diagnosis(client, tokens):
    forbidden = ("wrong", "incorrect", "instead of", "%", "score", "probability",
                 "tone 1", "tone 2", "tone 3", "tone 4", "traceback")
    for tone, path in tokens.items():
        body = json.dumps(post(client, path, f"T{tone}").json()).lower()
        assert not any(term in body for term in forbidden)
        assert not any(character.isdigit() for character in body)


def test_research_log_keeps_the_score_server_side(client, tokens):
    post(client, tokens["2"], "T2")
    log = deployment_api.last_research_log()
    assert "raw_score" in log
    assert log["fitted_model_sha256"]
    assert log["system_sha256"]


# --- validation unit -------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [("1", "1"), ("T2", "2"), (" t3 ", "3"),
                                          ("4", "4")])
def test_valid_tone_labels_normalise(raw, expected):
    assert validate_expected_tone(raw) == expected


@pytest.mark.parametrize("raw", [None, 2, 2.0, True, [2], {"t": 2}, b"2", "",
                                 "5", "T5", "two"])
def test_invalid_tone_labels_raise(raw):
    with pytest.raises(ValueError):
        validate_expected_tone(raw)


# --- determinism -----------------------------------------------------------

def test_repeated_calls_are_deterministic(client, tokens):
    first = [post(client, tokens[t], f"T{t}").json() for t in ("1", "2", "3", "4")]
    second = [post(client, tokens[t], f"T{t}").json() for t in ("1", "2", "3", "4")]
    assert first == second


def test_startup_fails_closed_on_a_tampered_bundle():
    from pronunciation.wav2vec_tone.deployment_inference import ContractViolation

    bundle = FrozenInferenceBundle.load()
    bundle.metadata = dict(bundle.metadata, fitted_model_sha256="0" * 64)
    with pytest.raises(ContractViolation):
        bundle.verify_startup()
