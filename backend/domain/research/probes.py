"""Pure probe-scheduling rules for the Epic 7 independent outcome bank.

No database, no I/O. Two responsibilities: partition a section's assigned
words into disjoint probe pools per learner (Task 7.7 - a word is never
both a 7-day AND a 21-day probe for the same student), and compute when
each pool becomes due (Task 7.3). ``final_retention`` has no fixed offset
in the plan (it is released once the study reaches its posttest phase, an
operational/admin decision covered by a later Epic) - its due date is left
unset here and is populated administratively, not by enrollment timing.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional

PROBE_TYPES = ("probe_7d", "probe_21d", "final_retention")

_PROBE_7D_OFFSET_DAYS = 7
_PROBE_21D_OFFSET_DAYS = 21


def partition_probe_pool(student_id: str, word_ids: list[str]) -> dict[str, str]:
    """word_id -> probe_type, disjoint per student (Task 7.7).

    Deterministic (same student+word always lands in the same pool, so
    re-running enrollment for an already-enrolled section is a no-op rather
    than reshuffling), but not sequential - a hash of (student_id, word_id)
    decides the bucket, not word order, so pool membership can't be
    inferred from a word's position within its section.
    """
    partition: dict[str, str] = {}
    for word_id in word_ids:
        digest = hashlib.sha256(f"{student_id}:{word_id}".encode("utf-8")).digest()
        partition[word_id] = PROBE_TYPES[digest[0] % len(PROBE_TYPES)]
    return partition


def due_at_for_probe_type(probe_type: str, enrolled_at: datetime) -> Optional[datetime]:
    """When a just-enrolled word's probe becomes due. None for
    final_retention - see module docstring."""
    if probe_type == "probe_7d":
        return enrolled_at + timedelta(days=_PROBE_7D_OFFSET_DAYS)
    if probe_type == "probe_21d":
        return enrolled_at + timedelta(days=_PROBE_21D_OFFSET_DAYS)
    if probe_type == "final_retention":
        return None
    raise ValueError(f"Unknown probe_type: {probe_type!r}")


def is_probe_due(due_at: Optional[datetime], now: datetime) -> bool:
    """A probe with no due_at yet (final_retention pending admin release)
    is never due on its own."""
    return due_at is not None and due_at <= now
