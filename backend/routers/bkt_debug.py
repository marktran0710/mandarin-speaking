"""Admin-only tool to inject a batch of correct/incorrect answers for one
student+word, through the real response ledger, and watch how BKT mastery
would have evolved step by step.

Exists so an admin can debug/tune the BKT pipeline without needing a real
student to click through an actual quiz for every scenario they want to try.
Injected rows are tagged evidence_origin='synthetic' (never counted as real
calibration evidence) for the same reason scripts/seed_test_accounts.py tags
its rows that way.
"""

from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import auth
from analytics.bkt import BKT_CONFIG
from analytics.bkt_assessment_resolver import _published_assessment
from analytics.bkt_mastery import (
    mastery_trace_for_word,
    response_rows_for_attempt,
    upsert_raw_responses,
)
from database import connect_db

router = APIRouter(dependencies=[Depends(auth.require_admin)])

_PATTERN_RE = re.compile(r"^[01]{1,50}$")


class BktDebugInjectRequest(BaseModel):
    studentId: str
    storyId: str
    wordId: str
    pattern: str = Field(..., description="e.g. '1011010' - 1 = correct, 0 = incorrect, in order")


def _find_easy_item(story_id: str, word_id: str) -> tuple[str, dict[str, Any]]:
    with connect_db() as db:
        published = _published_assessment(db, story_id)
    if published is None:
        raise HTTPException(status_code=404, detail="Story not found or not published.")
    canonical_id, assessment = published
    for item in assessment:
        if item.get("wordId") == word_id and str(item.get("level") or "").casefold() == "easy":
            return canonical_id, item
    raise HTTPException(status_code=404, detail="No tier1 (easy) assessment item for this word in this story.")


def _fake_result(item: dict[str, Any], word_id: str, correct: bool, exposure: int) -> dict[str, Any]:
    return {
        "word": item.get("targetWord") or word_id,
        "conceptId": word_id,
        "correct": correct,
        "level": "tier1",
        "mode": "tier1",
        "itemId": f"bkt-debug-{word_id}-{exposure}",
        "questionKind": "basic_meaning_mcq",
        "roundType": "know_it",
        "knowledgeDimension": "meaning",
        "activityType": "diagnostic",
        "isBktEligible": True,
        "authoritativeResolved": True,
        "resolverVersion": "admin-bkt-debug-v1",
        "bktValidationStatus": "APPROVED",
        "diagnosticExposureId": f"bkt-debug-{word_id}-{exposure}-{int(time.time() * 1000)}",
        "answeredAt": None,
        "questionIndex": exposure,
    }


@router.post("/api/admin/bkt-debug/inject")
async def inject_bkt_debug_responses(request: BktDebugInjectRequest) -> dict[str, Any]:
    if not _PATTERN_RE.match(request.pattern):
        raise HTTPException(status_code=400, detail="Pattern must be 1-50 characters of 0/1 only.")

    canonical_story_id, item = _find_easy_item(request.storyId, request.wordId)
    completed_at = "2026-01-01T00:00:00Z"
    results = [
        _fake_result(item, request.wordId, char == "1", exposure)
        for exposure, char in enumerate(request.pattern, start=1)
    ]
    attempt = {
        "id": f"bkt-debug-{request.studentId}-{int(time.time() * 1000)}",
        "storyId": canonical_story_id,
        "baseStoryId": canonical_story_id,
        "level": "tier1",
        "mode": "tier1",
        "completedAt": completed_at,
    }
    rows = response_rows_for_attempt(attempt, request.studentId, results)
    if not rows:
        raise HTTPException(status_code=422, detail="These responses were not accepted as BKT-eligible evidence.")
    for row in rows:
        row["evidence_origin"] = "synthetic"

    with connect_db() as db:
        upsert_raw_responses(db, rows)
        steps = mastery_trace_for_word(db, request.studentId, request.wordId)

    return {
        "wordId": request.wordId,
        "targetWord": item.get("targetWord") or request.wordId,
        "steps": steps,
        "finalMastery": steps[-1]["pLearned"] if steps else BKT_CONFIG.initial_mastery,
        "correctCount": sum(1 for step in steps if step["correct"]),
        "totalCount": len(steps),
        "injectedCount": len(rows),
    }
