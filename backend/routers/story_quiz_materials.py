import json

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb

import auth
from db import connect_db
from models import (
    QuizExclusionsUpdateRequest,
    QuizPendingApprovalsUpdateRequest,
    QuizQuestionReplaceRequest,
)


router = APIRouter(dependencies=[Depends(auth.require_story_access)])


def _load_frames(db, story_id: str) -> list:
    row = db.execute(
        "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Story not found.")
    return row["frames"] or []


def _write_frame_field(db, story_id: str, frame_index: int, field: str, value_json: str) -> None:
    db.execute(
        "UPDATE custom_stories "
        "SET frames = jsonb_set(frames, ARRAY[%s, %s], to_jsonb(%s::text), true) "
        "WHERE id = %s",
        (str(frame_index), field, value_json, story_id),
    )


def _existing_pool(frame: dict, field: str) -> list:
    try:
        pool = json.loads(frame.get(field) or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return pool if isinstance(pool, list) else []


@router.put("/api/custom-stories/{story_id}/quiz-exclusions")
def update_quiz_exclusions(story_id: str, request: QuizExclusionsUpdateRequest):
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
def update_quiz_pending_approvals(story_id: str, request: QuizPendingApprovalsUpdateRequest):
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
def replace_quiz_question(story_id: str, request: QuizQuestionReplaceRequest):
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        if request.frameIndex >= len(frames):
            raise HTTPException(status_code=404, detail="Frame not found.")
        frame = frames[request.frameIndex]
        if request.kind == "translation":
            if not isinstance(request.value, str) or not request.value.strip():
                raise HTTPException(status_code=422, detail="translation value must be a non-empty string.")
            field = request.translationField or "vocabularyTranslation"
            translations = [item.strip() for item in str(frame.get(field) or "").split(",")]
            while len(translations) <= request.wordIndex:
                translations.append("")
            vocabulary_field = field.replace("Translation", "")
            vocabulary_text = str(frame.get(vocabulary_field) or frame.get("vocabulary") or "")
            words = [word.strip() for word in vocabulary_text.split(",")]
            if request.wordIndex >= len(words) or not words[request.wordIndex]:
                raise HTTPException(status_code=422, detail="Translation does not have a matching vocabulary word.")
            translations[request.wordIndex] = request.value.strip()
            _write_frame_field(db, story_id, request.frameIndex, field, ", ".join(translations))
            db.execute(
                "UPDATE custom_stories SET quiz_approved_snapshot = "
                "COALESCE((SELECT jsonb_object_agg(k, COALESCE((SELECT jsonb_agg(item) "
                "FROM jsonb_array_elements(v) AS item WHERE item->>'word' <> %s), '[]'::jsonb)) "
                "FROM jsonb_each(quiz_approved_snapshot) AS entries(k, v)), '{}'::jsonb) "
                "WHERE id = %s",
                (words[request.wordIndex], story_id),
            )
            return {"ok": True, "approvedSnapshotsInvalidated": True}
        if request.kind == "pinyin":
            if not isinstance(request.value, str) or not request.value.strip():
                raise HTTPException(status_code=422, detail="pinyin value must be a non-empty string.")
            field = request.pinyinField or "vocabularyPinyin"
            pinyins = [item.strip() for item in str(frame.get(field) or "").split(",")]
            while len(pinyins) <= request.wordIndex:
                pinyins.append("")
            pinyins[request.wordIndex] = request.value.strip()
            _write_frame_field(db, story_id, request.frameIndex, field, ", ".join(pinyins))
            return {"ok": True}
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
