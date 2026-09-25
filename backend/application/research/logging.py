"""Epic 8, Task 8.1: the append-only research policy-event log.

Every research orchestration module (core completion, practice, retention,
probes) writes here at the moment it makes a protocol-relevant decision, so
a researcher can later reconstruct what happened to one student - or the
whole study - without re-deriving it from side effects on other tables.
This module is a thin, validating wrapper around repositories/
vocabulary_research.py's insert; the actual call sites live in each
feature's own application module (research_practice_session.py,
research_retention.py, research_probes.py, vocabulary_research.py) since
each already has the condition/word/study context this needs in hand.

`policy_violation` is a supported event_type in the schema and this
module's POLICY_EVENT_TYPES, with no automatic detector wired up yet - the
plan does not specify what should trigger one, and this Epic's design
already makes most violations structurally impossible (Epic 4's blind
selection literally never fetches the data it would need to leak, Epic 6's
routing table is exhaustive). Real violation detection belongs to Epic
10's audit_research_readiness.py, which can call record_policy_event with
this type once it defines a concrete check.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from domain.research.assignment import BktPolicy, RetentionPolicy, condition_for_policies
from repositories import research as repo

POLICY_EVENT_TYPES = (
    "assignment_loaded",
    "core_completed",
    "practice_session_created",
    "practice_item_selected",
    "retention_enrolled",
    "review_scheduled",
    "review_yoked",
    "review_completed",
    "probe_assigned",
    "probe_completed",
    "policy_violation",
)


def condition_label(bkt_policy: str, retention_policy: str) -> str:
    """The C/B/S/BS letter for a (bkt_policy, retention_policy) pair, for
    stamping into a word-scoped event's payload at write time (Task 8.2's
    fidelity queries read it back rather than re-joining assignments)."""
    return condition_for_policies(BktPolicy(bkt_policy), RetentionPolicy(retention_policy)).value


def record_policy_event(
    db,
    *,
    study_id: Optional[str],
    student_id: str,
    event_type: str,
    word_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
) -> None:
    """A no-op when study_id is None. Every call site already guards on an
    active research participant before reaching here, but a policy event
    with no study to attribute it to is meaningless, not an error worth
    raising and potentially breaking the production path that called it."""
    if not study_id:
        return
    if event_type not in POLICY_EVENT_TYPES:
        raise ValueError(f"Unknown policy event_type: {event_type!r}")
    now = occurred_at or datetime.now(timezone.utc)
    repo.insert_policy_event(
        db, study_id=study_id, student_id=student_id, event_type=event_type,
        word_id=word_id, payload=payload, occurred_at=now, created_at=now.isoformat(),
    )
