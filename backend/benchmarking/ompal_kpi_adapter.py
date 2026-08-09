"""Adapt the frozen OMPAL manifest into a gold-only unified KPI report.

OMPAL contains learner labels for T1--T4 and a frozen speaker-disjoint split,
but it does not contain neutral-tone (T5) examples or predictions from the
current V2 system.  This adapter therefore emits a *partial* report: measured
dataset/alignment facts are included, while prediction-dependent metrics are
left absent/``None``.  Leaving them missing is intentional and keeps the
release gate fail-closed rather than turning gold labels into fake predictions.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from benchmarking.kpi_release_gate import evaluate_kpi_gate, write_kpi_artifacts


TONES = ("T1", "T2", "T3", "T4", "T5")
DEFAULT_MANIFEST = Path(
    "backend/pronunciation/wav2vec_tone/data/ompal_full_tone_benchmark_manifest_split.csv"
)


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _bool(value: str | None) -> bool | None:
    if value in ("1", "true", "True", "yes"):
        return True
    if value in ("0", "false", "False", "no"):
        return False
    return None


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> list[dict[str, str]]:
    """Load learner rows from the frozen split manifest.

    Native reference rows are intentionally excluded from the primary learner
    benchmark; they remain available in the source manifest for separate
    reference analyses.
    """

    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    learner_rows = [row for row in rows if row.get("split") in {"train", "dev", "test"}]
    if not learner_rows:
        raise ValueError(f"no train/dev/test learner rows found in {manifest_path}")
    return learner_rows


def build_gold_rows(manifest_rows: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    """Produce canonical rows without inventing ``detected_tone`` values."""

    output: list[dict[str, Any]] = []
    for row in manifest_rows:
        expected = str(row.get("expected_tone") or "").strip()
        if expected not in {"1", "2", "3", "4"}:
            continue
        item: dict[str, Any] = {
            "dataset": "OMPAL",
            "sample_id": row.get("token_id"),
            "utterance_id": row.get("utterance_id"),
            "speaker_id": row.get("speaker_id"),
            "split": row.get("split"),
            "expected_tone": f"T{expected}",
            "tone_correctness": _bool(row.get("tone_correctness")),
            "alignment_success": _bool(row.get("alignment_success")),
            "alignment_status": row.get("alignment_status_detail") or None,
            "human_usable_boundary": None,
            "start_seconds": _number(row.get("start_seconds")),
            "end_seconds": _number(row.get("end_seconds")),
        }
        # Deliberately do not add detected_tone, confidence, phone labels, QC
        # decisions, or correctness predictions: OMPAL has no V2 predictions.
        output.append(item)
    return output


def build_partial_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    """Build a release-gate-compatible, explicitly incomplete OMPAL report."""

    learner_rows = list(rows)
    speakers = sorted({str(row["speaker_id"]) for row in learner_rows if row.get("speaker_id")})
    split_counts = Counter(str(row.get("split")) for row in learner_rows)
    split_speakers = {
        split: sorted({str(row["speaker_id"]) for row in learner_rows if row.get("split") == split})
        for split in ("train", "dev", "test")
    }
    tone_support = Counter(str(row.get("expected_tone")) for row in learner_rows)
    alignment_rows = [row for row in learner_rows if isinstance(row.get("alignment_success"), bool)]
    alignment_success = (
        sum(bool(row["alignment_success"]) for row in alignment_rows) / len(alignment_rows)
        if alignment_rows
        else None
    )

    per_tone: dict[str, dict[str, Any]] = {}
    for tone in TONES:
        per_tone[tone] = {
            "support": tone_support.get(tone, 0),
            # Prediction metrics are intentionally absent until V2 rows exist.
            "precision": None,
            "recall": None,
            "f1": None,
        }

    report: dict[str, Any] = {
        "benchmark": "OMPAL gold-only partial T1-T4 benchmark",
        "status_note": (
            "Gold labels and alignment metadata only. No system predictions were "
            "present, so prediction-dependent KPI values remain missing."
        ),
        "provenance": {
            "dataset": "OMPAL",
            "dataset_version": "ompal-tone-benchmark-1.0",
            "manifest_path": str(Path(manifest_path)),
            "pipeline_version": "align-mmsfa-star-0ms-1.0",
            "aligner": "torchaudio MMS_FA CTC forced alignment (with_star=True)",
            "boundary_policy": "original_0ms",
            "target_pronunciation_source": "moe_dict (moedict.tw), Taiwan Mandarin",
            "gold_only": True,
        },
        "dataset": {
            "speaker_count": len(speakers),
            "learner_speaker_count": len(speakers),
            "row_count": len(learner_rows),
            "split_counts": dict(split_counts),
            "tone_support": dict(tone_support),
        },
        "test_set": {
            "name": "ompal_speaker_split_v1",
            "sealed": False,
            "speaker_count": len(split_speakers["test"]),
            "row_count": split_counts.get("test", 0),
            "note": "Frozen speaker-disjoint audit exists; release sealing/model provenance are not asserted here.",
        },
        "character_alignment": {
            "success": alignment_success,
            "human_usable_boundaries": 0.81,
            "human_review_count": 100,
            "human_review_note": "Independent blinded review of original boundaries; not a per-row label.",
        },
        "phone_alignment": {
            "within_30ms": None,
            "gold_count": 0,
            "note": "No phone-level gold boundaries in OMPAL manifest.",
        },
        "phone_recognition": {
            "f1": None,
            "per_phone": {},
            "note": "No system phone predictions in this artifact.",
        },
        "tone_detection": {
            "accuracy": None,
            "macro_f1": None,
            "per_tone": per_tone,
            "note": "Expected T1-T4 labels only; detected tones intentionally omitted.",
        },
        "detection": {"coverage": None, "unknown_rate": None},
        "correct_incorrect": {},
        "audio_qc": {
            "auc": None,
            "usable_retention": None,
            "unusable_recall": None,
            "reviewed_count": 0,
            "unusable_count": 0,
        },
        "high_confidence_pass": {"precision": None},
        "calibration": {"ece": None},
        "speaker_robustness": {"min_balanced_accuracy": None},
        "split": {
            "speaker_overlap": 0,
            "protocol": "ompal_speaker_split_v1",
            "speaker_counts": {name: len(ids) for name, ids in split_speakers.items()},
            "note": "Train/dev/test speaker sets are disjoint per frozen split audit.",
        },
        "deferred_requirements": [
            "T5 learner labels and sealed-test support",
            "V2 detected-tone predictions and probabilities",
            "phone gold boundaries and predictions",
            "audio-QC reviewed labels and predictions",
        ],
    }
    report["release_gate"] = evaluate_kpi_gate(report).as_dict()
    return report


def write_partial_artifacts(
    manifest_path: str | Path = DEFAULT_MANIFEST,
    output_dir: str | Path = "backend/reports/kpi_gate_ompal_partial_v2",
) -> dict[str, str]:
    rows = build_gold_rows(load_manifest(manifest_path))
    report = build_partial_report(rows, manifest_path=manifest_path)
    return write_kpi_artifacts(report, rows, output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default="backend/reports/kpi_gate_ompal_partial_v2")
    args = parser.parse_args()
    artifacts = write_partial_artifacts(args.manifest, args.output_dir)
    report = json.loads(Path(artifacts["json"]).read_text(encoding="utf-8"))
    gate = report["release_gate"]
    print(f"OMPAL rows: {report['dataset']['row_count']}")
    print(f"OMPAL learner speakers: {report['dataset']['speaker_count']}")
    print(f"KPI STATUS: {gate['status']}")
    print(f"RELEASE STATUS: {gate['release_status']}")
    print(f"JSON ARTIFACT: {artifacts['json']}")
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
