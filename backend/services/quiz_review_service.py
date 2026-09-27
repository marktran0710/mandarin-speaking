"""Use-case orchestration for publishing teacher-approved quiz material.

Raises QuizReviewError (not HTTPException) - the router maps it to an HTTP
status code. This module opens its own ``connect_db()`` blocks (rather than
taking an already-open connection) because the original router endpoint
deliberately ran the existence check and the write as two separate
transactions, with the (non-DB) material validation happening in between -
that two-transaction shape is preserved here verbatim.
"""
from db import connect_db
from repositories import quiz_review_repository as repo

_MAX_PUBLISHED_WRONG_OPTIONS = 3


class QuizReviewError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


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
            raise QuizReviewError(422, "Quiz material contains an empty word.")
        if word in seen_words:
            raise QuizReviewError(422, f"Quiz material repeats the word: {word}")
        seen_words.add(word)

        distractors = list(entry.get("distractors", []))[:_MAX_PUBLISHED_WRONG_OPTIONS]

        cloze = []
        for candidate in entry.get("cloze", []):
            sentence = str(candidate.get("sentence", "")).strip()
            if not sentence:
                raise QuizReviewError(
                    422,
                    f"Quiz material has an empty cloze sentence for: {word}",
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
                raise QuizReviewError(
                    422,
                    f"Quiz material has an empty synonym for: {word}",
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


def approve_quiz_material(story_id: str, level: str, material_dicts: list[dict]) -> dict:
    """The only place quiz_approved_snapshot changes. ``material_dicts`` is
    built by the caller from the candidates a teacher checked (typed by hand
    or bulk uploaded) in the review UI — this becomes exactly what students
    are served for this tier once approved."""
    # Fail fast for a stale/deleted story instead of writing material that
    # cannot be published anyway.
    with connect_db() as db:
        exists = repo.story_exists(db, story_id)
    if not exists:
        raise QuizReviewError(404, "Story not found.")

    material = _publishable_material_or_raise(material_dicts)
    with connect_db() as db:
        row = repo.set_approved_snapshot_for_level(db, story_id, level, material)
        if not row:
            raise QuizReviewError(404, "Story not found.")
    return {"id": story_id, "level": level, "approvedCount": len(material)}
