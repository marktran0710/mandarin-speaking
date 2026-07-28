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
from quiz_bank import candidates_for_review, translation_integrity_candidates
from quiz_chat import make_chat
from quiz_pipeline import validate_candidates

router = APIRouter()

# The pipeline's internal Candidate.kind for a distractor pool is
# "translation" (it shares the translation question's solver/judge prompts) —
# translated back to "distractors" here so the response uses the same pool
# names as QuizExclusionKind (see quizExclusions.ts) instead of leaking an
# implementation detail of quiz_pipeline.py into the API.
_API_KIND = {"cloze": "cloze", "synonym": "synonym"}
_MAX_PUBLISHED_WRONG_OPTIONS = 3


def _pool_index(key: str) -> int | None:
    parts = key.split(":")
    if len(parts) < 3:
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


async def _publishable_material_or_raise(material: list[dict]) -> list[dict]:
    """Return a canonical, fully-verifiable snapshot or reject the publish.

    The browser only shows three wrong choices per question.  Limit every
    approved pool to those three choices before validation so a later shuffle
    cannot surface an unvalidated fourth option.  The server repeats the
    blind solver + judge gate here: UI checkboxes are a convenience, not a
    security or correctness boundary.
    """
    canonical: list[dict] = []
    expected_keys: set[str] = set()
    seen_words: set[str] = set()

    for entry in material:
        word = str(entry.get("word", "")).strip()
        if not word:
            raise HTTPException(status_code=422, detail="Quiz material contains an empty word.")
        if word in seen_words:
            raise HTTPException(status_code=422, detail=f"Quiz material repeats the word: {word}")
        seen_words.add(word)

        distractors = list(entry.get("distractors", []))[:_MAX_PUBLISHED_WRONG_OPTIONS]
        cloze = [
            {**candidate, "distractors": list(candidate.get("distractors", []))[:_MAX_PUBLISHED_WRONG_OPTIONS]}
            for candidate in entry.get("cloze", [])
        ]
        synonym = [
            {**candidate, "distractors": list(candidate.get("distractors", []))[:_MAX_PUBLISHED_WRONG_OPTIONS]}
            for candidate in entry.get("synonym", [])
        ]
        canonical.append(
            {
                **entry,
                "word": word,
                "distractors": distractors,
                "cloze": cloze,
                "synonym": synonym,
            }
        )
        if entry.get("translation"):
            expected_keys.add(f"{word}:translation")
        elif distractors:
            expected_keys.add(f"{word}:distractors")
        expected_keys.update(f"{word}:cloze:{index}" for index in range(len(cloze)))
        expected_keys.update(f"{word}:synonym:{index}" for index in range(len(synonym)))

    candidates = translation_integrity_candidates(canonical) + [
        candidate for candidate in candidates_for_review(canonical, []) if candidate.kind != "translation"
    ]
    candidate_keys = {candidate.key for candidate in candidates}
    missing = expected_keys - candidate_keys
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Quiz material is malformed and cannot be validated: " + ", ".join(sorted(missing)),
        )
    if not candidates:
        return canonical

    chat = make_chat(main.GROQ_API_KEY, main.GEMINI_API_KEY)
    result = await validate_candidates(chat, candidates, max_repairs=0)
    if result.dropped:
        failures = "; ".join(
            f"{outcome.candidate.key}: {outcome.judge.reason if outcome.judge else outcome.reason}"
            for outcome in result.dropped
        )
        raise HTTPException(
            status_code=422,
            detail=f"Quiz material failed the publish validation: {failures}",
        )
    return canonical


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
    candidates = translation_integrity_candidates(words) + [
        candidate for candidate in candidates_for_review(words, exclusions) if candidate.kind != "translation"
    ]
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
    # Fail fast for a stale/deleted story instead of spending LLM calls on
    # material that cannot be published anyway.
    with connect_db() as db:
        exists = db.execute("SELECT 1 FROM custom_stories WHERE id = %s", (story_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Story not found.")

    material = await _publishable_material_or_raise([w.model_dump() for w in request.material])
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
