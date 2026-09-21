from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb

import security.auth as auth
from main import QuizApproveRequest
from db import connect_db

router = APIRouter(dependencies=[Depends(auth.require_teacher_or_admin)])

_MAX_PUBLISHED_WRONG_OPTIONS = 3


def _publishable_material_or_raise(material: list[dict]) -> list[dict]:
    """Return a canonical, publishable snapshot or reject the publish.

    The browser only shows three wrong choices per question. Trim every
    approved pool to those three choices before publish. Quiz material is
    entirely teacher-authored (typed or bulk-uploaded) now — no AI
    generation or validation runs here, only structural checks: a word
    can't be blank or repeated, and a cloze/synonym candidate can't have
    blank prompt text. The teacher is responsible for question quality.
    """
    canonical: list[dict] = []
    seen_words: set[str] = set()

    for entry in material:
        word = str(entry.get("word", "")).strip()
        if not word:
            raise HTTPException(status_code=422, detail="Quiz material contains an empty word.")
        if word in seen_words:
            raise HTTPException(status_code=422, detail=f"Quiz material repeats the word: {word}")
        seen_words.add(word)

        distractors = list(entry.get("distractors", []))[:_MAX_PUBLISHED_WRONG_OPTIONS]

        cloze = []
        for candidate in entry.get("cloze", []):
            sentence = str(candidate.get("sentence", "")).strip()
            if not sentence:
                raise HTTPException(
                    status_code=422,
                    detail=f"Quiz material has an empty cloze sentence for: {word}",
                )
            cloze.append(
                {
                    **candidate,
                    "sentence": sentence,
                    "distractors": list(candidate.get("distractors", []))[:_MAX_PUBLISHED_WRONG_OPTIONS],
                }
            )

        synonym = []
        for candidate in entry.get("synonym", []):
            syn = str(candidate.get("synonym", "")).strip()
            if not syn:
                raise HTTPException(
                    status_code=422,
                    detail=f"Quiz material has an empty synonym for: {word}",
                )
            synonym.append(
                {
                    **candidate,
                    "synonym": syn,
                    "distractors": list(candidate.get("distractors", []))[:_MAX_PUBLISHED_WRONG_OPTIONS],
                }
            )

        canonical.append(
            {
                **entry,
                "word": word,
                "distractors": distractors,
                "cloze": cloze,
                "synonym": synonym,
            }
        )
    return canonical


@router.post("/api/custom-stories/{story_id}/quiz/approve")
async def approve_quiz_material(story_id: str, request: QuizApproveRequest):
    """The only place quiz_approved_snapshot changes. `material` is built by
    the caller from the candidates a teacher checked (typed by hand or bulk
    uploaded) in the review UI — this becomes exactly what students are
    served for this tier once approved."""
    # Fail fast for a stale/deleted story instead of writing material that
    # cannot be published anyway.
    with connect_db() as db:
        exists = db.execute("SELECT 1 FROM custom_stories WHERE id = %s", (story_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Story not found.")

    material = _publishable_material_or_raise([w.model_dump() for w in request.material])
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
