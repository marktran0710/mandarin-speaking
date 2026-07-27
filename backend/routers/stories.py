import json

from fastapi import APIRouter, HTTPException, Query
from psycopg.types.json import Jsonb

from database import connect_db, row_to_custom_story
import main
from main import (
    CustomStoryRequest,
    QuizExclusionsUpdateRequest,
    QuizPendingApprovalsUpdateRequest,
    QuizQuestionReplaceRequest,
    VocabularyClozeUpdateRequest,
    VocabularyDistractorsUpdateRequest,
    VocabularyLookalikeUpdateRequest,
    VocabularySynonymUpdateRequest,
)

router = APIRouter()


def _load_frames(db, story_id: str) -> list:
    """Reads a story's frames (already-parsed JSONB), 404-ing if it's gone."""
    row = db.execute(
        "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Story not found.")
    return row["frames"] or []


def _write_frame_field(db, story_id: str, frame_index: int, field: str, value_json: str) -> None:
    """Writes one field of one frame in place.

    jsonb_set targets `frames -> frame_index -> field` instead of rewriting
    the whole frames array, so two PATCHes touching different frames (or
    different fields of the same frame) can't clobber each other's work.

    `value_json` is a JSON *string* — the pools are stored serialised inside
    the frame because the frontend does JSON.parse() on them, so to_jsonb()
    of the text is exactly the right value.
    """
    db.execute(
        "UPDATE custom_stories "
        "SET frames = jsonb_set(frames, ARRAY[%s, %s], to_jsonb(%s::text), true) "
        "WHERE id = %s",
        (str(frame_index), field, value_json, story_id),
    )


def _existing_pool(frame: dict, field: str) -> list:
    """The per-word pool for a frame field, as a Python list.

    Stored as a JSON string inside the frame; a malformed or missing value
    is treated as an empty pool rather than failing the request.
    """
    try:
        pool = json.loads(frame.get(field) or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return pool if isinstance(pool, list) else []


@router.get("/api/custom-stories")
async def list_custom_stories(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM custom_stories ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, skip),
        ).fetchall()
    return [row_to_custom_story(row) for row in rows]


@router.post("/api/custom-stories")
async def create_custom_story(story: CustomStoryRequest):
    frames = [frame.model_dump() for frame in story.frames]
    stored_frames = main.persist_story_frame_images(story.id, frames)
    stored_frames = main.persist_story_frame_audio(story.id, stored_frames)
    with connect_db() as db:
        # ON CONFLICT DO UPDATE, not the old INSERT OR REPLACE: SQLite's
        # replace was a DELETE+INSERT, so every re-save wiped the two columns
        # missing from this list (quiz_exclusions, created_at). Updating only
        # the listed columns keeps a teacher's quiz-review work and the
        # story's original position in the list.
        db.execute(
            """
            INSERT INTO custom_stories (
                id, title, learning_goal, frames, published, linear,
                lesson_number, narrative_mode, first_frame_is_example
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                learning_goal = EXCLUDED.learning_goal,
                frames = EXCLUDED.frames,
                published = EXCLUDED.published,
                linear = EXCLUDED.linear,
                lesson_number = EXCLUDED.lesson_number,
                narrative_mode = EXCLUDED.narrative_mode,
                first_frame_is_example = EXCLUDED.first_frame_is_example
            """,
            (
                story.id,
                story.title,
                story.learningGoal,
                Jsonb(stored_frames),
                story.published,
                story.linear,
                story.lessonNumber,
                story.narrativeMode,
                story.firstFrameIsExample,
            ),
        )
    return {
        **story.model_dump(),
        "frames": stored_frames,
    }


@router.delete("/api/custom-stories/{story_id}")
async def delete_custom_story(story_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s",
            (story_id,),
        ).fetchone()
        db.execute("DELETE FROM custom_stories WHERE id = %s", (story_id,))
    if row:
        for frame in row["frames"] or []:
            main.remove_uploaded_file(frame.get("imageUrl", ""))
            main.remove_uploaded_file(frame.get("listenAudioUrl", ""))
    return {"ok": True}


@router.patch("/api/custom-stories/{story_id}/vocabulary-distractors")
async def update_vocabulary_distractors(
    story_id: str, request: VocabularyDistractorsUpdateRequest
):
    """
    Tops up a story's per-word distractor pool (grown over time as students
    complete quiz rounds) rather than replacing it — merges new distractors
    into the existing list per word, deduping case-insensitively and capping
    at MAX_VOCAB_DISTRACTORS_PER_WORD so the pool doesn't grow unbounded.
    """
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularyDistractors")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {d.strip().lower() for d in existing}
            merged = list(existing)
            for distractor in update.distractors:
                distractor = distractor.strip()
                key = distractor.lower()
                if (
                    not distractor
                    or key in seen
                    or len(merged) >= main.MAX_VOCAB_DISTRACTORS_PER_WORD
                ):
                    continue
                seen.add(key)
                merged.append(distractor)
            pool[update.wordIndex] = merged
            # Keep the local copy in sync so several updates to the same
            # frame in one request build on each other.
            frame["vocabularyDistractors"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularyDistractors",
                frame["vocabularyDistractors"],
            )
    return {"ok": True}


@router.patch("/api/custom-stories/{story_id}/vocabulary-lookalike")
async def update_vocabulary_lookalike(
    story_id: str, request: VocabularyLookalikeUpdateRequest
):
    """
    Tops up a story's per-word look-alike pool (the tier-3 quiz's
    face-confusion traps), mirroring update_vocabulary_distractors above —
    merges new characters into the existing list per word, deduping and
    capping at MAX_VOCAB_LOOKALIKE_PER_WORD.
    """
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularyLookalike")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {c.strip() for c in existing}
            merged = list(existing)
            for lookalike in update.lookalikes:
                lookalike = lookalike.strip()
                if (
                    not lookalike
                    or lookalike in seen
                    or len(merged) >= main.MAX_VOCAB_LOOKALIKE_PER_WORD
                ):
                    continue
                seen.add(lookalike)
                merged.append(lookalike)
            pool[update.wordIndex] = merged
            frame["vocabularyLookalike"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularyLookalike",
                frame["vocabularyLookalike"],
            )
    return {"ok": True}


@router.put("/api/custom-stories/{story_id}/quiz-exclusions")
async def update_quiz_exclusions(story_id: str, request: QuizExclusionsUpdateRequest):
    """Replaces the story's teacher-marked bad-quiz-material list wholesale —
    the review page's toggles always send the complete current set, so PUT
    semantics keep the endpoint idempotent and trivially undoable. Also
    stamps quiz_material_snapshot (when sent) in the same statement, so the
    two columns can never drift out of sync with each other."""
    exclusions = [exclusion.model_dump(exclude_none=True) for exclusion in request.exclusions]
    with connect_db() as db:
        row = db.execute(
            "UPDATE custom_stories SET quiz_exclusions = %s, "
            "quiz_material_snapshot = COALESCE(%s, quiz_material_snapshot) "
            "WHERE id = %s RETURNING id",
            (
                Jsonb(exclusions),
                Jsonb(request.materialSnapshot) if request.materialSnapshot is not None else None,
                story_id,
            ),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Story not found.")
    return {"id": story_id, "quizExclusions": exclusions}


@router.put("/api/custom-stories/{story_id}/quiz-pending-approvals")
async def update_quiz_pending_approvals(story_id: str, request: QuizPendingApprovalsUpdateRequest):
    """Saves the Quiz Review page's opt-in checkbox selections for one tier
    — not a publish action (see /quiz/approve), just so a teacher's
    in-progress review survives a page reload. Keyed by tier like
    quiz_approved_snapshot, replaced wholesale per tier so one tier's save
    never clobbers another's."""
    approvals = [a.model_dump(exclude_none=True) for a in request.approvals]
    with connect_db() as db:
        row = db.execute(
            "UPDATE custom_stories SET quiz_pending_approvals = "
            "jsonb_set(COALESCE(quiz_pending_approvals, '{}'::jsonb), ARRAY[%s], %s) "
            "WHERE id = %s RETURNING id",
            (request.level, Jsonb(approvals), story_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Story not found.")
    return {"id": story_id, "level": request.level, "approvals": approvals}


@router.put("/api/custom-stories/{story_id}/quiz-question")
async def replace_quiz_question(story_id: str, request: QuizQuestionReplaceRequest):
    """Replaces one candidate's content in place, unlike the vocabulary-*
    PATCH endpoints above (which only merge new items into a pool and can't
    fix an existing bad one). distractors has no poolIndex — editing it
    replaces the word's whole distractor list, matching how Quiz Review
    shows it as a single row. Frontend resets that row to unvalidated and
    unchecked after a successful edit."""
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        if request.frameIndex >= len(frames):
            raise HTTPException(status_code=404, detail="Frame not found.")
        frame = frames[request.frameIndex]
        field = {
            "distractors": "vocabularyDistractors",
            "cloze": "vocabularyCloze",
            "synonym": "vocabularySynonym",
        }[request.kind]
        pool = _existing_pool(frame, field)
        while len(pool) <= request.wordIndex:
            pool.append([] if request.kind != "distractors" else [])

        if request.kind == "distractors":
            if not isinstance(request.value, list) or not all(
                isinstance(d, str) for d in request.value
            ):
                raise HTTPException(status_code=422, detail="distractors value must be a list of strings.")
            pool[request.wordIndex] = request.value
        else:
            candidates = pool[request.wordIndex]
            if request.poolIndex is None or request.poolIndex >= len(candidates):
                raise HTTPException(status_code=404, detail="Candidate not found at poolIndex.")
            key = "sentence" if request.kind == "cloze" else "synonym"
            if key not in request.value or not isinstance(request.value.get("distractors"), list):
                raise HTTPException(
                    status_code=422,
                    detail=f"{request.kind} value must have '{key}' and 'distractors'.",
                )
            candidates[request.poolIndex] = {
                key: request.value[key],
                "distractors": request.value["distractors"],
            }
            pool[request.wordIndex] = candidates

        serialized = json.dumps(pool, ensure_ascii=False)
        _write_frame_field(db, story_id, request.frameIndex, field, serialized)
    return {"ok": True}


@router.patch("/api/custom-stories/{story_id}/vocabulary-cloze")
async def update_vocabulary_cloze(story_id: str, request: VocabularyClozeUpdateRequest):
    """
    Tops up a story's per-word cloze-question pool (grown over time as
    students complete quiz rounds), mirroring update_vocabulary_distractors
    above — merges new {sentence, distractors} candidates into the existing
    list per word, deduping by sentence text and capping at
    MAX_VOCAB_CLOZE_PER_WORD so the pool doesn't grow unbounded.
    """
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularyCloze")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {c.get("sentence", "").strip() for c in existing if isinstance(c, dict)}
            merged = list(existing)
            for candidate in update.candidates:
                sentence = candidate.sentence.strip()
                if (
                    not sentence
                    or sentence in seen
                    or len(merged) >= main.MAX_VOCAB_CLOZE_PER_WORD
                ):
                    continue
                seen.add(sentence)
                merged.append({"sentence": sentence, "distractors": candidate.distractors})
            pool[update.wordIndex] = merged
            frame["vocabularyCloze"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularyCloze",
                frame["vocabularyCloze"],
            )
    return {"ok": True}


@router.patch("/api/custom-stories/{story_id}/vocabulary-synonym")
async def update_vocabulary_synonym(story_id: str, request: VocabularySynonymUpdateRequest):
    """
    Tops up a story's per-word synonym-question pool, mirroring
    update_vocabulary_cloze above — merges new {synonym, distractors}
    candidates into the existing list per word, deduping by synonym text and
    capping at MAX_VOCAB_SYNONYM_PER_WORD.
    """
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            pool = _existing_pool(frame, "vocabularySynonym")
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {c.get("synonym", "").strip() for c in existing if isinstance(c, dict)}
            merged = list(existing)
            for candidate in update.candidates:
                synonym = candidate.synonym.strip()
                if (
                    not synonym
                    or synonym in seen
                    or len(merged) >= main.MAX_VOCAB_SYNONYM_PER_WORD
                ):
                    continue
                seen.add(synonym)
                merged.append({"synonym": synonym, "distractors": candidate.distractors})
            pool[update.wordIndex] = merged
            frame["vocabularySynonym"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularySynonym",
                frame["vocabularySynonym"],
            )
    return {"ok": True}
