from fastapi import APIRouter, Depends

import security.auth as auth
from application.vocabulary_research import get_research_context
from db import connect_db

router = APIRouter()


@router.get("/api/research/vocabulary/context")
def get_vocabulary_research_context(identity: auth.Identity = Depends(auth.require_student)):
    """Student-safe research context. Never expose which experimental
    condition(s) the student is assigned to, their study_id, policy/
    assignment version, or practice budget - those would let a student (or
    anyone reading the network tab) infer or reason about their own
    treatment, which is exactly what the research design must prevent.

    practiceAvailable/reviewAvailable/probeAvailable are hardcoded false for
    every student right now - those features don't exist yet (Epics 4, 5,
    7). This endpoint exists so the frontend has one stable place to ask
    "is anything different for me right now", starting from an honest
    "no" for everyone.
    """
    with connect_db() as db:
        context = get_research_context(db, identity.id)
    return {
        "active": context.active,
        "coreCompletionPolicy": context.progression_policy.value,
        "practiceAvailable": False,
        "reviewAvailable": False,
        "probeAvailable": False,
    }
