"""Admin-only edits of existing Speaking vocabulary metadata.

Holds the business logic that used to live inline in
routers/story_vocabulary_metadata.py. ``metadata_changes`` and
``update_assessment_metadata`` raise ``fastapi.HTTPException`` directly
(rather than a domain exception) because they are consumed directly - by
name - from other modules (the ``routers.content.vocabulary`` compatibility facade,
and tests) that expect exactly that exception type; changing that would be
a behavior change for those callers, not just this router.
"""
from fastapi import HTTPException

from repositories.content import vocabulary_metadata as repo
from repositories.database import row_to_custom_story

FIELDS = {"vocabulary": "vocabulary", "pinyin": "vocabularyPinyin",
          "translation": "vocabularyTranslation", "pos": "vocabularyPos"}
SUFFIXES = {"easy": ""}


def effective_columns(frame: dict, tier: str) -> dict[str, str]:
    suffix = SUFFIXES[tier]
    result = {}
    for key, field in FIELDS.items():
        base = str(frame.get(field) or "")
        own = str(frame.get(field + suffix) or "")
        result[key] = own if own.strip() else base
    return result


def metadata_changes(frame: dict, edit) -> dict[str, str]:
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


def assessment_columns(question: dict) -> dict[str, str]:
    return {
        "vocabulary": str(question.get("targetWord") or ""),
        "pinyin": str(question.get("pinyin") or ""),
        "translation": str(question.get("simpleEnglishMeaning") or ""),
        "pos": str(question.get("pos") or ""),
    }


def update_assessment_metadata(assessment: list, edit) -> list:
    """Update one quiz word's shared fields across its three round rows."""
    rows = [row for row in assessment if isinstance(row, dict) and row.get("wordId") == edit.assessmentWordId]
    if not rows:
        raise HTTPException(409, "The selected quiz word changed. Reload the story before saving again.")
    current = assessment_columns(rows[0])
    if current != edit.expected.model_dump() or current["vocabulary"] != edit.word:
        raise HTTPException(409, "Quiz vocabulary changed. Reload the story before saving again.")
    if any(assessment_columns(row) != current for row in rows[1:]):
        raise HTTPException(409, "Quiz vocabulary is inconsistent. Reload the story before saving again.")

    old_pinyin, old_translation = current["pinyin"], current["translation"]
    for row in rows:
        row["pinyin"] = edit.pinyin
        row["simpleEnglishMeaning"] = edit.translation
        row["pos"] = edit.pos
        # Easy questions grade the English gloss, Medium questions grade the
        # reading. Keep their answer keys and visible correct option aligned
        # with the vocabulary that students see in all three rounds.
        if row.get("questionType") == "basic_meaning_mcq":
            _replace_answer_value(row, old_translation, edit.translation)
        elif row.get("questionType") == "character_to_pinyin_typing":
            _replace_answer_value(row, old_pinyin, edit.pinyin)
    return assessment


def _replace_answer_value(question: dict, old: str, new: str) -> None:
    if question.get("correctAnswer") == old:
        question["correctAnswer"] = new
    for field in ("acceptedAnswers", "options"):
        values = question.get(field)
        if isinstance(values, list):
            question[field] = [new if value == old else value for value in values]


def update_vocabulary_metadata(db, story_id: str, edit) -> dict:
    row = repo.find_story_for_update(db, story_id)
    if row is None:
        raise HTTPException(404, "Story not found.")
    if edit.assessmentWordId:
        assessment = row.get("vocab_assessment")
        if not isinstance(assessment, list):
            raise HTTPException(409, "Quiz vocabulary changed. Reload the story before saving again.")
        updated_assessment = update_assessment_metadata(assessment, edit)
        repo.set_vocab_assessment(db, story_id, updated_assessment)
    elif edit.storyWide:
        story_vocabulary = row.get("story_vocabulary") or {}
        current_vocabulary = story_vocabulary.get("easy") if isinstance(story_vocabulary, dict) else None
        if not isinstance(current_vocabulary, dict):
            raise HTTPException(409, "Story-wide vocabulary changed. Reload the story before saving again.")
        changes = metadata_changes(current_vocabulary, edit)
        for field, value in changes.items():
            repo.set_story_vocabulary_field(db, story_id, field, value)
    else:
        frames = row["frames"] or []
        if edit.frameIndex >= len(frames):
            raise HTTPException(409, "The selected scene changed. Reload the story before saving again.")
        changes = metadata_changes(frames[edit.frameIndex], edit)
        # The lock and field-level writes preserve unrelated content and
        # published quiz snapshots, which still require explicit Quiz Review.
        for field, value in changes.items():
            repo.set_frame_field(db, story_id, edit.frameIndex, field, value)
    updated = repo.find_story(db, story_id)
    return row_to_custom_story(updated)
