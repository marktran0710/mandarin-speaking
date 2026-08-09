"""Audit T3 recognition errors without touching the sealed OMPAL Test set.

This is a diagnostic over already-produced Train/Dev predictions.  It never
fits, tunes, or changes a classifier.  In particular, it distinguishes the
lexical T3 label from a *possible* T3+T3 surface-T2 realization without
rewriting gold labels.  Half-third and other surface-label claims require an
explicit annotation column; acoustic metadata alone is reported as
``needs_data`` rather than interpreted as gold.

The default split cache is deliberately the Train/Dev-only feature cache.  A
cache or input row containing ``test`` / ``sealed_test`` is rejected before a
report is produced.

Run from ``backend``::

    python -m pronunciation.wav2vec_tone.audit_t3_sandhi
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np


DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
DEFAULT_METADATA = DATA_DIR / "ompal_tone_benchmark_metadata.csv"
DEFAULT_PREDICTIONS = DATA_DIR / "ompal_produced_tone_train_oof.csv"
DEFAULT_SPLIT_CACHE = DATA_DIR / "dev_features_train_dev.npz"
DEFAULT_OUTPUT = REPORTS_DIR / "ompal_t3_sandhi_audit"

ALLOWED_SPLITS = frozenset({"train", "dev"})
SEALED_SPLITS = frozenset({"test", "sealed_test"})
TONES = frozenset({"T1", "T2", "T3", "T4"})
SURFACE_LABEL_COLUMNS = (
    "surface_tone",
    "surface_label",
    "produced_surface_tone",
    "tone_label_type",
    "label_type",
    "sandhi_applied",
)


class SealedTestViolation(ValueError):
    """Raised when an audit input attempts to include a sealed Test row."""


def _token_id(row: dict[str, str]) -> str:
    supplied = str(row.get("token_id", "")).strip()
    if supplied:
        return supplied
    utterance = str(row.get("utterance_id", "")).strip()
    raw_index = str(row.get("token_index", "")).strip()
    if not utterance or not raw_index:
        raise ValueError("metadata needs token_id or utterance_id + token_index")
    try:
        return f"{utterance}_{int(raw_index):02d}"
    except ValueError as exc:
        raise ValueError(f"invalid token_index {raw_index!r} for {utterance!r}") from exc


def _tone(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    if raw in {"1", "2", "3", "4"}:
        raw = f"T{raw}"
    return raw if raw in TONES else None


def _truthy(value: Any) -> bool | None:
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return None


def load_train_dev_split_map(path: str | Path) -> dict[str, str]:
    """Load a Train/Dev-only token map and reject any sealed membership."""
    cache_path = Path(path)
    if "test" in cache_path.name.lower() or "seal" in cache_path.name.lower():
        raise SealedTestViolation(f"refusing a Test/sealed split input: {cache_path}")
    cache = np.load(cache_path, allow_pickle=True)
    required = {"token_ids", "split"}
    missing = required - set(cache.files)
    if missing:
        raise ValueError(f"split cache missing {sorted(missing)}")
    token_ids = [str(value) for value in cache["token_ids"].tolist()]
    splits = [str(value).strip().lower() for value in cache["split"].tolist()]
    if len(token_ids) != len(splits):
        raise ValueError("split cache token_ids and split lengths differ")
    forbidden = sorted(set(splits) & SEALED_SPLITS)
    if forbidden:
        raise SealedTestViolation(f"TEST LOCK VIOLATION: split cache contains {forbidden}")
    unknown = sorted(set(splits) - ALLOWED_SPLITS)
    if unknown:
        raise ValueError(f"split cache contains non-Train/Dev values {unknown}")
    result = dict(zip(token_ids, splits))
    if len(result) != len(token_ids):
        raise ValueError("duplicate token_id in split cache")
    return result


def _read_csv(path: str | Path) -> tuple[list[dict[str, str]], set[str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        return list(reader), set(reader.fieldnames or [])


def load_metadata(path: str | Path, split_map: dict[str, str]) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Load only metadata whose IDs exist in the non-sealed Train/Dev map."""
    rows, columns = _read_csv(path)
    metadata: dict[str, dict[str, str]] = {}
    for row in rows:
        explicit_split = str(row.get("split", "")).strip().lower()
        if explicit_split in SEALED_SPLITS:
            raise SealedTestViolation("TEST LOCK VIOLATION: metadata contains a sealed split row")
        token_id = _token_id(row)
        split = explicit_split or split_map.get(token_id, "")
        if not split:
            # Metadata from outside the Train/Dev cache cannot be safely
            # assigned a split by guessing from speaker or utterance IDs.
            continue
        if split not in ALLOWED_SPLITS:
            raise ValueError(f"metadata {token_id} has invalid split {split!r}")
        if token_id in metadata:
            raise ValueError(f"duplicate metadata token_id {token_id!r}")
        metadata[token_id] = {**row, "token_id": token_id, "split": split}
    return metadata, columns


def load_predictions(path: str | Path, metadata: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows, _ = _read_csv(path)
    result: list[dict[str, str]] = []
    for row in rows:
        explicit_split = str(row.get("split", "")).strip().lower()
        if explicit_split in SEALED_SPLITS:
            raise SealedTestViolation("TEST LOCK VIOLATION: predictions contain a sealed split row")
        token_id = str(row.get("token_id", "")).strip()
        if not token_id:
            raise ValueError("prediction row has no token_id")
        meta = metadata.get(token_id)
        if meta is None:
            # Do not join unknown rows against the full benchmark manifest:
            # that could open the sealed Test partition.
            raise ValueError(f"prediction token {token_id!r} is absent from Train/Dev metadata")
        if explicit_split and explicit_split != meta["split"]:
            raise ValueError(f"prediction {token_id} split conflicts with Train/Dev metadata")
        result.append({**row, "split": meta["split"]})
    return result


def _context_index(metadata: Iterable[dict[str, str]]) -> dict[tuple[str, str, str], dict[int, dict[str, str]]]:
    grouped: dict[tuple[str, str, str], dict[int, dict[str, str]]] = defaultdict(dict)
    for row in metadata:
        utterance = str(row.get("utterance_id", "")).strip()
        index = str(row.get("token_index", "")).strip()
        if not utterance or not index:
            continue
        try:
            grouped[(str(row["split"]), str(row.get("speaker_id", "")), utterance)][int(index)] = row
        except ValueError:
            continue
    return grouped


def _surface_status(row: dict[str, str], surface_columns: list[str]) -> tuple[str, str]:
    if not surface_columns:
        return "needs_data_no_surface_label", ""
    evidence = "; ".join(f"{column}={row[column]}" for column in surface_columns if str(row.get(column, "")).strip())
    return ("explicit_surface_annotation_present", evidence) if evidence else ("needs_data_empty_surface_label", "")


def _boundary_status(row: dict[str, str], metadata_columns: set[str]) -> tuple[str, str]:
    required = {"alignment_success", "alignment_status_detail"}
    if not required <= metadata_columns:
        return "needs_data_no_boundary_fields", ""
    successful = _truthy(row.get("alignment_success"))
    detail = str(row.get("alignment_status_detail", "")).strip()
    if successful is False:
        return "alignment_flagged", detail
    if detail and detail.lower() not in {"ok", "success", "aligned"}:
        return "alignment_detail_flagged", detail
    return "alignment_available_no_flag", detail


def _pitch_status(row: dict[str, str], metadata_columns: set[str]) -> tuple[str, str]:
    if "praat_flags" not in metadata_columns:
        return "needs_data_no_pitch_flags", ""
    flags = str(row.get("praat_flags", "")).strip()
    return ("pitch_flagged", flags) if flags else ("pitch_available_no_flag", "")


def audit_t3_sandhi(
    metadata: dict[str, dict[str, str]],
    predictions: Iterable[dict[str, str]],
    metadata_columns: set[str],
) -> dict[str, Any]:
    """Create a non-tuning T3 error report from Train/Dev rows only."""
    predictions = list(predictions)
    contexts = _context_index(metadata.values())
    surface_columns = [column for column in SURFACE_LABEL_COLUMNS if column in metadata_columns]
    detail_rows: list[dict[str, Any]] = []

    for prediction in predictions:
        token_id = prediction["token_id"]
        row = metadata[token_id]
        target = _tone(prediction.get("produced_tone_proxy")) or _tone(row.get("expected_tone"))
        if target != "T3":
            continue
        predicted = _tone(prediction.get("predicted_tone"))
        utterance = str(row.get("utterance_id", "")).strip()
        index_raw = str(row.get("token_index", "")).strip()
        key = (str(row["split"]), str(row.get("speaker_id", "")), utterance)
        previous = following = None
        context_status = "needs_data_missing_context"
        try:
            index = int(index_raw)
            context = contexts.get(key, {})
            previous = _tone(context.get(index - 1, {}).get("expected_tone"))
            following = _tone(context.get(index + 1, {}).get("expected_tone"))
            context_status = "available" if context else "needs_data_missing_context"
        except ValueError:
            pass

        if predicted in {"T1", "T2", "T4"}:
            error_group = f"T3_to_{predicted}"
        elif predicted == "T3":
            error_group = "T3_correct"
        else:
            error_group = "needs_data_missing_or_invalid_prediction"

        sandhi_context = "T3_plus_T3" if following == "T3" else "not_observed"
        sandhi_note = (
            "possible_surface_T2_not_gold_override"
            if sandhi_context == "T3_plus_T3" and predicted == "T2"
            else "not_applicable"
        )
        surface_status, surface_evidence = _surface_status(row, surface_columns)
        boundary_status, boundary_evidence = _boundary_status(row, metadata_columns)
        pitch_status, pitch_evidence = _pitch_status(row, metadata_columns)
        detail_rows.append({
            "token_id": token_id,
            "split": row["split"],
            "speaker_id": row.get("speaker_id", ""),
            "utterance_id": utterance,
            "token_index": index_raw,
            "lexical_target": "T3",
            "predicted_tone": predicted or "",
            "error_group": error_group,
            "previous_lexical_tone": previous or "",
            "following_lexical_tone": following or "",
            "context_status": context_status,
            "sandhi_context": sandhi_context,
            "sandhi_interpretation": sandhi_note,
            "surface_label_status": surface_status,
            "surface_label_evidence": surface_evidence,
            "boundary_flag_status": boundary_status,
            "boundary_flag_evidence": boundary_evidence,
            "pitch_flag_status": pitch_status,
            "pitch_flag_evidence": pitch_evidence,
            "duration_seconds": row.get("duration_seconds", ""),
            "voiced_proportion": row.get("voiced_proportion", ""),
        })

    mapping = Counter(row["error_group"] for row in detail_rows)
    sandhi = Counter(row["sandhi_context"] for row in detail_rows)
    surface = Counter(row["surface_label_status"] for row in detail_rows)
    boundary = Counter(row["boundary_flag_status"] for row in detail_rows)
    pitch = Counter(row["pitch_flag_status"] for row in detail_rows)
    needs_data = sorted({
        row["context_status"] for row in detail_rows if row["context_status"].startswith("needs_data")
    } | {
        row["surface_label_status"] for row in detail_rows if row["surface_label_status"].startswith("needs_data")
    } | {
        row["boundary_flag_status"] for row in detail_rows if row["boundary_flag_status"].startswith("needs_data")
    } | {
        row["pitch_flag_status"] for row in detail_rows if row["pitch_flag_status"].startswith("needs_data")
    })
    return {
        "protocol": {
            "scope": "Train/Dev metadata and existing predictions only; no classifier fitting or threshold selection",
            "sealed_test_accessed": False,
            "gold_policy": "Lexical labels remain unchanged. T3+T3 is an audit flag, never a gold-label rewrite.",
            "half_third_policy": "Only explicit surface-label metadata may support a half-third/surface claim.",
        },
        "input_counts": {"metadata_train_dev": len(metadata), "predictions_train_dev": len(predictions)},
        "t3_summary": {
            "n_t3_predictions": len(detail_rows),
            "mapping": dict(sorted(mapping.items())),
            "sandhi_context": dict(sorted(sandhi.items())),
            "surface_label_status": dict(sorted(surface.items())),
            "boundary_flags": dict(sorted(boundary.items())),
            "pitch_flags": dict(sorted(pitch.items())),
            "needs_data": needs_data,
        },
        "rows": detail_rows,
    }


def write_artifacts(report: dict[str, Any], output_base: str | Path) -> tuple[Path, Path, Path]:
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    markdown_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = report["rows"]
    fields = list(rows[0]) if rows else ["token_id", "split", "lexical_target", "predicted_tone", "error_group"]
    with csv_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = report["t3_summary"]
    markdown_path.write_text(
        "# OMPAL T3 sandhi audit\n\n"
        "Scope: Train/Dev metadata and existing predictions only. The sealed Test set was not opened.\n\n"
        f"- T3 predictions audited: {summary['n_t3_predictions']}\n"
        f"- T3 mappings: `{json.dumps(summary['mapping'], ensure_ascii=False, sort_keys=True)}`\n"
        f"- T3+T3 context: `{json.dumps(summary['sandhi_context'], ensure_ascii=False, sort_keys=True)}`\n"
        f"- Needs data: `{', '.join(summary['needs_data']) or 'none'}`\n\n"
        "A T3→T2 row in T3+T3 context is a possible surface-sandhi observation only; it does not alter gold labels or metrics.\n",
        encoding="utf-8",
    )
    return json_path, csv_path, markdown_path


def run(
    metadata_path: str | Path = DEFAULT_METADATA,
    predictions_path: str | Path = DEFAULT_PREDICTIONS,
    split_cache_path: str | Path = DEFAULT_SPLIT_CACHE,
) -> dict[str, Any]:
    split_map = load_train_dev_split_map(split_cache_path)
    metadata, metadata_columns = load_metadata(metadata_path, split_map)
    predictions = load_predictions(predictions_path, metadata)
    return audit_t3_sandhi(metadata, predictions, metadata_columns)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--split-cache", type=Path, default=DEFAULT_SPLIT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.metadata, args.predictions, args.split_cache)
    artifacts = write_artifacts(report, args.output)
    print(f"T3 audit: {report['t3_summary']['n_t3_predictions']} Train/Dev rows")
    print(f"needs_data: {', '.join(report['t3_summary']['needs_data']) or 'none'}")
    print("artifacts: " + ", ".join(str(path) for path in artifacts))


if __name__ == "__main__":
    main()
