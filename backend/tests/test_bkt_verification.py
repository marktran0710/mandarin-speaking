import pytest

from services.bkt_verification_service import build_golden_report


def test_golden_report_uses_the_versioned_contract_and_passes_all_checks():
    report = build_golden_report()

    assert report["fixtureVersion"] == "format-aware-bkt-v2"
    assert report["contractStatus"] == "MATCH"
    assert report["summary"] == {"passed": 7, "total": 7}
    assert all(check["result"] == "PASS" for check in report["checks"])


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("No response", 0.2),
        ("One MCQ correct", 0.6),
        ("One MCQ incorrect", 0.17575757575757578),
        ("One typed correct", 0.8380952380952381),
        ("One typed incorrect", 0.1822784810126582),
        ("Three MCQ correct", 0.9773510971786833),
        ("Mixed golden vector", 0.9979619773755845),
    ],
)
def test_golden_scenarios_keep_the_reviewed_expected_outputs(scenario, expected):
    report = build_golden_report()
    check = next(item for item in report["checks"] if item["scenario"] == scenario)

    assert check["expected"]["pLearned"] == pytest.approx(expected)
