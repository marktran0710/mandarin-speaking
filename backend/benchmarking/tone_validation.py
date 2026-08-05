"""Auditable evaluation utilities for Mandarin tone scoring.

The application score is only useful when it is compared with independent,
human-labelled recordings.  This module deliberately evaluates already-scored
recordings: it does not tune a model or choose a pass threshold.  Keeping the
external test set out of those decisions prevents test-set leakage.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from benchmarking.stats import binary_agreement, spearman


_TRUE_LABELS = {"1", "true", "pass", "passed", "correct", "yes"}
_FALSE_LABELS = {"0", "false", "fail", "failed", "incorrect", "no"}


@dataclass(frozen=True)
class ToneBenchmarkRow:
    """One human-labelled syllable or prompted-word attempt.

    ``human_label`` is the blinded human judgement of whether the expected
    tone was produced correctly.  ``system_score`` is the score returned by
    the app before any benchmark-specific calibration.
    """

    recording_id: str
    speaker_id: str
    expected_tone: int
    human_label: bool
    system_score: float
    detected_tone: int | None = None
    human_score: float | None = None


def _parse_bool(value: str, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_LABELS:
        return True
    if normalized in _FALSE_LABELS:
        return False
    raise ValueError(
        f"{field} must be one of {sorted(_TRUE_LABELS | _FALSE_LABELS)}, got {value!r}"
    )


def _optional_float(value: str | None, field: str) -> float | None:
    if value is None or not value.strip():
        return None
    result = float(value)
    if not 0.0 <= result <= 100.0:
        raise ValueError(f"{field} must be between 0 and 100, got {result}")
    return result


def _optional_tone(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    tone = int(value)
    if tone not in {1, 2, 3, 4}:
        raise ValueError(f"detected_tone must be 1, 2, 3, or 4, got {tone}")
    return tone


def load_benchmark_csv(path: str | Path) -> list[ToneBenchmarkRow]:
    """Load a scored benchmark CSV and validate its schema.

    Required columns are ``recording_id``, ``speaker_id``, ``expected_tone``,
    ``human_label``, and ``system_score``. Optional ``detected_tone`` permits
    a separate T1–T4 recognition report; optional ``human_score`` (0–100)
    enables score-correlation metrics.
    """

    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"recording_id", "speaker_id", "expected_tone", "human_label", "system_score"}
        columns = set(reader.fieldnames or [])
        missing = sorted(required - columns)
        if missing:
            raise ValueError(f"Missing required benchmark columns: {', '.join(missing)}")

        rows: list[ToneBenchmarkRow] = []
        seen_recordings: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            try:
                recording_id = (raw.get("recording_id") or "").strip()
                speaker_id = (raw.get("speaker_id") or "").strip()
                if not recording_id or not speaker_id:
                    raise ValueError("recording_id and speaker_id cannot be blank")
                if recording_id in seen_recordings:
                    raise ValueError(f"duplicate recording_id {recording_id!r}")

                expected_tone = int((raw.get("expected_tone") or "").strip())
                if expected_tone not in {1, 2, 3, 4}:
                    raise ValueError(f"expected_tone must be 1, 2, 3, or 4, got {expected_tone}")
                score = _optional_float(raw.get("system_score"), "system_score")
                if score is None:
                    raise ValueError("system_score cannot be blank")

                rows.append(
                    ToneBenchmarkRow(
                        recording_id=recording_id,
                        speaker_id=speaker_id,
                        expected_tone=expected_tone,
                        human_label=_parse_bool(raw.get("human_label") or "", "human_label"),
                        system_score=score,
                        detected_tone=_optional_tone(raw.get("detected_tone")),
                        human_score=_optional_float(raw.get("human_score"), "human_score"),
                    )
                )
                seen_recordings.add(recording_id)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid row {line_number}: {error}") from error

    if not rows:
        raise ValueError("Benchmark CSV has no recordings")
    return rows


def speaker_disjoint_split(
    rows: Iterable[ToneBenchmarkRow],
    *,
    train_ratio: float = 0.7,
    dev_ratio: float = 0.15,
    seed: int = 42,
) -> dict[str, list[ToneBenchmarkRow]]:
    """Split records by speaker, never by individual recording.

    Use this only for internal development data.  An external benchmark must
    remain untouched and be evaluated with :func:`build_evaluation_report`.
    """

    rows = list(rows)
    if not rows:
        raise ValueError("Cannot split an empty benchmark")
    if not 0 < train_ratio < 1 or not 0 <= dev_ratio < 1 or train_ratio + dev_ratio >= 1:
        raise ValueError("Ratios must satisfy 0 < train < 1, 0 <= dev < 1, and train + dev < 1")

    speakers = sorted({row.speaker_id for row in rows})
    if len(speakers) < 3:
        raise ValueError("At least three speakers are required for train/dev/test speaker splits")
    random.Random(seed).shuffle(speakers)

    train_end = max(1, round(len(speakers) * train_ratio))
    dev_end = max(train_end + 1, round(len(speakers) * (train_ratio + dev_ratio)))
    dev_end = min(dev_end, len(speakers) - 1)
    assignments = {
        speaker: "train" if index < train_end else "dev" if index < dev_end else "test"
        for index, speaker in enumerate(speakers)
    }
    result = {"train": [], "dev": [], "test": []}
    for row in rows:
        result[assignments[row.speaker_id]].append(row)
    return result


def _binary_metrics(rows: Iterable[ToneBenchmarkRow], threshold: float) -> dict[str, float | int | None]:
    rows = list(rows)
    return binary_agreement(
        [row.system_score >= threshold for row in rows],
        [row.human_label for row in rows],
    )


def _score_metrics(rows: Iterable[ToneBenchmarkRow]) -> dict[str, float | int | None]:
    paired = [(row.system_score, row.human_score) for row in rows if row.human_score is not None]
    if not paired:
        return {"n": 0, "mean_absolute_error": None, "spearman_correlation": None}
    system_scores, human_scores = zip(*paired)
    return {
        "n": len(paired),
        "mean_absolute_error": sum(abs(system - human) for system, human in paired) / len(paired),
        "spearman_correlation": spearman(list(system_scores), list(human_scores)),
    }


def _detection_metrics(rows: Iterable[ToneBenchmarkRow]) -> dict[str, Any] | None:
    detected = [row for row in rows if row.detected_tone is not None]
    if not detected:
        return None
    matrix = {
        str(expected): {str(predicted): 0 for predicted in range(1, 5)}
        for expected in range(1, 5)
    }
    for row in detected:
        matrix[str(row.expected_tone)][str(row.detected_tone)] += 1
    correct = sum(matrix[str(tone)][str(tone)] for tone in range(1, 5))
    return {
        "n": len(detected),
        "accuracy": correct / len(detected),
        "confusion_matrix": matrix,
    }


def build_evaluation_report(
    rows: Iterable[ToneBenchmarkRow], *, threshold: float = 70.0, audit_limit: int = 50
) -> dict[str, Any]:
    """Return a JSON-serializable, human-auditable benchmark report."""

    rows = list(rows)
    if not rows:
        raise ValueError("Cannot evaluate an empty benchmark")
    if not 0 <= threshold <= 100:
        raise ValueError("threshold must be between 0 and 100")

    by_tone: dict[str, dict[str, float | int | None]] = {}
    for tone in range(1, 5):
        tone_rows = [row for row in rows if row.expected_tone == tone]
        by_tone[str(tone)] = _binary_metrics(tone_rows, threshold) if tone_rows else {"n": 0}

    disagreements = [
        {
            "recording_id": row.recording_id,
            "speaker_id": row.speaker_id,
            "expected_tone": row.expected_tone,
            "human_label": row.human_label,
            "system_score": row.system_score,
            "system_pass": row.system_score >= threshold,
            "detected_tone": row.detected_tone,
        }
        for row in rows
        if row.human_label != (row.system_score >= threshold)
    ]

    return {
        "benchmark_protocol": {
            "threshold": threshold,
            "speaker_count": len({row.speaker_id for row in rows}),
            "recording_count": len(rows),
            "rule": "A system pass is system_score >= threshold; human_label is the independent ground truth.",
            "warning": "Do not choose this threshold using the external final-test corpus.",
        },
        "pass_fail_agreement": _binary_metrics(rows, threshold),
        "by_expected_tone": by_tone,
        "score_agreement": _score_metrics(rows),
        "tone_detection": _detection_metrics(rows),
        "audit": {
            "disagreement_count": len(disagreements),
            "disagreements": disagreements[:audit_limit],
            "truncated": len(disagreements) > audit_limit,
        },
    }
