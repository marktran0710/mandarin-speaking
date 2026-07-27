from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

import main
from main import (
    QuizApproveRequest,
    QuizValidateRequest,
    QuizValidateResponse,
    QuizValidateResultItem,
)
from database import connect_db
from quiz_bank import candidates_for_review
from quiz_chat import make_chat
from quiz_pipeline import validate_candidates

router = APIRouter()

# The pipeline's internal Candidate.kind for a distractor pool is
# "translation" (it shares the translation question's solver/judge prompts) —
# translated back to "distractors" here so the response uses the same pool
# names as QuizExclusionKind (see quizExclusions.ts) instead of leaking an
# implementation detail of quiz_pipeline.py into the API.
_API_KIND = {"translation": "distractors", "cloze": "cloze", "synonym": "synonym"}


def _pool_index(key: str) -> int | None:
    parts = key.split(":")
    if len(parts) < 3:
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


@router.post(
    "/api/custom-stories/{story_id}/quiz/validate",
    response_model=QuizValidateResponse,
)
async def validate_quiz_material(story_id: str, request: QuizValidateRequest):
    """Runs the adversarial pipeline (pre-gate -> blind solver -> judge, no
    repair) against a story's *current* live quiz material — whatever
    exists, teacher-authored or grown in the background by students'
    practice rounds — and labels each item clean or suspicious. Read-only:
    nothing is written here, so a teacher can validate freely before
    deciding what to exclude or approve."""
    words = [w.model_dump() for w in request.words]
    exclusions = [e.model_dump(exclude_none=True) for e in request.exclusions]
    candidates = candidates_for_review(words, exclusions)
    if not candidates:
        return QuizValidateResponse(results=[])

    chat = make_chat(main.GROQ_API_KEY, main.GEMINI_API_KEY)
    # max_repairs=0: detection only. The teacher decides what to do with a
    # suspicious item (exclude it or leave it); the pipeline never rewrites
    # material on its own here.
    result = await validate_candidates(chat, candidates, max_repairs=0)

    results = []
    for outcome in result.kept:
        results.append(
            QuizValidateResultItem(
                word=outcome.candidate.word,
                kind=_API_KIND.get(outcome.candidate.kind, outcome.candidate.kind),
                poolIndex=_pool_index(outcome.candidate.key),
                status="clean",
                reason="",
            )
        )
    for outcome in result.dropped:
        results.append(
            QuizValidateResultItem(
                word=outcome.candidate.word,
                kind=_API_KIND.get(outcome.candidate.kind, outcome.candidate.kind),
                poolIndex=_pool_index(outcome.candidate.key),
                status="suspicious",
                # outcome.reason is a coarse bucket ("rejected", "pre-gate
                # rule name") used for aggregate counts; the judge's actual
                # free-text explanation is what tells a teacher what to look
                # at, so prefer it whenever a judge ran.
                reason=outcome.judge.reason if outcome.judge else outcome.reason,
            )
        )
    return QuizValidateResponse(results=results)


@router.post("/api/custom-stories/{story_id}/quiz/approve")
async def approve_quiz_material(story_id: str, request: QuizApproveRequest):
    """The only place quiz_approved_snapshot changes. `material` is built by
    the caller from only the candidates a teacher explicitly checked in the
    opt-in review UI — this becomes exactly what students are served for
    this tier. Nothing reaches here without already having been visibly
    validated and deliberately checked, so there's no separate confirm gate."""
    material = [w.model_dump() for w in request.material]
    with connect_db() as db:
        row = db.execute(
            "UPDATE custom_stories SET quiz_approved_snapshot = "
            "jsonb_set(COALESCE(quiz_approved_snapshot, '{}'::jsonb), ARRAY[%s], %s) "
            "WHERE id = %s RETURNING id",
            (request.level, Jsonb(material), story_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Story not found.")
    return {"id": story_id, "level": request.level, "approvedCount": len(material)}
