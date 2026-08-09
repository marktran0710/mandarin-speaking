"""Unified KPI gate for the character/phone/tone experimental pipeline.

The gate is deliberately data-first.  It never turns a missing metric into a
pass, and it keeps ``T5`` (neutral) separate from ``Unknown``.  A report with
missing support is ``NEEDS_DATA``; a measured regression is ``BLOCKED``.  Only
an explicitly teacher-validated, fully passing report may be promoted beyond
``OWNER_PILOT_READY``.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TONES = ("T1", "T2", "T3", "T4", "T5")
_MISSING = object()


@dataclass(frozen=True)
class KpiThresholds:
    min_speaker_count: int = 40
    min_tone_support: int = 50
    min_phone_gold_count: int = 300
    min_audio_reviewed_count: int = 300
    min_audio_unusable_count: int = 100
    character_alignment_success: float = 0.95
    human_usable_boundaries: float = 0.90
    phone_boundary_within_30ms: float = 0.80
    phone_f1: float = 0.80
    tone_accuracy: float = 0.80
    tone_macro_f1: float = 0.80
    per_tone_f1: float = 0.80
    detection_coverage: float = 0.80
    max_unknown_rate: float = 0.20
    correct_balanced_accuracy: float = 0.80
    correct_sensitivity: float = 0.80
    correct_specificity: float = 0.80
    audio_qc_auc: float = 0.80
    audio_qc_retention: float = 0.80
    audio_qc_unusable_recall: float = 0.80
    high_confidence_precision: float = 0.92
    calibration_ece: float = 0.10
    speaker_balanced_accuracy: float = 0.70
    # T5 is intentionally deferred for the current pilot.  It remains a
    # first-class label in manifests and is never folded into Unknown.
    require_t5: bool = False


KPIThresholds = KpiThresholds


@dataclass(frozen=True)
class KpiCheck:
    name: str
    passed: bool
    actual: float | None
    operator: str
    threshold: float
    required: bool = True
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KpiGateResult:
    checks: tuple[KpiCheck, ...]
    status: str
    release_status: str
    missing_metrics: tuple[str, ...]
    failed_metrics: tuple[str, ...]
    deferred_metrics: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "release_status": self.release_status,
            "passed": self.passed,
            "missing_metrics": list(self.missing_metrics),
            "failed_metrics": list(self.failed_metrics),
            "deferred_metrics": list(self.deferred_metrics),
            "checks": [check.as_dict() for check in self.checks],
        }


def _nested(report: Mapping[str, Any], *path: str) -> Any:
    current: Any = report
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _first(report: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _nested(report, *path)
        if value is not _MISSING:
            return value
    return _MISSING


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _check(name: str, value: Any, operator: str, threshold: float, *, detail: str = "") -> KpiCheck:
    actual = _number(value)
    if actual is None:
        return KpiCheck(name, False, None, operator, threshold, True, detail or "required metric is missing")
    passed = actual >= threshold if operator == ">=" else actual <= threshold
    return KpiCheck(name, passed, actual, operator, threshold, True, detail)


def _presence_check(name: str, value: Any, *, detail: str) -> KpiCheck:
    present = isinstance(value, str) and bool(value.strip()) or isinstance(value, bool) and value
    return KpiCheck(name, bool(present), 1.0 if present else None, "=", 1.0, True, detail if present else f"{detail} is missing")


def _support(report: Mapping[str, Any], tone: str) -> Any:
    support = _first(report, ("tone_support",), ("tone_detection", "support"), ("by_tone",))
    if isinstance(support, Mapping):
        item = support.get(tone, support.get(tone.removeprefix("T"), support.get(int(tone.removeprefix("T")))))
        if isinstance(item, Mapping):
            return item.get("support", item.get("count", _MISSING))
        return item
    by_tone = _first(report, ("tone_detection", "per_tone"), ("by_expected_tone",))
    if isinstance(by_tone, Mapping):
        item = by_tone.get(tone, by_tone.get(tone.removeprefix("T")))
        if isinstance(item, Mapping):
            return item.get("support", item.get("count", _MISSING))
    return _MISSING


def _per_tone_metric(report: Mapping[str, Any], tone: str, metric: str) -> Any:
    for path in (("tone_detection", "per_tone"), ("by_tone",), ("by_expected_tone",)):
        values = _nested(report, *path)
        if isinstance(values, Mapping):
            item = values.get(tone, values.get(tone.removeprefix("T"), values.get(int(tone.removeprefix("T")))))
            if isinstance(item, Mapping) and metric in item:
                return item[metric]
            if _number(item) is not None:
                return item
    return _MISSING


def _speaker_min_balanced_accuracy(report: Mapping[str, Any]) -> Any:
    direct = _first(report, ("speaker_robustness", "min_balanced_accuracy"), ("speaker_min_balanced_accuracy",))
    if direct is not _MISSING:
        return direct
    rows = _first(report, ("speaker_robustness", "per_speaker"), ("per_speaker",))
    if isinstance(rows, Mapping):
        values = [item.get("balanced_accuracy") for item in rows.values() if isinstance(item, Mapping)]
    elif isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        values = [item.get("balanced_accuracy") for item in rows if isinstance(item, Mapping)]
    else:
        values = []
    numeric = [_number(value) for value in values]
    numeric = [value for value in numeric if value is not None]
    return min(numeric) if numeric else _MISSING


def _phone_group_min_f1(report: Mapping[str, Any]) -> Any:
    groups = _first(report, ("phone_recognition", "per_phone"), ("phone_recognition", "by_phone"), ("phone_per_group",))
    if not isinstance(groups, Mapping) or not groups:
        return _MISSING
    values = []
    for item in groups.values():
        if isinstance(item, Mapping):
            value = _number(item.get("f1"))
        else:
            value = _number(item)
        if value is not None:
            values.append(value)
    return min(values) if values else _MISSING


def evaluate_kpi_gate(report: Mapping[str, Any], thresholds: KpiThresholds | None = None) -> KpiGateResult:
    if not isinstance(report, Mapping):
        raise TypeError("KPI report must be a JSON object")
    limits = thresholds or KpiThresholds()
    checks: list[KpiCheck] = [
        _presence_check("model_version", _first(report, ("provenance", "model_version"), ("model_version",)), detail="frozen model provenance"),
        _presence_check("schema_version", _first(report, ("provenance", "schema_version"), ("schema_version",)), detail="frozen schema provenance"),
        _presence_check("sealed_test_set", _first(report, ("test_set", "sealed"), ("sealed_test_set",)), detail="sealed test set marker"),
        _check("speaker_count", _first(report, ("dataset", "speaker_count"), ("speaker_count",)), ">=", limits.min_speaker_count),
        _check("character_alignment_success", _first(report, ("character_alignment", "success"), ("character_alignment_success",)), ">=", limits.character_alignment_success),
        _check("human_usable_boundaries", _first(report, ("character_alignment", "human_usable_boundaries"), ("human_usable_boundaries",)), ">=", limits.human_usable_boundaries),
        _check("phone_boundary_within_30ms", _first(report, ("phone_alignment", "within_30ms"), ("phone_boundary_within_30ms",)), ">=", limits.phone_boundary_within_30ms),
        _check("phone_gold_count", _first(report, ("phone_alignment", "gold_count"), ("phone_gold_count",)), ">=", limits.min_phone_gold_count),
        _check("phone_f1", _first(report, ("phone_recognition", "f1"), ("phone_f1",)), ">=", limits.phone_f1),
        _check("phone_group_min_f1", _phone_group_min_f1(report), ">=", limits.phone_f1),
        _check("tone_accuracy", _first(report, ("tone_detection", "accuracy"), ("tone_accuracy",)), ">=", limits.tone_accuracy),
        _check("tone_macro_f1", _first(report, ("tone_detection", "macro_f1"), ("tone_macro_f1",)), ">=", limits.tone_macro_f1),
        _check("detection_coverage", _first(report, ("detection", "coverage"), ("detection_coverage",)), ">=", limits.detection_coverage),
        _check("unknown_rate", _first(report, ("detection", "unknown_rate"), ("unknown_rate",)), "<=", limits.max_unknown_rate),
        _check("correct_balanced_accuracy", _first(report, ("correct_incorrect", "balanced_accuracy"), ("correct_balanced_accuracy",)), ">=", limits.correct_balanced_accuracy),
        _check("correct_sensitivity", _first(report, ("correct_incorrect", "sensitivity"), ("correct_sensitivity",)), ">=", limits.correct_sensitivity),
        _check("correct_specificity", _first(report, ("correct_incorrect", "specificity"), ("correct_specificity",)), ">=", limits.correct_specificity),
        _check("audio_qc_auc", _first(report, ("audio_qc", "auc"), ("audio_qc_auc",)), ">=", limits.audio_qc_auc),
        _check("audio_qc_retention", _first(report, ("audio_qc", "usable_retention"), ("audio_qc_retention",)), ">=", limits.audio_qc_retention),
        _check("audio_qc_unusable_recall", _first(report, ("audio_qc", "unusable_recall"), ("audio_qc_unusable_recall",)), ">=", limits.audio_qc_unusable_recall),
        _check("audio_qc_reviewed_count", _first(report, ("audio_qc", "reviewed_count"), ("audio_qc_reviewed_count",)), ">=", limits.min_audio_reviewed_count),
        _check("audio_qc_unusable_count", _first(report, ("audio_qc", "unusable_count"), ("audio_qc_unusable_count",)), ">=", limits.min_audio_unusable_count),
        _check("high_confidence_precision", _first(report, ("high_confidence_pass", "precision"), ("high_confidence_precision",)), ">=", limits.high_confidence_precision),
        _check("calibration_ece", _first(report, ("calibration", "ece"), ("calibration_ece",)), "<=", limits.calibration_ece),
        _check("speaker_min_balanced_accuracy", _speaker_min_balanced_accuracy(report), ">=", limits.speaker_balanced_accuracy),
    ]
    deferred: list[str] = []
    tones_to_gate = TONES if limits.require_t5 else TONES[:-1]
    if not limits.require_t5:
        deferred.extend([f"t5_{metric}" for metric in ("precision", "recall", "f1", "test_support")])
    for tone in tones_to_gate:
        for metric in ("precision", "recall", "f1"):
            checks.append(_check(f"{tone.lower()}_{metric}", _per_tone_metric(report, tone, metric), ">=", limits.per_tone_f1))
        support = _support(report, tone)
        support_number = _number(support)
        checks.append(KpiCheck(f"{tone.lower()}_test_support", support_number is not None and support_number >= limits.min_tone_support, support_number, ">=", limits.min_tone_support, True, "T5 requires learner test support" if tone == "T5" else ""))

    speaker_overlap = _first(report, ("split", "speaker_overlap"), ("speaker_overlap",))
    checks.append(_check("speaker_leakage", 0 if speaker_overlap == 0 else speaker_overlap, "<=", 0, detail="speaker-disjoint split required"))
    missing = tuple(check.name for check in checks if check.actual is None)
    failed = tuple(check.name for check in checks if check.actual is not None and not check.passed)
    if missing:
        status = "NEEDS_DATA"
    elif failed:
        status = "FAIL"
    else:
        status = "PASS"
    teacher_validated = bool(_first(report, ("teacher_validation", "validated"), ("teacher_validated",)) is True)
    if status == "PASS":
        release_status = "TEACHER_VALIDATED" if teacher_validated else "OWNER_PILOT_READY"
    elif status == "FAIL":
        release_status = "BLOCKED"
    else:
        release_status = "EXPERIMENTAL"
    return KpiGateResult(tuple(checks), status, release_status, missing, failed, tuple(deferred))


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _binary_metrics(rows: Sequence[Mapping[str, Any]], expected_key: str, predicted_key: str) -> dict[str, float] | None:
    pairs = [(bool(row[expected_key]), bool(row[predicted_key])) for row in rows if expected_key in row and predicted_key in row]
    if not pairs:
        return None
    tp = sum(expected and predicted for expected, predicted in pairs)
    tn = sum(not expected and not predicted for expected, predicted in pairs)
    fp = sum(not expected and predicted for expected, predicted in pairs)
    fn = sum(expected and not predicted for expected, predicted in pairs)
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {"balanced_accuracy": (sensitivity + specificity) / 2, "sensitivity": sensitivity, "specificity": specificity}


def build_kpi_report(rows: Sequence[Mapping[str, Any]], provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a gate-ready summary from per-character/per-phone benchmark rows.

    Rows may contain richer model-specific fields; the canonical fields are
    ``expected_tone``, ``detected_tone``, ``speaker_id``, alignment metrics,
    phone labels/boundary errors, and optional QC/correctness labels.
    """
    rows = [row for row in rows if isinstance(row, Mapping)]
    tone_rows = [row for row in rows if str(row.get("expected_tone", "")) in TONES]
    known_rows = [row for row in tone_rows if str(row.get("detected_tone", "Unknown")) in TONES]
    per_tone: dict[str, dict[str, Any]] = {}
    for tone in TONES:
        subset = [row for row in tone_rows if str(row.get("expected_tone")) == tone]
        tp = sum(str(row.get("detected_tone")) == tone for row in subset)
        fp = sum(str(row.get("detected_tone")) == tone for row in tone_rows if str(row.get("detected_tone")) == tone and str(row.get("expected_tone")) != tone)
        fn = len(subset) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_tone[tone] = {"support": len(subset), "precision": precision, "recall": recall, "f1": _f1(precision, recall)}
    alignment_values = [_number(row.get("alignment_success")) for row in rows if "alignment_success" in row]
    usable_values = [_number(row.get("human_usable_boundary")) for row in rows if "human_usable_boundary" in row]
    boundary_values = [abs(float(row["phone_boundary_error_ms"])) <= 30 for row in rows if _number(row.get("phone_boundary_error_ms")) is not None]
    phone_pairs = [row for row in rows if "phone_expected" in row and "phone_detected" in row]
    phone_correct = sum(row["phone_expected"] == row["phone_detected"] for row in phone_pairs)
    phone_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in phone_pairs:
        phone_groups[str(row.get("phone_expected"))].append(row)
    per_phone: dict[str, dict[str, float]] = {}
    for phone, group in phone_groups.items():
        tp = sum(row["phone_expected"] == row["phone_detected"] for row in group)
        per_phone[phone] = {"f1": tp / len(group) if group else 0.0}
    correct_metrics = _binary_metrics(rows, "correct_expected", "correct_predicted") or _binary_metrics(rows, "expected_correct", "predicted_correct")
    qc_metrics = _binary_metrics(rows, "audio_qc_expected_usable", "audio_qc_predicted_usable")
    confidences = [(float(row["confidence"]), bool(row.get("confidence_correct", row.get("correct", False)))) for row in rows if _number(row.get("confidence")) is not None]
    ece = sum(abs(confidence - float(correct)) for confidence, correct in confidences) / len(confidences) if confidences else None
    speaker_values: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("speaker_id") is not None:
            speaker_values[str(row["speaker_id"])].append(row)
    speaker_scores = []
    for speaker_rows in speaker_values.values():
        metrics = _binary_metrics(speaker_rows, "correct_expected", "correct_predicted") or _binary_metrics(speaker_rows, "expected_correct", "predicted_correct")
        if metrics:
            speaker_scores.append(metrics["balanced_accuracy"])
    report: dict[str, Any] = {
        "provenance": dict(provenance or {}),
        "dataset": {"speaker_count": len(speaker_values), "row_count": len(rows)},
        "character_alignment": {
            "success": sum(value for value in alignment_values if value is not None) / len(alignment_values) if alignment_values else None,
            "human_usable_boundaries": sum(value for value in usable_values if value is not None) / len(usable_values) if usable_values else None,
        },
        "phone_alignment": {"within_30ms": sum(boundary_values) / len(boundary_values) if boundary_values else None, "gold_count": len(boundary_values)},
        "phone_recognition": {"f1": phone_correct / len(phone_pairs) if phone_pairs else None, "per_phone": per_phone},
        "tone_detection": {"accuracy": sum(str(row.get("expected_tone")) == str(row.get("detected_tone")) for row in tone_rows) / len(tone_rows) if tone_rows else None, "macro_f1": sum(item["f1"] for item in per_tone.values()) / len(per_tone) if per_tone else None, "per_tone": per_tone},
        "detection": {"coverage": len(known_rows) / len(tone_rows) if tone_rows else None, "unknown_rate": 1 - len(known_rows) / len(tone_rows) if tone_rows else None},
        "correct_incorrect": correct_metrics or {},
        "audio_qc": {"reviewed_count": len([row for row in rows if "audio_qc_expected_usable" in row]), "unusable_count": len([row for row in rows if row.get("audio_qc_expected_usable") is False]), **(qc_metrics or {})},
        "high_confidence_pass": {"precision": sum(bool(row.get("confidence_correct")) for row in rows if row.get("high_confidence_pass")) / sum(bool(row.get("high_confidence_pass")) for row in rows) if any(row.get("high_confidence_pass") for row in rows) else None},
        "calibration": {"ece": ece},
        "speaker_robustness": {"min_balanced_accuracy": min(speaker_scores) if speaker_scores else None},
        "split": {"speaker_overlap": (provenance or {}).get("speaker_overlap")},
    }
    return report


def confusion_matrix(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    matrix = {tone: {predicted: 0 for predicted in (*TONES, "Unknown")} for tone in (*TONES, "Unknown")}
    for row in rows:
        expected = str(row.get("expected_tone", "Unknown"))
        detected = str(row.get("detected_tone", "Unknown"))
        expected = expected if expected in TONES else "Unknown"
        detected = detected if detected in TONES else "Unknown"
        matrix.setdefault(expected, {predicted: 0 for predicted in (*TONES, "Unknown")})
        matrix[expected][detected] += 1
    return matrix


def write_kpi_artifacts(report: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], output_dir: str | Path) -> dict[str, str]:
    """Write the unified JSON/CSV/confusion/phone/Markdown artifact bundle."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    result = evaluate_kpi_gate(report)
    enriched = dict(report)
    enriched["release_gate"] = result.as_dict()
    paths = {
        "json": destination / "kpi_report.json",
        "csv": destination / "kpi_rows.csv",
        "confusion": destination / "tone_confusion_matrix.json",
        "phone": destination / "phone_boundary_report.json",
        "markdown": destination / "kpi_dashboard.md",
    }
    paths["json"].write_text(json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["confusion"].write_text(json.dumps(confusion_matrix(rows), indent=2), encoding="utf-8")
    phone_rows = [dict(row) for row in rows if any(key in row for key in ("phone_boundary_error_ms", "phone_boundary_within_30ms", "phone_expected", "phone_detected"))]
    paths["phone"].write_text(json.dumps(phone_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    fieldnames = sorted({key for row in rows for key in row})
    with paths["csv"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["row"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    failed = ", ".join(result.failed_metrics) or "none"
    missing = ", ".join(result.missing_metrics) or "none"
    lines = [
        "# Unified KPI dashboard",
        "",
        f"- Status: **{result.status}**",
        f"- Release status: **{result.release_status}**",
        f"- Failed metrics: {failed}",
        f"- Missing data: {missing}",
        "",
        "| Metric | Actual | Threshold | Result |",
        "|---|---:|---:|---|",
    ]
    lines.extend(f"| {check.name} | {check.actual if check.actual is not None else 'missing'} | {check.operator} {check.threshold} | {'PASS' if check.passed else 'FAIL'} |" for check in result.checks)
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}
