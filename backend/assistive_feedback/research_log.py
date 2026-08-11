"""STEP 6: the per-attempt research log documented in
`system_validation_logging_plan.md`, implemented.

Sink: an append-only JSONL file under `private-data/` (git-ignored, same
convention as every other research artifact in this project --
`private-data/wav2vec_embeddings_cache/`, etc.) rather than a live database
table. This is a deliberate, minimal choice for a first integration: it
needs no schema migration against the app's real Postgres database (a
higher-risk, harder-to-reverse change this task's "smallest possible
production changes" scope does not ask for), while still being fully
queryable by the aggregation functions below -- moving the sink to a real
table later is a drop-in change to `log_attempt`'s implementation only; the
schema and every metric function are unaffected either way.

Never logs anything students see. `read_records`/the metric functions are
for research/teacher tooling only -- see `assistive_feedback_design.md`'s
access-boundary note.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

LOG_PATH = Path(os.environ.get("ASSISTIVE_FEEDBACK_LOG_PATH", "private-data/assistive_feedback_research_log.jsonl"))

ProgressionOutcome = Literal[
    "continued_immediately", "continued_after_retry", "continued_after_cap", "abandoned",
]

#: STEP 4 of the pre-pilot plumbing task, verbatim.
AttemptType = Literal["WHOLE_SENTENCE_INITIAL", "FOCUSED_RETRY", "WHOLE_SENTENCE_FINAL"]


@dataclass(frozen=True)
class AttemptLogRecord:
    """One scored syllable attempt -- one record per retry too (linked via
    `retry_of_attempt_id`), matching `system_validation_logging_plan.md`
    STEP 6's schema, extended per the pre-pilot plumbing task's STEP 7 join
    key: `participant_id, session_id, item_id, attempt_id, attempt_number,
    attempt_type` together let a full participant -> item -> attempt 1 ->
    feedback -> retry -> attempt 2 -> progression sequence be reconstructed
    from explicit fields alone -- see `reconstruct_sequence`, which never
    reads `timestamp` to order anything."""

    attempt_id: str
    participant_id: str
    item_id: str
    syllable_index: int
    character: str
    policy_state: str  # ACCEPT / UNCERTAIN / NEEDS_PRACTICE -- internal names, for direct comparability with feedback_policy_protocol.json
    f1_risk_score: float | None
    e2_diagnostic_category: str
    e2_score: float | None
    expected_tone: int
    accepted_surface_tones: list[int]
    retry_chosen: bool = False
    retry_of_attempt_id: str | None = None
    #: The ORIGINAL attempt's `syllable_index` this record re-scores. A
    #: focused retry recording is its own short clip (its own
    #: `syllable_index` starts back at 0), so `retry_of_attempt_id` alone is
    #: not enough to link the right syllable within a multi-syllable
    #: original attempt -- both fields together are.
    retry_of_syllable_index: int | None = None
    second_attempt_policy_state: str | None = None
    progression_outcome: ProgressionOutcome = "continued_immediately"
    #: STEP 5/7: a pilot/study context field, distinct from participant
    #: identity -- see `src/utils/pilotSession.ts`. `""` in ordinary use.
    session_id: str = ""
    #: STEP 4: which of the (at most three) recordings in one item's
    #: attempt sequence this record is.
    attempt_number: int = 1
    attempt_type: AttemptType = "WHOLE_SENTENCE_INITIAL"
    #: STEP 5: "" (ordinary use) or "pilot" -- mirrors
    #: `pilotSession.resolvePilotContext`'s `studyPhase`, never an
    #: experimental/control group label (STEP 5 explicitly says not to
    #: encode that unless it already belongs in the study workflow, which
    #: it does not yet).
    study_phase: str = ""
    #: STEP 6: whether assistive feedback was actually active for this
    #: request (global flag, or the pilot override) -- lets research
    #: distinguish "no issue was ever computed" from "ACCEPT was computed".
    feedback_enabled: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def log_attempt(record: AttemptLogRecord, path: Path = LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def log_attempt_batch(records: Iterable[AttemptLogRecord], path: Path = LOG_PATH) -> int:
    n = 0
    for record in records:
        log_attempt(record, path)
        n += 1
    return n


def read_records(path: Path = LOG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# ---------------------------------------------------------------------------
# Retry reconciliation -- the append-only sink cannot go back and edit an
# attempt's own row once its retry happens in a LATER, separate request, so
# `retry_chosen`/`second_attempt_policy_state` must never be trusted as
# written by the ORIGINAL row alone. `join_retries` derives both from the
# one field a retry's own request naturally knows: `retry_of_attempt_id`
# (set by whichever record IS the retry, pointing back at what it retried).
# Every STEP 7 metric below reads the JOINED view, never the raw stored
# fields directly -- this is also why reconstruction never needs
# `timestamp`: `attempt_id` / `retry_of_attempt_id` / `attempt_number` carry
# the entire ordering and linkage.
# ---------------------------------------------------------------------------


def join_retries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keyed by `(retry_of_attempt_id, retry_of_syllable_index)` ->
    `(attempt_id, syllable_index)`, NOT by `attempt_id` alone: a focused
    retry's own recording re-indexes its syllable(s) from 0, and an
    original attempt can have several syllables, so attempt-id-only
    matching would incorrectly link a retry to every syllable in the
    attempt it retried rather than just the one it actually re-scores."""
    retry_of: dict[tuple[str, int], dict[str, Any]] = {}
    for r in records:
        if r.get("retry_of_attempt_id") is not None and r.get("retry_of_syllable_index") is not None:
            retry_of[(r["retry_of_attempt_id"], r["retry_of_syllable_index"])] = r

    joined = []
    for r in records:
        retry_record = retry_of.get((r["attempt_id"], r["syllable_index"]))
        row = dict(r)
        if retry_record is not None:
            row["retry_chosen"] = True
            row["second_attempt_policy_state"] = retry_record["policy_state"]
        joined.append(row)
    return joined


# ---------------------------------------------------------------------------
# STEP 7 metrics -- each one a pure aggregation over `join_retries(
# read_records())`, matching `system_validation_logging_plan.md`'s
# definitions exactly.
# ---------------------------------------------------------------------------


def retry_rate(records: list[dict[str, Any]]) -> float | None:
    records = join_retries(records)
    offered = [r for r in records if r["policy_state"] == "NEEDS_PRACTICE"]
    if not offered:
        return None
    return sum(1 for r in offered if r["retry_chosen"]) / len(offered)


def voluntary_retry_uptake(records: list[dict[str, Any]]) -> float | None:
    return retry_rate(records)  # same definition today -- see the plan doc's note


def attempt1_to_attempt2_transition_counts(records: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for r in join_retries(records):
        if r.get("retry_chosen") and r.get("second_attempt_policy_state"):
            key = (r["policy_state"], r["second_attempt_policy_state"])
            counts[key] = counts.get(key, 0) + 1
    return counts


def flagged_syllable_count(records: list[dict[str, Any]]) -> int:
    return sum(1 for r in records if r["policy_state"] == "NEEDS_PRACTICE")


def uncertain_case_count(records: list[dict[str, Any]]) -> int:
    return sum(1 for r in records if r["policy_state"] == "UNCERTAIN")


def completion_rate(records: list[dict[str, Any]]) -> float | None:
    if not records:
        return None
    return sum(1 for r in records if r["progression_outcome"] != "abandoned") / len(records)


def abandonment_rate_by_state(records: list[dict[str, Any]]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for state in ("ACCEPT", "UNCERTAIN", "NEEDS_PRACTICE"):
        subset = [r for r in records if r["policy_state"] == state]
        result[state] = (
            sum(1 for r in subset if r["progression_outcome"] == "abandoned") / len(subset)
            if subset else None
        )
    return result


# ---------------------------------------------------------------------------
# STEP 8: sequence reconstruction, using ONLY explicit join fields -- never
# `timestamp` for ordering or grouping (`attempt_number`/`syllable_index`
# are the ordering keys; `attempt_id`/`retry_of_attempt_id` are the linking
# keys).
# ---------------------------------------------------------------------------


def reconstruct_sequence(
    records: list[dict[str, Any]], participant_id: str, item_id: str, session_id: str | None = None,
) -> list[dict[str, Any]]:
    """One participant's full attempt sequence for one item, as a list of
    attempts (each with its syllable-level records), ordered by
    `attempt_number` then `syllable_index` -- explicit fields only."""
    matching = [
        r for r in join_retries(records)
        if r["participant_id"] == participant_id and r["item_id"] == item_id
        and (session_id is None or r["session_id"] == session_id)
    ]
    by_attempt: dict[str, list[dict[str, Any]]] = {}
    for row in matching:
        by_attempt.setdefault(row["attempt_id"], []).append(row)
    for rows in by_attempt.values():
        rows.sort(key=lambda r: r["syllable_index"])

    attempts = [
        {
            "attempt_id": attempt_id,
            "attempt_number": rows[0]["attempt_number"],
            "attempt_type": rows[0]["attempt_type"],
            "retry_of_attempt_id": rows[0]["retry_of_attempt_id"],
            "syllables": rows,
        }
        for attempt_id, rows in by_attempt.items()
    ]
    attempts.sort(key=lambda a: a["attempt_number"])
    return attempts
