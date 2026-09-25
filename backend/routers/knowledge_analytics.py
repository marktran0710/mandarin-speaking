"""Admin-only PFA/BKT pilot analytics for vocabulary quiz responses."""

from __future__ import annotations

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

import security.auth as auth
import services.knowledge_analytics_service as knowledge_analytics_service
from analytics.ttl_cache import TTLCache


router = APIRouter(
    prefix="/api/admin/analytics",
    tags=["admin-analytics"],
    dependencies=[Depends(auth.require_admin)],
)

# These endpoints are admin-only, read-only, and deterministic for a given
# database state, but each recomputes PFA/BKT models (the audit scans every
# quiz attempt). Memoise the result for a short window so a dashboard refresh
# or several concurrent views don't repeat the work. Staleness is bounded by
# the TTL; set ANALYTICS_CACHE_TTL_SECONDS=0 to disable for real-time debugging.
_ANALYTICS_CACHE_TTL = float(os.getenv("ANALYTICS_CACHE_TTL_SECONDS", "60"))
_analytics_cache = TTLCache(_ANALYTICS_CACHE_TTL)


@router.get("/knowledge-state")
async def get_knowledge_state(
    model: Literal["pfa", "bkt", "compare"] = Query(default="compare"),
    student_id: Optional[str] = Query(default=None),
    story_id: Optional[str] = Query(default=None),
    # Filters on vocab_quiz_responses.quiz_level — the three-round vocabulary
    # diagnostic (know_it/say_it/use_it). Migration 0033 unified this with
    # quiz_mode's tier1/tier2/tier3 labels (it used to be easy/medium/hard,
    # a separate axis from the removed story-text tiers — see that
    # migration's docstring for the full history).
    level: Optional[Literal["tier1", "tier2", "tier3"]] = Query(default=None),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    return await run_in_threadpool(
        _analytics_cache.get_or_compute,
        ("knowledge-state", model, student_id, story_id, level),
        lambda: knowledge_analytics_service.compute_knowledge_state(model, student_id, story_id, level),
    )


@router.get("/bkt-question-audit")
async def get_bkt_question_audit(
    all_tiers: bool = Query(default=False),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    return await run_in_threadpool(
        _analytics_cache.get_or_compute,
        ("bkt-question-audit", all_tiers),
        lambda: knowledge_analytics_service.compute_bkt_question_audit(all_tiers),
    )
