from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
from api.schemas.models import ResearchProbeResponseRequest
from application.research.practice_session import ResearchPracticeUnavailableError, build_practice_session
from application.research.probes import (
    ResearchProbeAssignmentNotFoundError,
    ResearchProbeUnavailableError,
    build_due_probes,
    submit_probe_response,
)
from application.research.fidelity import ResearchStudyNotFoundError, build_admin_summary
from application.research.retention import ResearchReviewUnavailableError, build_review_session
from application.research.response_routing import get_research_context
from db import connect_db

router = APIRouter()


@router.get("/api/research/vocabulary/context")
def get_vocabulary_research_context(identity: auth.Identity = Depends(auth.require_student)):
    """Student-safe research context. Never expose which experimental
    condition(s) the student is assigned to, their study_id, policy/
    assignment version, or practice budget - those would let a student (or
    anyone reading the network tab) infer or reason about their own
    treatment, which is exactly what the research design must prevent.

    practiceAvailable/reviewAvailable/probeAvailable all follow the
    student's actual active research/due state (Epics 4/5/7).
    """
    with connect_db() as db:
        context = get_research_context(db, identity.id)
        probe_available = False
        if context.active:
            try:
                probe_available = bool(build_due_probes(db, identity.id)["questions"])
            except ResearchProbeUnavailableError:
                probe_available = False
    return {
        "active": context.active,
        "coreCompletionPolicy": context.progression_policy.value,
        "practiceAvailable": context.active,
        "reviewAvailable": context.active,
        "probeAvailable": probe_available,
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


@router.get("/api/research/vocabulary/probes/due")
def get_research_probes_due(identity: auth.Identity = Depends(auth.require_student)):
    """Task 7.5: due, unanswered "Learning Check" questions only, from the
    independent outcome bank - never the normal quiz-attempt/core content.
    Never returns probe_type, study_id, or the correct answer (Task 7.6);
    the neutral "Learning Check" framing (Task 7.8) is a frontend concern
    this endpoint only enables by staying silent about the research design.
    """
    with connect_db() as db:
        try:
            session = build_due_probes(db, identity.id)
        except ResearchProbeUnavailableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session


@router.post("/api/research/vocabulary/probes/{assignment_id}/response")
def submit_research_probe_response(
    assignment_id: int,
    payload: ResearchProbeResponseRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    """Task 7.5: a probe is never submitted through the normal quiz-attempt
    API. Task 7.6: the response is graded server-side only - this always
    returns a plain acknowledgement, never correctness, the correct answer,
    or an explanation, since feedback here would itself be an intervention
    on the outcome measure it's meant to read.
    """
    with connect_db() as db:
        try:
            result = submit_probe_response(
                db, identity.id, assignment_id, payload.response,
                source_response_id=payload.sourceResponseId,
            )
        except ResearchProbeAssignmentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.get("/api/research/vocabulary/admin/summary")
def get_research_admin_summary(study_id: str, identity: auth.Identity = Depends(auth.require_admin)):
    """Task 8.3/8.4: the research admin page's one data call - study status,
    participant counts, assignment balance, and fidelity (Task 8.2). Admin
    only, unlike every other endpoint in this router, and the only one that
    is allowed to return condition information - it never reaches a student
    or a teacher (Task 8.5's blinding is enforced by this dependency, not by
    trusting every caller to only ask for their own data).
    """
    with connect_db() as db:
        try:
            summary = build_admin_summary(db, study_id)
        except ResearchStudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return summary
