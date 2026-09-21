import json

from fastapi import APIRouter, Depends

import auth
from db import connect_db
from models import (
    MAX_VOCAB_CLOZE_PER_WORD,
    MAX_VOCAB_DISTRACTORS_PER_WORD,
    MAX_VOCAB_SYNONYM_PER_WORD,
    VocabularyClozeUpdateRequest,
    VocabularyDistractorsUpdateRequest,
    VocabularySynonymUpdateRequest,
)
from routers.story_quiz_materials import (
    _existing_pool,
    _load_frames,
    _write_frame_field,
)


router = APIRouter(dependencies=[Depends(auth.require_story_access)])


@router.patch("/api/custom-stories/{story_id}/vocabulary-distractors")
def update_vocabulary_distractors(
    story_id: str, request: VocabularyDistractorsUpdateRequest
):
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
                    or len(merged) >= MAX_VOCAB_DISTRACTORS_PER_WORD
                ):
                    continue
                seen.add(key)
                merged.append(distractor)
            pool[update.wordIndex] = merged
            frame["vocabularyDistractors"] = json.dumps(pool, ensure_ascii=False)
            _write_frame_field(
                db, story_id, update.frameIndex, "vocabularyDistractors",
                frame["vocabularyDistractors"],
            )
    return {"ok": True}


@router.patch("/api/custom-stories/{story_id}/vocabulary-cloze")
def update_vocabulary_cloze(story_id: str, request: VocabularyClozeUpdateRequest):
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
                    or len(merged) >= MAX_VOCAB_CLOZE_PER_WORD
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
def update_vocabulary_synonym(story_id: str, request: VocabularySynonymUpdateRequest):
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
                    or len(merged) >= MAX_VOCAB_SYNONYM_PER_WORD
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
