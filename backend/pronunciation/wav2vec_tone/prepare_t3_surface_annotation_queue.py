"""Prepare a human-review queue for ambiguous Train-only T3 fusion OOF rows.

The input is the nested speaker-disjoint *Train-only* fusion OOF artifact.
This module ranks existing predictions for annotation; it does not train,
calibrate, tune, or alter any model.  Dev and Test are rejected.  Every row is
an immutable preannotation suggestion: a reviewer must write a human label and
adjudication before any downstream benchmark may treat it as gold.

Metadata is deliberately optional.  A full benchmark manifest that contains
Dev/Test must not be supplied.  To add lexical context, boundary provenance,
or source-audio paths, first export a separate Train-only metadata CSV with an
explicit ``split=train`` column.

Run from ``backend``::

    python -m pronunciation.wav2vec_tone.prepare_t3_surface_annotation_queue
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
DEFAULT_PREDICTIONS = DATA_DIR / "ompal_produced_tone_fusion_nested_train_oof.csv"
DEFAULT_OUTPUT = REPORTS_DIR / "ompal_t3_surface_annotation_queue"
TOKEN_AUDIO_DIRECTORY = "benchmark_token_segments"
T3 = "T3"
TRAIN = "train"
FORBIDDEN_SPLITS = frozenset({"dev", "test", "sealed_test", "native_reference"})
DECISION_COLUMNS = tuple(f"decision_score_T{tone}" for tone in range(1, 5))


class SealedPartitionViolation(ValueError):
    """Raised before a non-Train row can enter the annotation queue."""


def _tone(value: Any) -> str | None:
    value = str(value or "").strip().upper()
    if value in {"1", "2", "3", "4"}:
        value = f"T{value}"
    return value if value in {"T1", "T2", "T3", "T4"} else None


def _token_id(row: dict[str, str]) -> str:
    token_id = str(row.get("token_id", "")).strip()
    if token_id:
        return token_id
    utterance = str(row.get("utterance_id", "")).strip()
    index = str(row.get("token_index", "")).strip()
    if not utterance or not index:
        raise ValueError("metadata needs token_id or utterance_id + token_index")
    return f"{utterance}_{int(index):02d}"


def _read_csv(path: str | Path) -> tuple[list[dict[str, str]], set[str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        return list(reader), set(reader.fieldnames or [])


def load_train_fusion_oof(path: str | Path) -> list[dict[str, str]]:
    """Load a fusion OOF file only if every row is demonstrably Train-only."""
    rows, columns = _read_csv(path)
    required = {"token_id", "produced_tone_proxy", "predicted_tone", *DECISION_COLUMNS}
    missing = required - columns
    if missing:
        raise ValueError(f"fusion OOF missing {sorted(missing)}")
    output: list[dict[str, str]] = []
    for row in rows:
        split = str(row.get("split", TRAIN)).strip().lower() or TRAIN
        if split in FORBIDDEN_SPLITS:
            raise SealedPartitionViolation(f"TRAIN-ONLY LOCK VIOLATION: fusion OOF contains {split}")
        if split != TRAIN:
            raise ValueError(f"fusion OOF split must be train, got {split!r}")
        if not str(row.get("token_id", "")).strip():
            raise ValueError("fusion OOF row has no token_id")
        output.append({**row, "split": TRAIN})
    return output


def load_explicit_train_metadata(path: str | Path | None) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Load an optional metadata export, rejecting any row outside Train."""
    if path is None:
        return {}, set()
    rows, columns = _read_csv(path)
    if "split" not in columns:
        raise ValueError("Train-only metadata must have an explicit split=train column")
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        split = str(row.get("split", "")).strip().lower()
        if split in FORBIDDEN_SPLITS:
            raise SealedPartitionViolation(f"TRAIN-ONLY LOCK VIOLATION: metadata contains {split}")
        if split != TRAIN:
            raise ValueError(f"metadata split must be train, got {split!r}")
        token_id = _token_id(row)
        if token_id in output:
            raise ValueError(f"duplicate metadata token_id {token_id!r}")
        output[token_id] = {**row, "token_id": token_id, "split": TRAIN}
    return output, columns


def _context_index(metadata: Iterable[dict[str, str]]) -> dict[tuple[str, str], dict[int, dict[str, str]]]:
    grouped: dict[tuple[str, str], dict[int, dict[str, str]]] = defaultdict(dict)
    for row in metadata:
        utterance = str(row.get("utterance_id", "")).strip()
        raw_index = str(row.get("token_index", "")).strip()
        if not utterance or not raw_index:
            continue
        try:
            grouped[(str(row.get("speaker_id", "")), utterance)][int(raw_index)] = row
        except ValueError:
            continue
    return grouped


def _decision_values(row: dict[str, str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for tone in range(1, 5):
        field = f"decision_score_T{tone}"
        try:
            value = float(row[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid {field} for {row.get('token_id')}") from exc
        if not math.isfinite(value):
            raise ValueError(f"non-finite {field} for {row.get('token_id')}")
        result[f"T{tone}"] = value
    return result


def _margin(values: dict[str, float]) -> tuple[float, str]:
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=True)
    return ordered[0][1] - ordered[1][1], ordered[1][0]


def _metadata_provenance(row: dict[str, str] | None, columns: set[str]) -> dict[str, str]:
    if row is None:
        return {
            "context_status": "needs_data_train_metadata_not_supplied",
            "boundary_provenance": "needs_data_train_metadata_not_supplied",
            "pitch_provenance": "needs_data_train_metadata_not_supplied",
            "source_audio_path": "",
            "source_audio_status": "needs_data_train_metadata_not_supplied",
            "previous_lexical_tone": "",
            "following_lexical_tone": "",
            "sandhi_context": "needs_data_train_metadata_not_supplied",
        }
    boundary_fields = {"alignment_success", "alignment_status_detail", "alignment_score"}
    pitch_fields = {"praat_flags", "voiced_proportion", "f0_range_hz"}
    return {
        "context_status": "available" if {"utterance_id", "token_index"} <= columns else "needs_data_context_fields_missing",
        "boundary_provenance": "; ".join(f"{field}={row.get(field, '')}" for field in sorted(boundary_fields & columns)) or "needs_data_boundary_fields_missing",
        "pitch_provenance": "; ".join(f"{field}={row.get(field, '')}" for field in sorted(pitch_fields & columns)) or "needs_data_pitch_fields_missing",
        "source_audio_path": str(row.get("source_utterance_path") or row.get("audio_path") or ""),
        "source_audio_status": "available" if (row.get("source_utterance_path") or row.get("audio_path")) else "needs_data_source_audio_path",
        "previous_lexical_tone": "",
        "following_lexical_tone": "",
        "sandhi_context": "not_observed",
    }


def prepare_queue(
    predictions: Iterable[dict[str, str]],
    metadata: dict[str, dict[str, str]] | None = None,
    metadata_columns: set[str] | None = None,
    *,
    low_margin_quantile: float = 0.20,
    limit: int | None = None,
) -> dict[str, Any]:
    """Rank T3 errors/context/low-margin rows without inventing human labels."""
    if not 0.0 < low_margin_quantile <= 1.0:
        raise ValueError("low_margin_quantile must be in (0, 1]")
    predictions = list(predictions)
    metadata = metadata or {}
    metadata_columns = metadata_columns or set()
    contexts = _context_index(metadata.values())
    candidates: list[dict[str, Any]] = []
    for prediction in predictions:
        target = _tone(prediction.get("produced_tone_proxy"))
        if target != T3:
            continue
        values = _decision_values(prediction)
        margin, runner_up = _margin(values)
        meta = metadata.get(prediction["token_id"])
        provenance = _metadata_provenance(meta, metadata_columns)
        if meta is not None and provenance["context_status"] == "available":
            try:
                index = int(str(meta["token_index"]))
                context = contexts.get((str(meta.get("speaker_id", "")), str(meta.get("utterance_id", ""))), {})
                previous = _tone(context.get(index - 1, {}).get("expected_tone"))
                following = _tone(context.get(index + 1, {}).get("expected_tone"))
                provenance["previous_lexical_tone"] = previous or ""
                provenance["following_lexical_tone"] = following or ""
                provenance["sandhi_context"] = "T3_plus_T3" if following == T3 else "not_observed"
            except (KeyError, TypeError, ValueError):
                provenance["context_status"] = "needs_data_invalid_context_fields"
        candidates.append({
            "token_id": prediction["token_id"],
            "split": TRAIN,
            "token_audio_path": f"{TOKEN_AUDIO_DIRECTORY}/{prediction['token_id']}.wav",
            "target_tone_proxy": T3,
            "target_tone_proxy_source": "human_correct_prompt_proxy",
            "predicted_tone": _tone(prediction.get("predicted_tone")) or "",
            "model_candidate": (
                prediction.get("nested_selected_candidate")
                or prediction.get("selected_candidate", "")
            ),
            "model_score_type": prediction.get("score_type", ""),
            **{field: prediction.get(field, "") for field in DECISION_COLUMNS},
            "top1_margin": round(margin, 8),
            "runner_up_tone": runner_up,
            **provenance,
            # Human fields must stay blank: this artifact is never a label source.
            "annotation_status": "preannotation_needs_human_review",
            "gold_status": "not_gold",
            "auto_promotion_prohibited": True,
            "human_perceived_tone": "",
            "human_correctness": "",
            "reviewer_id": "",
            "reviewed_at": "",
            "adjudicator_id": "",
            "adjudication_status": "not_reviewed",
            "review_notes": "",
        })
    if not candidates:
        raise ValueError("no T3 rows found in Train-only fusion OOF")
    margins = sorted(float(row["top1_margin"]) for row in candidates)
    cutoff_index = max(0, math.ceil(len(margins) * low_margin_quantile) - 1)
    low_margin_cutoff = margins[cutoff_index]
    queue: list[dict[str, Any]] = []
    for row in candidates:
        reasons: list[str] = []
        if row["predicted_tone"] != T3:
            reasons.append("T3_error")
        if row["sandhi_context"] == "T3_plus_T3":
            reasons.append("T3_plus_T3_context")
        if float(row["top1_margin"]) <= low_margin_cutoff:
            reasons.append("low_margin_ambiguous")
        if not reasons:
            continue
        row["queue_reasons"] = ";".join(reasons)
        row["priority_band"] = 1 if "T3_error" in reasons else (2 if "T3_plus_T3_context" in reasons else 3)
        queue.append(row)
    queue.sort(key=lambda row: (int(row["priority_band"]), float(row["top1_margin"]), row["token_id"]))
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        queue = queue[:limit]
    reasons = Counter(reason for row in queue for reason in row["queue_reasons"].split(";"))
    return {
        "protocol": {
            "partition": "OMPAL Train-only nested fusion OOF; Dev/Test are prohibited",
            "selection": "union of T3 errors, T3+T3 context when Train metadata supplies it, and lowest-margin quantile",
            "low_margin_quantile": low_margin_quantile,
            "margin_definition": "largest uncalibrated LinearSVC decision margin minus runner-up margin",
            "gold_policy": "Rows are preannotations only; human review and adjudication are required. Auto-promotion is prohibited.",
            "surface_policy": "T3+T3 is a review priority, not a surface-tone or correctness label.",
            "sealed_test_accessed": False,
        },
        "input_counts": {"train_fusion_oof": len(predictions), "t3_candidates": len(candidates)},
        "queue_summary": {
            "queued": len(queue),
            "reason_counts": dict(sorted(reasons.items())),
            "low_margin_cutoff": low_margin_cutoff,
            "metadata_available": bool(metadata),
            "needs_data_rows": sum(1 for row in queue if str(row["context_status"]).startswith("needs_data")),
        },
        "rows": queue,
    }


def write_artifacts(report: dict[str, Any], output_base: str | Path) -> tuple[Path, Path, Path]:
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    json_path, csv_path, markdown_path = base.with_suffix(".json"), base.with_suffix(".csv"), base.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = report["rows"]
    fields = list(rows[0]) if rows else ["token_id", "annotation_status", "gold_status"]
    with csv_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    markdown_path.write_text(
        "# T3 surface-tone annotation queue\n\n"
        "This is a **Train-only preannotation queue**, not a gold dataset. Dev and sealed Test are prohibited.\n\n"
        "## Reviewer procedure\n\n"
        "1. Open `token_audio_path`; use `source_audio_path` only when it is present.\n"
        "2. Listen without treating the model prediction or lexical prompt as the answer.\n"
        "3. Fill `human_perceived_tone` (T1–T4 or Unknown), `human_correctness`, `reviewer_id`, and `reviewed_at`.\n"
        "4. Flag uncertain boundary/pitch cases in `review_notes`; do not infer missing context.\n"
        "5. A second reviewer/adjudicator must set `adjudication_status`; only a separate gold-ingestion process may promote a reviewed row.\n\n"
        "`T3_plus_T3_context` is a prioritization signal only. It never rewrites a lexical T3 target to T2.\n\n"
        f"Queued rows: {report['queue_summary']['queued']}\n"
        f"Reasons: `{json.dumps(report['queue_summary']['reason_counts'], ensure_ascii=False, sort_keys=True)}`\n",
        encoding="utf-8",
    )
    return json_path, csv_path, markdown_path


def run(
    predictions_path: str | Path = DEFAULT_PREDICTIONS,
    metadata_path: str | Path | None = None,
    *,
    low_margin_quantile: float = 0.20,
    limit: int | None = None,
) -> dict[str, Any]:
    predictions = load_train_fusion_oof(predictions_path)
    metadata, metadata_columns = load_explicit_train_metadata(metadata_path)
    return prepare_queue(predictions, metadata, metadata_columns,
                         low_margin_quantile=low_margin_quantile, limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--metadata", type=Path, help="separate, explicit Train-only metadata export")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--low-margin-quantile", type=float, default=0.20)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    report = run(args.predictions, args.metadata, low_margin_quantile=args.low_margin_quantile, limit=args.limit)
    paths = write_artifacts(report, args.output)
    print(f"T3 annotation queue: {report['queue_summary']['queued']} rows")
    print(f"reasons: {report['queue_summary']['reason_counts']}")
    print("artifacts: " + ", ".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
