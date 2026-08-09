"""Fail-closed split and augmentation audits for speech benchmarks.

The most common way a small speech benchmark looks much better than it really
is is not an intentionally bad model: it is a recording, speaker, or augmented
copy appearing on both sides of a split.  This module keeps that failure mode
out of the release workflow.  It only inspects provenance fields; it does not
look at predictions or choose model settings.

Supported manifests may use either the compact OMPAL names (``token_id``,
``split``) or the annotation names (``annotation_id``, ``dataset_split``).
Optional provenance fields that make the audit stronger are:

``audio_sha256`` / ``content_sha256``
    Hash of the original audio bytes.  Equal hashes must never cross splits.
``source_sample_id`` / ``augmentation_of``
    Stable identifier of the unaugmented source.  All derivatives remain in
    its source split and augmentation is allowed only in training.
``augmentation_id`` / ``augmentation_recipe``
    Explicit declaration that a row is derived/augmented.

The guard is intentionally conservative.  A missing optional hash is reported
as a warning, while evidence of leakage is an error.  This lets legacy OMPAL
manifests be audited without pretending that they contain content hashes.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_SPLIT_ALIASES = {"test": "sealed_test", "sealed_test": "sealed_test"}
_NON_EVALUATION_SPLITS = {"native_reference", "unassigned", ""}
_VALID_SPLITS = {"train", "dev", "sealed_test", "native_reference", "unassigned", ""}


def _text(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def canonical_split(row: Mapping[str, Any]) -> str:
    """Return a common name for legacy and annotation-manifest splits."""

    raw = _text(row, "dataset_split", "split").lower()
    return _SPLIT_ALIASES.get(raw, raw)


def sample_id(row: Mapping[str, Any], index: int) -> str:
    """Return the row identity, with a deterministic fallback for diagnostics."""

    return _text(row, "sample_id", "token_id", "annotation_id", "recording_id") or f"row:{index}"


def source_group(row: Mapping[str, Any], index: int) -> str:
    """Return the indivisible provenance group that must stay in one split.

    ``parent_id`` is deliberately not used: annotation manifests use it for
    audio -> character -> phone hierarchy, where grouping by recording is more
    useful and does not confuse annotation hierarchy with augmentation.
    """

    value = _text(
        row,
        "source_sample_id",
        "augmentation_of",
        "source_utterance_id",
        "utterance_id",
        "source_utterance_path",
        "audio_sha256",
        "content_sha256",
        "sha256",
        "audio_path",
    )
    return value or sample_id(row, index)


def is_augmentation(row: Mapping[str, Any]) -> bool:
    """Whether a row declares a derived/augmented version of source audio."""

    return bool(_text(row, "augmentation_id", "augmentation_recipe", "augmentation_of"))


@dataclass(frozen=True)
class LeakageAudit:
    """Serializable result of an immutable benchmark provenance check."""

    row_count: int
    manifest_sha256: str
    split_counts: dict[str, int]
    speaker_counts: dict[str, int]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "row_count": self.row_count,
            "manifest_sha256": self.manifest_sha256,
            "split_counts": self.split_counts,
            "speaker_counts": self.speaker_counts,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "policy": {
                "speaker_disjoint": True,
                "source_group_disjoint": True,
                "content_hash_disjoint_when_available": True,
                "augmentation_train_only": True,
                "sealed_test_never_tuned": True,
            },
        }


def _fingerprint(rows: list[Mapping[str, Any]]) -> str:
    """Hash only immutable provenance fields, never labels or predictions."""

    canonical = []
    for index, row in enumerate(rows):
        canonical.append({
            "sample_id": sample_id(row, index),
            "speaker_id": _text(row, "speaker_id"),
            "split": canonical_split(row),
            "source_group": source_group(row, index),
            "audio_hash": _text(row, "audio_sha256", "content_sha256", "sha256"),
            "augmentation": is_augmentation(row),
        })
    encoded = json.dumps(sorted(canonical, key=lambda item: item["sample_id"]),
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def audit_rows(rows: Iterable[Mapping[str, Any]], *, require_sealed_test: bool = False) -> LeakageAudit:
    """Audit leakage and return all failures instead of stopping at the first.

    A source/recording group can contain several character/phone rows; that is
    allowed as long as every row remains in a single split.  Repeated prompt
    text across *different speakers* is reported only as descriptive metadata,
    not leakage: prompt generalisation is a real deployment condition.
    """

    materialized = [dict(row) for row in rows]
    errors: list[str] = []
    warnings: list[str] = []
    if not materialized:
        errors.append("manifest has no rows")

    ids: dict[str, list[int]] = defaultdict(list)
    speaker_splits: dict[str, set[str]] = defaultdict(set)
    group_splits: dict[str, set[str]] = defaultdict(set)
    content_splits: dict[str, set[str]] = defaultdict(set)
    split_counts: Counter[str] = Counter()
    split_speakers: dict[str, set[str]] = defaultdict(set)
    hashed_rows = 0
    sealed_rows = 0

    for index, row in enumerate(materialized, start=1):
        split = canonical_split(row)
        identity = sample_id(row, index)
        speaker = _text(row, "speaker_id")
        group = source_group(row, index)
        content_hash = _text(row, "audio_sha256", "content_sha256", "sha256")
        ids[identity].append(index)

        if split not in _VALID_SPLITS:
            errors.append(f"row {index} ({identity}): unsupported split {split!r}")
        if split in _NON_EVALUATION_SPLITS:
            continue
        split_counts[split] += 1
        if split == "sealed_test":
            sealed_rows += 1
        if not speaker:
            errors.append(f"row {index} ({identity}): speaker_id is required for a benchmark split")
        else:
            speaker_splits[speaker].add(split)
            split_speakers[split].add(speaker)
        group_splits[group].add(split)
        if content_hash:
            hashed_rows += 1
            content_splits[content_hash].add(split)
        if is_augmentation(row) and split != "train":
            errors.append(
                f"row {index} ({identity}): augmentation is allowed only in train, not {split}"
            )

    for identity, indices in sorted(ids.items()):
        if len(indices) > 1:
            errors.append(f"duplicate sample id {identity!r} at rows {indices}")
    for speaker, splits in sorted(speaker_splits.items()):
        if len(splits) > 1:
            errors.append(f"speaker leakage for {speaker!r}: {sorted(splits)}")
    for group, splits in sorted(group_splits.items()):
        if len(splits) > 1:
            errors.append(f"source-group leakage for {group!r}: {sorted(splits)}")
    for digest, splits in sorted(content_splits.items()):
        if len(splits) > 1:
            errors.append(f"audio-content leakage for sha256 {digest[:16]}: {sorted(splits)}")

    if require_sealed_test and sealed_rows == 0:
        errors.append("a release benchmark requires at least one sealed_test row")
    if not hashed_rows and materialized:
        warnings.append(
            "no audio_sha256/content_sha256 values present; byte-identical files cannot be checked"
        )
    if split_counts.get("train", 0) == 0:
        warnings.append("no train rows declared; this may be an evaluation-only manifest")
    if not split_counts.get("sealed_test", 0):
        warnings.append("no sealed_test rows declared; this manifest cannot be a final release benchmark")

    return LeakageAudit(
        row_count=len(materialized),
        manifest_sha256=_fingerprint(materialized),
        split_counts=dict(sorted(split_counts.items())),
        speaker_counts={name: len(ids) for name, ids in sorted(split_speakers.items())},
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


__all__ = ["LeakageAudit", "audit_rows", "canonical_split", "is_augmentation", "sample_id", "source_group"]
