"""Strict, machine-readable release criteria for Mandarin tone feedback.

This module only consumes an already-generated benchmark JSON report. It does
not run the scorer or tune a threshold, which makes it safe to use as a
separate CI/CD release gate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


_MISSING = object()


@dataclass(frozen=True)
class ToneReleaseThresholds:
    """Minimum evidence and quality required for a student-facing release."""

    min_recording_count: int = 800
    min_speaker_count: int = 40
    min_accuracy: float = 0.85
    min_kappa: float = 0.70
    min_per_tone_f1: float = 0.80
    max_false_positive_rate: float = 0.05
    max_mean_absolute_error: float = 12.0
    min_spearman_correlation: float = 0.75


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    actual: float | None
    operator: str
    threshold: float
    detail: str = ""


@dataclass(frozen=True)
class ToneReleaseGateResult:
    checks: tuple[GateCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def _nested(report: Mapping[str, Any], *path: str) -> Any:
    current: Any = report
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _valid_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _comparison_check(
    name: str,
    value: Any,
    operator: str,
    threshold: float,
    *,
    valid_min: float | None = None,
    valid_max: float | None = None,
    detail: str = "",
) -> GateCheck:
    actual = _valid_number(value)
    invalid = actual is None
    if actual is not None and valid_min is not None and actual < valid_min:
        invalid = True
    if actual is not None and valid_max is not None and actual > valid_max:
        invalid = True

    if value is _MISSING or value is None:
        reason = "required metric is missing"
    elif invalid:
        reason = "metric is not a finite number in the valid range"
    else:
        reason = detail

    passed = False
    if not invalid and value is not _MISSING and value is not None:
        passed = actual >= threshold if operator == ">=" else actual <= threshold
    return GateCheck(name, passed, actual, operator, threshold, reason)


def _false_positive_rate(report: Mapping[str, Any]) -> tuple[Any, str]:
    explicit = _nested(report, "pass_fail_agreement", "false_positive_rate")
    if explicit is not _MISSING:
        return explicit, "reported directly"

    false_positive = _valid_number(
        _nested(report, "pass_fail_agreement", "false_positive")
    )
    true_negative = _valid_number(
        _nested(report, "pass_fail_agreement", "true_negative")
    )
    if (
        false_positive is None
        or true_negative is None
        or false_positive < 0
        or true_negative < 0
        or false_positive + true_negative <= 0
    ):
        return _MISSING, (
            "required metric is missing and cannot be derived from "
            "false_positive and true_negative"
        )
    return (
        false_positive / (false_positive + true_negative),
        "derived as false_positive / (false_positive + true_negative)",
    )


def evaluate_tone_release_gate(
    report: Mapping[str, Any],
    thresholds: ToneReleaseThresholds | None = None,
) -> ToneReleaseGateResult:
    """Evaluate every release criterion without short-circuiting."""

    if not isinstance(report, Mapping):
        raise TypeError("benchmark report must be a JSON object")
    limits = thresholds or ToneReleaseThresholds()
    checks = [
        _comparison_check(
            "recording_count",
            _nested(report, "benchmark_protocol", "recording_count"),
            ">=",
            limits.min_recording_count,
            valid_min=0,
        ),
        _comparison_check(
            "speaker_count",
            _nested(report, "benchmark_protocol", "speaker_count"),
            ">=",
            limits.min_speaker_count,
            valid_min=0,
        ),
        _comparison_check(
            "accuracy",
            _nested(report, "pass_fail_agreement", "accuracy"),
            ">=",
            limits.min_accuracy,
            valid_min=0,
            valid_max=1,
        ),
        _comparison_check(
            "cohen_kappa",
            _nested(report, "pass_fail_agreement", "cohen_kappa"),
            ">=",
            limits.min_kappa,
            valid_min=-1,
            valid_max=1,
        ),
    ]

    for tone in ("1", "2", "3", "4"):
        checks.append(
            _comparison_check(
                f"tone_{tone}_f1",
                _nested(report, "by_expected_tone", tone, "f1"),
                ">=",
                limits.min_per_tone_f1,
                valid_min=0,
                valid_max=1,
            )
        )

    false_positive_rate, rate_detail = _false_positive_rate(report)
    checks.extend(
        [
            _comparison_check(
                "false_positive_rate",
                false_positive_rate,
                "<=",
                limits.max_false_positive_rate,
                valid_min=0,
                valid_max=1,
                detail=rate_detail,
            ),
            _comparison_check(
                "mean_absolute_error",
                _nested(report, "score_agreement", "mean_absolute_error"),
                "<=",
                limits.max_mean_absolute_error,
                valid_min=0,
            ),
            _comparison_check(
                "spearman_correlation",
                _nested(report, "score_agreement", "spearman_correlation"),
                ">=",
                limits.min_spearman_correlation,
                valid_min=-1,
                valid_max=1,
            ),
        ]
    )
    return ToneReleaseGateResult(tuple(checks))
