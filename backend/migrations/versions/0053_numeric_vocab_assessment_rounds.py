"""Normalize published vocabulary assessment banks to numeric rounds.

The old bank shape encoded the round in a difficulty label and frequently in
the question id.  New banks use the source question id plus round 1/2/3 and
the exact question type.  Response ledgers and in-progress attempt snapshots
are immutable and are intentionally not rewritten here.
"""

from __future__ import annotations

import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_TYPE_TO_ROUND = {
    "basic_meaning_mcq": 1,
    "character_to_pinyin_typing": 2,
    "context_cloze_mcq": 3,
}
_TIER_BY_ROUND = {1: "tier1", 2: "tier2", 3: "tier3"}


def _round(item: dict[str, Any]) -> int | None:
    value = item.get("round")
    if isinstance(value, str):
        value = value.strip().casefold().replace("round", "").strip()
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    if parsed in _TIER_BY_ROUND:
        return parsed
    weight = item.get("difficultyWeight")
    try:
        parsed = int(weight)
    except (TypeError, ValueError):
        parsed = 0
    if parsed in _TIER_BY_ROUND:
        return parsed
    level = str(item.get("level") or "").strip().casefold()
    return {"easy": 1, "medium": 2, "hard": 3}.get(level) or _TYPE_TO_ROUND.get(str(item.get("questionType") or ""))


def _clean_bank(story_id: str, assessment: Any) -> list[dict[str, Any]] | None:
    if not isinstance(assessment, list):
        return None
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_word_rounds: set[tuple[str, int]] = set()
    for index, raw in enumerate(assessment, start=1):
        if not isinstance(raw, dict):
            raise RuntimeError(f"Story {story_id} has a non-object vocabulary assessment row {index}.")
        round_number = _round(raw)
        if round_number is None:
            raise RuntimeError(f"Story {story_id} row {index} has no supported round or question type.")
        question_type = {
            1: "basic_meaning_mcq",
            2: "character_to_pinyin_typing",
            3: "context_cloze_mcq",
        }[round_number]
        word_id = str(raw.get("wordId") or raw.get("word_id") or "").strip()
        if not word_id:
            raise RuntimeError(f"Story {story_id} row {index} has no word id.")
        word_round = (word_id, round_number)
        if word_round in seen_word_rounds:
            raise RuntimeError(f"Story {story_id} has duplicate Word Key + Round {word_id} + {round_number}.")
        seen_word_rounds.add(word_round)
        question_id = str(raw.get("sourceQuestionId") or raw.get("questionId") or "").strip()
        if not question_id:
            raise RuntimeError(f"Story {story_id} row {index} has no question id.")
        if question_id.casefold().endswith(("_easy", "_medium", "_hard")):
            question_id = f"legacy-{story_id}-{index}"
        if question_id in seen:
            raise RuntimeError(f"Story {story_id} has duplicate question id {question_id} after normalization.")
        seen.add(question_id)
        item = dict(raw)
        for key in ("level", "difficultyWeight", "sourceQuestionId", "question_type", "answer_format"):
            item.pop(key, None)
        if round_number == 2:
            pinyin = str(item.get("pinyin") or item.get("correctAnswer") or "").strip()
            item["options"] = []
            item["correctAnswer"] = pinyin
            item["acceptedAnswers"] = [pinyin] if pinyin else []
            item["answerFormat"] = "free_text"
        else:
            item["answerFormat"] = "single_choice"
            options = item.get("options")
            if not isinstance(options, list) or len(options) != 4 or len(set(map(str, options))) != 4:
                correct = str(item.get("correctAnswer") or item.get("targetWord") or "").strip()
                item["options"] = [correct, "Other option 1", "Other option 2", "Other option 3"]
            accepted = item.get("acceptedAnswers")
            if not isinstance(accepted, list) or not accepted:
                item["acceptedAnswers"] = [str(item.get("correctAnswer") or item.get("targetWord") or "").strip()]
        item.update({
            "questionId": question_id,
            "round": round_number,
            "tier": _TIER_BY_ROUND[round_number],
            "questionType": question_type,
        })
        cleaned.append(item)
    return cleaned


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, vocab_assessment FROM custom_stories WHERE jsonb_typeof(vocab_assessment) = 'array'")
    ).mappings().all()
    for row in rows:
        cleaned = _clean_bank(str(row["id"]), row["vocab_assessment"])
        if cleaned is not None:
            bind.execute(
                sa.text("UPDATE custom_stories SET vocab_assessment = CAST(:assessment AS jsonb) WHERE id = :id"),
                {"id": row["id"], "assessment": json.dumps(cleaned, ensure_ascii=False)},
            )


def downgrade() -> None:
    raise RuntimeError("Numeric vocabulary assessment rounds cannot be downgraded to difficulty labels automatically.")
