"""Reference-relative librosa comparison tests."""

import json
import sys

import numpy as np
import pytest

from pron_audio import silent_wav, synth_wav
from services.pronunciation.librosa_comparison import compare_recordings


def test_same_recording_has_high_reference_relative_similarity(tmp_path, monkeypatch):
    pytest.importorskip("librosa", reason="librosa optional dependency")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "true")
    audio = synth_wav(tmp_path / "same.wav", ["flat", "rise", "fall"])

    result = compare_recordings(audio, audio)

    assert result["status"] == "scored"
    measurements = result["measurements"]
    assert measurements["mfcc_similarity"] > .95
    assert measurements["pitch_similarity"] > .95
    assert measurements["duration_similarity"] == pytest.approx(1.0)
    assert result["debug"]["dtw_path_length"] > 0
    assert result["debug"]["dtw_path"][0] == [0, 0]
    assert result["parameters"]["sample_rate"] == 16000
    json.dumps(result, allow_nan=False)


def test_feature_flag_can_disable_optional_comparison(tmp_path, monkeypatch):
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "false")
    audio = synth_wav(tmp_path / "same.wav", ["flat"])

    result = compare_recordings(audio, audio)

    assert result == {
        "status": "unavailable",
        "backend": "librosa",
        "reason": "feature_flag_disabled",
        "measurements": {},
        "debug": {},
    }


def test_missing_optional_dependency_does_not_require_audio_io(monkeypatch):
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "true")
    monkeypatch.setitem(sys.modules, "librosa", None)
    result = compare_recordings("missing-reference.wav", "missing-student.wav")
    assert result["reason"] == "librosa_not_installed"


def test_no_paired_pitch_keeps_mfcc_and_timing_evidence(tmp_path, monkeypatch):
    librosa = pytest.importorskip("librosa", reason="librosa optional dependency")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "true")
    audio = synth_wav(tmp_path / "no-pitch.wav", ["rise", "fall"])

    def no_pitch(audio, **kwargs):
        frames = len(audio) // kwargs["hop_length"] + 1
        return np.full(frames, np.nan), np.zeros(frames, dtype=bool), np.zeros(frames)

    monkeypatch.setattr(librosa, "pyin", no_pitch)
    result = compare_recordings(audio, audio)
    assert result["status"] == "scored"
    assert result["evidence_quality"] == "degraded"
    assert result["measurements"]["mfcc_similarity"] == pytest.approx(1.0)
    assert result["measurements"]["duration_similarity"] == pytest.approx(1.0)
    assert result["measurements"]["pitch_similarity"] is None
    assert all(value is None for _, value in result["debug"]["student_pitch_contour"])
    json.dumps(result, allow_nan=False)


def test_dtw_budget_and_effective_parameters_are_recorded(tmp_path, monkeypatch):
    pytest.importorskip("librosa", reason="librosa optional dependency")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "true")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_MAX_DTW_FRAMES", "20")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_MFCC_DISTANCE_SCALE", "2")
    audio = synth_wav(tmp_path / "bounded.wav", ["rise", "fall"])
    result = compare_recordings(audio, audio)
    assert result["status"] == "scored"
    assert result["debug"]["dtw_frame_stride"] > 1
    assert result["debug"]["dtw_path_length"] <= 20
    assert result["parameters"]["mfcc_distance_scale"] == 2.0


def test_duration_limit_rejects_comparison_without_truncating_evidence(tmp_path, monkeypatch):
    pytest.importorskip("librosa", reason="librosa optional dependency")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "true")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_MAX_DURATION_SECONDS", "1")
    audio = synth_wav(tmp_path / "long.wav", ["flat", "rise", "fall"])
    result = compare_recordings(audio, audio)
    assert result["status"] == "unavailable"
    assert result["reason"] == "comparison_duration_limit_exceeded"
    assert result["measurements"] == {}


def test_silent_reference_is_unavailable_instead_of_dividing_by_zero(tmp_path, monkeypatch):
    pytest.importorskip("librosa", reason="librosa optional dependency")
    monkeypatch.setenv("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "true")
    reference = silent_wav(tmp_path / "silent.wav")
    student = synth_wav(tmp_path / "student.wav", ["flat"])
    result = compare_recordings(reference, student)
    assert result["status"] == "unavailable"
    assert result["reason"] == "no_active_audio"
