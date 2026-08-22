import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routers.analysis_v2 import _character_contour, analysis_v2_health, build_character_prosody  # noqa: E402


class Metrics:
    word_prosody = [
        {
            "token": "你好",
            "start_time": 0.0,
            "end_time": 1.0,
            "confidence": 0.9,
            "pitch_contour": [(0.0, 220.0), (0.1, 225.0), (0.2, 230.0), (0.3, 235.0)],
            "syllables": [{"char": "你"}, {"char": "好"}],
        }
    ]


def test_v2_character_and_phone_schema_keeps_t5_separate():
    records = build_character_prosody(Metrics(), "你好", "ni3 hao5")
    assert [record["char"] for record in records] == ["你", "好"]
    assert records[0]["expected_tone"] == 3
    assert records[1]["expected_tone"] == 5
    assert records[1]["tone_status"] == "neutral_model_unavailable"
    assert records[0]["phones"]
    assert set(records[0]["tone_probabilities"]) == {"1", "2", "3", "4", "5"}


def test_v2_without_aligner_output_exposes_unknown_characters():
    class Empty:
        word_prosody = []

    records = build_character_prosody(Empty(), "学", "xue2")
    assert records[0]["detected_tone"] is None
    assert records[0]["tone_status"] == "unknown"


def test_character_projection_uses_contiguous_acoustic_spans_not_interleaved_frames():
    contour = [(index / 10, 200.0 + index) for index in range(8)]
    first = _character_contour(contour, 0, 2)
    second = _character_contour(contour, 1, 2)
    assert first == contour[:4]
    assert second == contour[4:]
    assert not set(first).intersection(second)


def test_v2_tone_evidence_uses_only_contiguous_audio_and_is_not_calibrated(monkeypatch):
    import routers.analysis_v2 as analysis_v2

    calls = []

    def fake_detect(contour):
        calls.append(list(contour))
        return {"detected_tone": 1, "scores": {1: 60.0, 2: 30.0, 3: 10.0, 4: 0.0}}

    class TwoCharacters:
        word_prosody = [{
            "token": "AB", "start_time": 0.0, "end_time": 0.7, "confidence": 0.9,
            "pitch_contour": [(index / 10, 180.0 + index) for index in range(8)],
            "syllables": [{"char": "A"}, {"char": "B"}],
        }]

    monkeypatch.setattr(analysis_v2, "detect_tone", fake_detect)
    records = build_character_prosody(TwoCharacters(), "AB", "ma1 ma2")

    assert len(calls) == 2
    assert calls[0] == [(0.0, 180.0), (0.1, 181.0), (0.2, 182.0), (0.3, 183.0)]
    assert calls[1] == [(0.4, 184.0), (0.5, 185.0), (0.6, 186.0), (0.7, 187.0)]
    assert records[0]["tone_probabilities"] == {"1": 0.6, "2": 0.3, "3": 0.1, "4": 0.0, "5": None}
    assert records[0]["tone_probability_status"] == "uncalibrated_relative_evidence"
    assert records[0]["phone_alignment_status"] == "not_acoustically_aligned"
    assert records[0]["phones"][0]["boundary_confidence"] == 0.0


@pytest.mark.asyncio
async def test_v2_health_is_explicitly_experimental_and_not_progression_eligible():
    payload = await analysis_v2_health()
    assert payload["experimental"] is True
    assert payload["progression_eligible"] is False
    assert payload["t5_status"] == "needs_data"
    assert payload["deferred_requirements"] == ["T5 learner labels and sealed-test support"]
    assert payload["kpi_gate"]["status"] == "NEEDS_DATA"
    assert payload["kpi_gate"]["release_status"] == "EXPERIMENTAL"


def test_v2_routes_are_separate_from_stable_analyze_route():
    import main

    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    assert "/api/analyze" in paths
    assert "/api/analyze/v2" in paths
    assert "/api/analyze/stream" in paths
    assert not any(path.startswith("/api/benchmark") for path in paths)
