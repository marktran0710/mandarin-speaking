import json

from benchmarking.kpi_release_gate import build_kpi_report, evaluate_kpi_gate, write_kpi_artifacts
from scripts.gate_kpi_release import main


def passing_report():
    return {
        "provenance": {"model_version": "v2-test", "schema_version": "analysis_v2.test.v1"},
        "test_set": {"sealed": True},
        "dataset": {"speaker_count": 40},
        "character_alignment": {"success": 0.96, "human_usable_boundaries": 0.91},
        "phone_alignment": {"within_30ms": 0.81, "gold_count": 300},
        "phone_recognition": {"f1": 0.82, "per_phone": {"initial": {"f1": 0.81}, "final": {"f1": 0.82}}},
        "tone_detection": {
            "accuracy": 0.83,
            "macro_f1": 0.82,
            "per_tone": {tone: {"precision": 0.81, "recall": 0.81, "f1": 0.81, "support": 50} for tone in ("T1", "T2", "T3", "T4", "T5")},
        },
        "detection": {"coverage": 0.84, "unknown_rate": 0.16},
        "correct_incorrect": {"balanced_accuracy": 0.82, "sensitivity": 0.81, "specificity": 0.83},
        "audio_qc": {"auc": 0.82, "usable_retention": 0.84, "unusable_recall": 0.81, "reviewed_count": 300, "unusable_count": 100},
        "high_confidence_pass": {"precision": 0.93},
        "calibration": {"ece": 0.09},
        "speaker_robustness": {"min_balanced_accuracy": 0.71},
        "split": {"speaker_overlap": 0},
    }


def test_all_non_t5_kpis_are_required_for_owner_pilot_ready():
    result = evaluate_kpi_gate(passing_report())
    assert result.status == "PASS"
    assert result.release_status == "OWNER_PILOT_READY"


def test_missing_t5_support_is_deferred_for_current_pilot():
    report = passing_report()
    del report["tone_detection"]["per_tone"]["T5"]["support"]
    result = evaluate_kpi_gate(report)
    assert result.status == "PASS"
    assert "t5_test_support" in result.deferred_metrics


def test_strict_mode_can_require_t5_for_future_release():
    report = passing_report()
    del report["tone_detection"]["per_tone"]["T5"]["support"]
    from benchmarking.kpi_release_gate import KpiThresholds
    result = evaluate_kpi_gate(report, KpiThresholds(require_t5=True))
    assert result.status == "NEEDS_DATA"
    assert "t5_test_support" in result.missing_metrics


def test_per_tone_failure_blocks_even_when_overall_tone_accuracy_passes():
    report = passing_report()
    report["tone_detection"]["per_tone"]["T3"]["f1"] = 0.79
    result = evaluate_kpi_gate(report)
    assert result.status == "FAIL"
    assert "t3_f1" in result.failed_metrics


def test_artifact_bundle_and_cli(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(passing_report()), encoding="utf-8")
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([{"expected_tone": "T5", "detected_tone": "Unknown", "speaker_id": "s1"}]), encoding="utf-8")
    output_dir = tmp_path / "artifacts"
    assert main(["--report", str(report_path), "--rows", str(rows_path), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "kpi_report.json").exists()
    assert (output_dir / "kpi_rows.csv").exists()
    assert (output_dir / "tone_confusion_matrix.json").exists()
    assert (output_dir / "phone_boundary_report.json").exists()
    assert (output_dir / "kpi_dashboard.md").exists()
    assert "KPI STATUS: PASS" in capsys.readouterr().out


def test_row_summary_keeps_t5_and_unknown_distinct():
    report = build_kpi_report(
        [
            {"speaker_id": "s1", "expected_tone": "T5", "detected_tone": "T5"},
            {"speaker_id": "s2", "expected_tone": "T5", "detected_tone": "Unknown"},
        ],
        {"model_version": "v2", "schema_version": "v1", "speaker_overlap": 0},
    )
    assert report["tone_detection"]["per_tone"]["T5"]["support"] == 2
    assert report["detection"]["unknown_rate"] == 0.5
