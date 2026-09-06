from analytics.bkt_calibration import calibrate_bkt
from analytics.knowledge_tracing import BKTParameters, ResponseRecord


def make_records(students=25, per_student=20):
    return [
        ResponseRecord(f"student-{student:02d}", f"concept-{index % 10}", bool((student + index) % 2), None, f"attempt-{student}", index)
        for student in range(students) for index in range(per_student)
    ]


def test_calibration_is_deterministic_and_has_no_student_leakage():
    records = make_records()
    first = calibrate_bkt(records, iterations=5)
    second = calibrate_bkt(reversed(records), iterations=5)

    assert first["digest"] == second["digest"]
    assert first["fold_assignments"] == second["fold_assignments"]
    assert first["metrics"] == second["metrics"]
    assert all(not fold["student_overlap"] for fold in first["folds"])
    assert {fold["fold"] for fold in first["folds"]} == set(range(5))


def test_candidate_constraints_reject_parameters_near_bounds(monkeypatch):
    near_bound = BKTParameters(prior=0.014, learn=0.1, guess=0.2, slip=0.1)

    def fit(*_args, **_kwargs):
        return near_bound, {"status": "success", "optimizer": "test", "message": "ok", "iterations": 1, "objective": 1.0, "finite": True}

    monkeypatch.setattr("analytics.bkt_calibration.fit_bkt_parameters", fit)
    result = calibrate_bkt(make_records())
    assert result["parameter_constraints"]["prior"] is False
    assert result["gates"]["parameter_constraints"] is False
    assert result["promotable"] is False


def test_insufficient_data_cannot_be_promoted():
    result = calibrate_bkt(make_records(students=2, per_student=4), iterations=2)
    assert result["gates"]["minimum_records"] is False
    assert result["gates"]["minimum_qualifying_students"] is False
    assert result["promotable"] is False


def test_synthetic_run_is_never_promotable(monkeypatch):
    accepted = BKTParameters(prior=0.2, learn=0.15, guess=0.2, slip=0.1)

    def fit(*_args, **_kwargs):
        return accepted, {"status": "success", "optimizer": "test", "message": "ok", "iterations": 1, "objective": 1.0, "finite": True}

    monkeypatch.setattr("analytics.bkt_calibration.fit_bkt_parameters", fit)
    result = calibrate_bkt(make_records(), synthetic=True)
    assert result["synthetic"] is True
    assert result["promotable"] is False


def test_optimizer_failure_blocks_promotion(monkeypatch):
    def fail(*_args, **_kwargs):
        return BKTParameters(), {"status": "failed", "optimizer": "test", "message": "failed", "iterations": 1, "objective": None, "finite": False}

    monkeypatch.setattr("analytics.bkt_calibration.fit_bkt_parameters", fail)
    result = calibrate_bkt(make_records())
    assert result["gates"]["all_optimizers_converged"] is False
    assert result["promotable"] is False
