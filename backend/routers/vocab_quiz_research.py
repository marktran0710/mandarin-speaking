from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
from application.research_practice_session import ResearchPracticeUnavailableError, build_practice_session
from application.research_retention import ResearchReviewUnavailableError, build_review_session
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

    practiceAvailable/reviewAvailable now follow the student's active
    research state (Epics 4/5 shipped their endpoints below). probeAvailable
    stays hardcoded false - that feature doesn't exist yet (Epic 7).
    """
    with connect_db() as db:
        context = get_research_context(db, identity.id)
    return {
        "active": context.active,
        "coreCompletionPolicy": context.progression_policy.value,
        "practiceAvailable": context.active,
        "reviewAvailable": context.active,
        "probeAvailable": False,
    }


@router.post("/api/research/vocabulary/practice-session")
def create_research_practice_session(identity: auth.Identity = Depends(auth.require_student)):
    """Server-owned word selection for a research participant's practice
    round (Epic 4, Task 4.3). The frontend must not choose these words
    itself from weakEntries - it submits whatever word list this endpoint
    returns. Never returns study_id, condition, or per-word p(learned) - a
    student-facing response is just the words to practice.
    """
    with connect_db() as db:
        try:
            session = build_practice_session(db, identity.id)
        except ResearchPracticeUnavailableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"wordIds": session["wordIds"]}


@router.get("/api/research/vocabulary/review-session")
def get_research_review_session(identity: auth.Identity = Depends(auth.require_student)):
    """Which of a research participant's own retention words are due right
    now (Epic 5, Task 5.7) - from vocab_research_retention_state only, never
    production's SM-2 queue. Same student-safe shape as the practice-session
    endpoint: no study_id, no condition, no "adaptive"/"yoked" label.
    """
    with connect_db() as db:
        try:
            session = build_review_session(db, identity.id)
        except ResearchReviewUnavailableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"wordIds": session["wordIds"]}
