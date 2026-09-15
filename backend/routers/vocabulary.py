"""Admin-only edits of existing Speaking vocabulary metadata."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

import auth
from database import connect_db, row_to_custom_story

router = APIRouter(dependencies=[Depends(auth.require_admin)])
FIELDS = {"vocabulary": "vocabulary", "pinyin": "vocabularyPinyin",
          "translation": "vocabularyTranslation", "pos": "vocabularyPos"}
SUFFIXES = {"easy": ""}


class VocabularyColumns(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vocabulary: str = Field(max_length=40000)
    pinyin: str = Field(max_length=40000)
    translation: str = Field(max_length=40000)
    pos: str = Field(max_length=40000)


class VocabularyMetadataEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frameIndex: int = Field(ge=0)
    wordIndex: int = Field(ge=0)
    storyWide: bool = False
    tier: Literal["easy"]
    word: str = Field(min_length=1, max_length=200)
    expected: VocabularyColumns
    pinyin: str = Field(min_length=1, max_length=300)
    translation: str = Field(min_length=1, max_length=500)
    pos: str = Field(min_length=1, max_length=50)

    @field_validator("pinyin", "translation", "pos")
    @classmethod
    def single_cell(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char in value for char in ",\r\n"):
            raise ValueError("Use one non-empty value without commas or line breaks.")
        return value


def effective_columns(frame: dict, tier: str) -> dict[str, str]:
    suffix = SUFFIXES[tier]
    result = {}
    for key, field in FIELDS.items():
        base = str(frame.get(field) or "")
        own = str(frame.get(field + suffix) or "")
        result[key] = own if own.strip() else base
    return result


def metadata_changes(frame: dict, edit: VocabularyMetadataEdit) -> dict[str, str]:
    current = effective_columns(frame, edit.tier)
    if current != edit.expected.model_dump():
        raise HTTPException(409, "Vocabulary changed. Reload the story before saving again.")
    words = [word.strip() for word in current["vocabulary"].split(",")]
    if edit.wordIndex >= len(words) or not words[edit.wordIndex] or words[edit.wordIndex] != edit.word:
        raise HTTPException(409, "The selected word changed. Reload the story before saving again.")
    changes = {}
    for key in ("pinyin", "translation", "pos"):
        cells = [cell.strip() for cell in current[key].split(",")] if current[key] else []
        if len(cells) > len(words):
            raise HTTPException(422, "Vocabulary columns are misaligned. Correct them in Story Builder first.")
        cells.extend([""] * (len(words) - len(cells)))
        value = getattr(edit, key)
        if cells[edit.wordIndex] == value:
            continue
        cells[edit.wordIndex] = value
        changes[FIELDS[key] + SUFFIXES[edit.tier]] = ", ".join(cells)
    return changes


@router.patch("/api/custom-stories/{story_id}/vocabulary-metadata")
async def update_vocabulary_metadata(story_id: str, edit: VocabularyMetadataEdit):
    with connect_db() as db:
        row = db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (story_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Story not found.")
        if edit.storyWide:
            story_vocabulary = row.get("story_vocabulary") or {}
            current_vocabulary = story_vocabulary.get("easy") if isinstance(story_vocabulary, dict) else None
            if not isinstance(current_vocabulary, dict):
                raise HTTPException(409, "Story-wide vocabulary changed. Reload the story before saving again.")
            changes = metadata_changes(current_vocabulary, edit)
            for field, value in changes.items():
                db.execute(
                    "UPDATE custom_stories SET story_vocabulary = jsonb_set("
                    "COALESCE(story_vocabulary, '{}'::jsonb), ARRAY['easy', %s], "
                    "to_jsonb(%s::text), true) WHERE id = %s",
                    (field, value, story_id),
                )
        else:
            frames = row["frames"] or []
            if edit.frameIndex >= len(frames):
                raise HTTPException(409, "The selected scene changed. Reload the story before saving again.")
            changes = metadata_changes(frames[edit.frameIndex], edit)
            # The lock and field-level writes preserve unrelated content and
            # published quiz snapshots, which still require explicit Quiz Review.
            for field, value in changes.items():
                db.execute(
                    "UPDATE custom_stories SET frames = jsonb_set(frames, ARRAY[%s, %s], "
                    "to_jsonb(%s::text), true) WHERE id = %s",
                    (str(edit.frameIndex), field, value, story_id),
                )
        updated = db.execute("SELECT * FROM custom_stories WHERE id = %s", (story_id,)).fetchone()
    return row_to_custom_story(updated)
