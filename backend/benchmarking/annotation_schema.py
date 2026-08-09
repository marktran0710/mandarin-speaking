"""Canonical annotation manifest schema for the experimental benchmark.

The corpus importer intentionally creates *unlabelled* rows.  A teacher or
reviewer can fill this schema without changing the source audio.  Rows are
allowed to be audio, character, or phone granularity; the ``parent_id`` field
links character/phone rows back to the recording.

The schema mirrors the keys consumed by :mod:`kpi_release_gate` and keeps T5
(neutral) distinct from ``Unknown``.  It is deliberately conservative: missing
gold labels are reported as validation errors instead of being inferred.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

TONES = ("T1", "T2", "T3", "T4", "T5")
DETECTED_TONES = TONES + ("Unknown",)
ROW_TYPES = ("audio", "character", "phone")
SPLITS = ("train", "dev", "sealed_test", "unassigned")
CORRECTNESS = ("correct", "incorrect", "ambiguous", "unusable")
QC_STATUSES = ("usable", "unusable", "needs_review")

# Keep this order stable: it is used for CSV exports and spreadsheet review.
ANNOTATION_COLUMNS = (
    # Identity and corpus provenance.
    "annotation_id", "parent_id", "row_type", "corpus", "source_url",
    "audio_path", "speaker_id", "session_id", "recording_id", "learner_l1",
    "consent_note",
    "level", "dataset_split", "is_sealed_test", "transcript", "expected_pinyin",
    "character_index", "character", "pinyin", "expected_tone",
    # Gold character labels and timing (milliseconds).
    "char_start_ms", "char_end_ms", "alignment_success", "human_usable_boundary",
    "char_alignment_status", "tone_label_status", "produced_tone", "correct_incorrect",
    "teacher_consensus", "teacher_agreement", "tone_confidence",
    # Gold phone labels and timing.
    "phone_index", "phone", "phone_expected", "phone_start_ms", "phone_end_ms",
    "phone_boundary_error_ms", "phone_boundary_status", "phone_gold_source",
    "phone_confidence",
    # Audio quality review.
    "audio_duration_ms", "sample_rate_hz", "device", "audio_qc_status",
    "audio_qc_expected_usable", "audio_qc_reasons", "audio_qc_annotator_id",
    "audio_qc_reviewed_at", "audio_qc_notes",
    # Frozen system outputs used by the KPI gate.
    "detected_tone", "tone_probability_t1", "tone_probability_t2",
    "tone_probability_t3", "tone_probability_t4", "tone_probability_t5",
    "confidence", "high_confidence_pass", "confidence_correct",
    "correct_expected", "correct_predicted", "audio_qc_predicted_usable",
    "phone_detected", "model_version", "schema_version",
    # Audit trail.
    "annotator_id", "annotation_version", "reviewed_at", "review_status", "notes",
)


def blank_annotation_row(base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a complete, review-ready row with safe empty defaults."""

    row: dict[str, Any] = {column: "" for column in ANNOTATION_COLUMNS}
    row.update({
        "row_type": "audio",
        "dataset_split": "unassigned",
        "is_sealed_test": False,
        "char_alignment_status": "needs_annotation",
        "tone_label_status": "needs_annotation",
        "phone_boundary_status": "needs_annotation",
        "audio_qc_status": "needs_review",
        "review_status": "needs_annotation",
    })
    if base:
        row.update({key: value for key, value in base.items() if key in row})
    return row


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "1", "yes", "y"}:
            return True
        if value in {"false", "0", "no", "n", ""}:
            return False
    return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def validate_annotation_row(row: Mapping[str, Any], *, require_gold: bool = False) -> list[str]:
    """Return human-readable validation errors for one annotation row.

    ``require_gold=False`` is suitable for an importer manifest.  Set it to
    ``True`` before including rows in a sealed KPI run.
    """

    errors: list[str] = []
    row_type = str(row.get("row_type", "audio") or "audio")
    if row_type not in ROW_TYPES:
        errors.append(f"row_type must be one of {ROW_TYPES}")
    split = str(row.get("dataset_split", "unassigned") or "unassigned")
    if split not in SPLITS:
        errors.append(f"dataset_split must be one of {SPLITS}")
    sealed = _as_bool(row.get("is_sealed_test"))
    if sealed is None and row.get("is_sealed_test") not in (None, ""):
        errors.append("is_sealed_test must be boolean")
    elif sealed and split != "sealed_test":
        errors.append("is_sealed_test=true requires dataset_split=sealed_test")
    elif split == "sealed_test" and sealed is False:
        errors.append("dataset_split=sealed_test requires is_sealed_test=true")

    expected = str(row.get("expected_tone", "") or "")
    detected = str(row.get("detected_tone", "") or "")
    if expected and expected not in TONES:
        errors.append("expected_tone must be T1..T5 (never Unknown)")
    if detected and detected not in DETECTED_TONES:
        errors.append("detected_tone must be T1..T5 or Unknown")
    if expected == "Unknown" or (expected == "T5" and detected == "Unknown"):
        errors.append("T5 and Unknown are separate states; do not substitute Unknown for T5")

    start = _as_float(row.get("char_start_ms"))
    end = _as_float(row.get("char_end_ms"))
    if start is not None and start < 0:
        errors.append("char_start_ms must be >= 0")
    if end is not None and end < 0:
        errors.append("char_end_ms must be >= 0")
    if start is not None and end is not None and end < start:
        errors.append("char_end_ms must be >= char_start_ms")

    phone_start = _as_float(row.get("phone_start_ms"))
    phone_end = _as_float(row.get("phone_end_ms"))
    if phone_start is not None and phone_start < 0:
        errors.append("phone_start_ms must be >= 0")
    if phone_end is not None and phone_end < 0:
        errors.append("phone_end_ms must be >= 0")
    if phone_start is not None and phone_end is not None and phone_end < phone_start:
        errors.append("phone_end_ms must be >= phone_start_ms")

    correctness = str(row.get("correct_incorrect", "") or "")
    if correctness and correctness not in CORRECTNESS:
        errors.append(f"correct_incorrect must be one of {CORRECTNESS}")
    qc = str(row.get("audio_qc_status", "") or "")
    if qc and qc not in QC_STATUSES:
        errors.append(f"audio_qc_status must be one of {QC_STATUSES}")
    qc_expected = _as_bool(row.get("audio_qc_expected_usable"))
    if qc_expected is None and row.get("audio_qc_expected_usable") not in (None, ""):
        errors.append("audio_qc_expected_usable must be boolean")
    if qc == "usable" and qc_expected is False:
        errors.append("audio_qc_status=usable conflicts with audio_qc_expected_usable=false")
    if qc == "unusable" and qc_expected is True:
        errors.append("audio_qc_status=unusable conflicts with audio_qc_expected_usable=true")

    if require_gold:
        required = {
            "speaker_id": "speaker_id",
            "expected_tone": "expected_tone",
            "produced_tone": "produced_tone",
            "correct_incorrect": "correct_incorrect",
            "dataset_split": "dataset_split",
        }
        for field, label in required.items():
            if not str(row.get(field, "") or "").strip():
                errors.append(f"{label} is required for gold benchmark rows")
        if row_type == "phone":
            for field in ("phone_expected", "phone_start_ms", "phone_end_ms"):
                if not str(row.get(field, "") or "").strip():
                    errors.append(f"{field} is required for gold phone rows")
        if qc == "needs_review" or qc_expected is None:
            errors.append("audio QC label is required for gold benchmark rows")
    return errors


def write_template(path: Path) -> None:
    """Write an empty CSV template with the canonical column order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=list(ANNOTATION_COLUMNS)).writeheader()


__all__ = [
    "ANNOTATION_COLUMNS", "DETECTED_TONES", "TONES", "blank_annotation_row",
    "validate_annotation_row", "write_template",
]
