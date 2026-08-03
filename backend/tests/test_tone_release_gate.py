import json

from benchmarking.tone_release_gate import (
    ToneReleaseThresholds,
    evaluate_tone_release_gate,
)
from scripts.gate_tone_release import main


def _passing_report():
    return {
        "benchmark_protocol": {"recording_count": 800, "speaker_count": 40},
        "pass_fail_agreement": {
            "accuracy": 0.85,
            "cohen_kappa": 0.70,
            "false_positive": 5,
            "true_negative": 95,
        },
        "by_expected_tone": {
            tone: {"f1": 0.80} for tone in ("1", "2", "3", "4")
        },
        "score_agreement": {
            "mean_absolute_error": 12.0,
            "spearman_correlation": 0.75,
        },
    }


def test_strict_defaults_accept_boundary_values_and_derive_false_positive_rate():
    result = evaluate_tone_release_gate(_passing_report())

    assert result.passed
    rate = next(check for check in result.checks if check.name == "false_positive_rate")
    assert rate.actual == 0.05
    assert "derived" in rate.detail


def test_every_missing_required_metric_fails_including_each_tone():
    result = evaluate_tone_release_gate(
        {
            "benchmark_protocol": {},
            "pass_fail_agreement": {},
            "by_expected_tone": {"1": {}, "2": {}, "3": {}, "4": {}},
            "score_agreement": {},
        }
    )

    assert not result.passed
    assert len(result.checks) == 11
    assert all(not check.passed for check in result.checks)
    assert all(check.actual is None for check in result.checks)


def test_one_weak_tone_or_excess_false_positive_rate_blocks_release():
    report = _passing_report()
    report["by_expected_tone"]["3"]["f1"] = 0.79
    report["pass_fail_agreement"]["false_positive_rate"] = 0.051

    result = evaluate_tone_release_gate(report)

    failures = {check.name for check in result.checks if not check.passed}
    assert failures == {"tone_3_f1", "false_positive_rate"}


def test_configurable_thresholds_can_be_made_more_strict():
    report = _passing_report()
    result = evaluate_tone_release_gate(
        report,
        ToneReleaseThresholds(min_recording_count=1_000),
    )

    assert not result.passed
    assert [check.name for check in result.checks if not check.passed] == [
        "recording_count"
    ]


def test_cli_returns_zero_for_pass_and_one_for_quality_failure(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_passing_report()), encoding="utf-8")

    assert main(["--report", str(report_path)]) == 0
    assert "RELEASE GATE PASSED" in capsys.readouterr().out

    report = _passing_report()
    report["pass_fail_agreement"]["accuracy"] = 0.849
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["--report", str(report_path)]) == 1
    output = capsys.readouterr()
    assert "[FAIL] accuracy" in output.out
    assert "Do not release" in output.err


def test_cli_returns_two_for_invalid_json_or_non_object(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text("{", encoding="utf-8")
    assert main(["--report", str(report_path)]) == 2
    assert "invalid JSON" in capsys.readouterr().err

    report_path.write_text("[]", encoding="utf-8")
    assert main(["--report", str(report_path)]) == 2
    assert "JSON object" in capsys.readouterr().err
