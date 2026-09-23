"""Admin-only edits of existing Speaking vocabulary metadata."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

import security.auth as auth
import services.story_vocabulary_metadata_service as story_vocabulary_metadata_service
from db import connect_db

router = APIRouter(dependencies=[Depends(auth.require_admin)])


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
    assessmentWordId: str | None = Field(default=None, min_length=1, max_length=200)
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


@router.patch("/api/custom-stories/{story_id}/vocabulary-metadata")
async def update_vocabulary_metadata(story_id: str, edit: VocabularyMetadataEdit):
    with connect_db() as db:
        return story_vocabulary_metadata_service.update_vocabulary_metadata(db, story_id, edit)
