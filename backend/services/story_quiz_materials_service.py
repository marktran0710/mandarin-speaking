"""Use-case orchestration for per-frame quiz material: exclusions, pending
approvals, and candidate distractors/cloze/synonym pool edits.

Holds the business logic that used to live inline in
routers/story_quiz_materials.py. Raises ``fastapi.HTTPException`` directly
(rather than a domain exception) because ``existing_pool`` is consumed
directly - by name - from routers/story_quiz_pools.py, and
``replace_quiz_question`` mirrors the same status-code-raising style as the
sibling quiz-vocabulary service for consistency within this cluster.
"""
import json

from fastapi import HTTPException

from repositories import story_quiz_materials_repository as repo


def existing_pool(frame: dict, field: str) -> list:
    try:
        pool = json.loads(frame.get(field) or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return pool if isinstance(pool, list) else []


def load_frames(db, story_id: str) -> list:
    frames = repo.find_frames(db, story_id)
    if frames is None:
        raise HTTPException(status_code=404, detail="Story not found.")
    return frames


def update_quiz_exclusions(db, story_id: str, request) -> dict:
    exclusions = [exclusion.model_dump(exclude_none=True) for exclusion in request.exclusions]
    row = repo.set_quiz_exclusions(db, story_id, exclusions, request.materialSnapshot)
    if not row:
        raise HTTPException(status_code=404, detail="Story not found.")
    return {"id": story_id, "quizExclusions": exclusions}


def update_quiz_pending_approvals(db, story_id: str, request) -> dict:
    approvals = [a.model_dump(exclude_none=True) for a in request.approvals]
    row = repo.set_quiz_pending_approvals(db, story_id, request.level, approvals)
    if not row:
        raise HTTPException(status_code=404, detail="Story not found.")
    return {"id": story_id, "level": request.level, "approvals": approvals}


def replace_quiz_question(db, story_id: str, request) -> dict:
    frames = load_frames(db, story_id)
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
        repo.write_frame_field(db, story_id, request.frameIndex, field, ", ".join(translations))
        repo.invalidate_translation_word_from_approved_snapshot(db, words[request.wordIndex], story_id)
        return {"ok": True, "approvedSnapshotsInvalidated": True}
    if request.kind == "pinyin":
        if not isinstance(request.value, str) or not request.value.strip():
            raise HTTPException(status_code=422, detail="pinyin value must be a non-empty string.")
        field = request.pinyinField or "vocabularyPinyin"
        pinyins = [item.strip() for item in str(frame.get(field) or "").split(",")]
        while len(pinyins) <= request.wordIndex:
            pinyins.append("")
        pinyins[request.wordIndex] = request.value.strip()
        repo.write_frame_field(db, story_id, request.frameIndex, field, ", ".join(pinyins))
        return {"ok": True}
    field = {
        "distractors": "vocabularyDistractors",
        "cloze": "vocabularyCloze",
        "synonym": "vocabularySynonym",
    }[request.kind]
    pool = existing_pool(frame, field)
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
    repo.write_frame_field(db, story_id, request.frameIndex, field, serialized)
    return {"ok": True}
