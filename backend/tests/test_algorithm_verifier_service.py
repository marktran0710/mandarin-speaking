from datetime import datetime, timezone
from dataclasses import replace

import pytest

from services import algorithm_verifier_service as service


def test_bkt_calculation_returns_trace_and_clamps_boundary():
    result = service.calculate_bkt({
        "prior": 0.999999,
        "correct": False,
        "questionFormat": "mcq",
    })

    assert result["result"] == "PASS"
    assert result["production"]["prior"] == pytest.approx(0.999999)
    assert result["production"]["resultingMastery"] == pytest.approx(result["reference"]["resultingMastery"], abs=1e-12)
    assert 0.000001 <= result["production"]["resultingMastery"] <= 0.999999


def test_bkt_sequence_keeps_production_and_reference_independent():
    result = service.calculate_bkt({
        "prior": 0.2,
        "observations": [
            {"correct": False, "questionFormat": "mcq"},
            {"correct": True, "questionFormat": "typed"},
            {"correct": True, "questionFormat": "mcq"},
        ],
    })

    assert result["result"] == "PASS"
    assert len(result["production"]["trace"]) == 3
    assert result["production"]["resultingMastery"] == pytest.approx(0.9594954449894884)
    assert result["difference"] <= result["tolerance"]


def test_sm2_enrollment_and_rounding_are_reported_exactly():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    enrollment = service.calculate_sm2({"operation": "enroll", "now": now.isoformat(), "daySeconds": 60})
    assert enrollment["result"] == "PASS"
    assert enrollment["production"]["repetitions"] == 1
    assert enrollment["production"]["nextDue"] == "2026-08-01T00:01:00+00:00"

    rounded_down = service.calculate_sm2({"repetitions": 2, "intervalDays": 1, "ease": 2.5, "quality": 4, "now": now.isoformat(), "daySeconds": 60})
    rounded_up = service.calculate_sm2({"repetitions": 2, "intervalDays": 3, "ease": 2.5, "quality": 4, "now": now.isoformat(), "daySeconds": 60})
    assert rounded_down["production"]["intervalDays"] == 2
    assert rounded_up["production"]["intervalDays"] == 8
    assert rounded_up["rawInterval"] == pytest.approx(7.5)


def test_development_gate_rejects_persistent_mutations(monkeypatch):
    monkeypatch.setattr(service, "settings", replace(service.settings, app_env="production"))
    with pytest.raises(service.AlgorithmVerifierError, match="development"):
        service.reset_integration(None)
