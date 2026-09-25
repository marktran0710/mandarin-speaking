"""Student-specific BKT initial priors derived from completed placement.

Placement priors are a runtime/read-model concern.  This module owns the
placement provenance and canonical story metadata checks, while ``bkt.core``
remains a pure implementation of the BKT equations.
"""

from __future__ import annotations

from collections import defaultdict
import unicodedata
from typing import Any, Iterable, Mapping

from analytics.learner_model.bkt.core import BKT_CONFIG, BktConfig


PLACEMENT_CHAPTERS = (5, 6, 7, 8)
PLACEMENT_QUESTIONS_PER_CHAPTER = 7
PLACEMENT_PRIOR_SHRINKAGE_K = 7.0
PLACEMENT_RESOLVER_VERSIONS = frozenset({
    "placement-assessment-v1",
    "placement-workbook-import-v1",
})
PLACEMENT_EXPOSURE_PREFIX = "placement:"
VALID_EVIDENCE_ORIGINS = frozenset({"real", "synthetic"})


def _chapter_number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        chapter = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return chapter if chapter in PLACEMENT_CHAPTERS else None


def is_placement_response(row: Mapping[str, Any]) -> bool:
    """Return whether a normalized row is explicit, eligible placement evidence."""
    exposure_id = str(row.get("diagnostic_exposure_id") or "")
    return (
        bool(row.get("bkt_eligible"))
        and row.get("activity_type") == "diagnostic"
        and exposure_id.startswith(PLACEMENT_EXPOSURE_PREFIX)
        and row.get("resolver_version") in PLACEMENT_RESOLVER_VERSIONS
        and row.get("evidence_origin") in VALID_EVIDENCE_ORIGINS
        and isinstance(row.get("correct"), bool)
    )


def compute_chapter_placement_priors(
    rows: Iterable[Mapping[str, Any]],
    params: BktConfig = BKT_CONFIG,
    *,
    questions_per_chapter: int = PLACEMENT_QUESTIONS_PER_CHAPTER,
    shrinkage_k: float = PLACEMENT_PRIOR_SHRINKAGE_K,
) -> dict[int, float]:
    """Compute valid chapter priors from one student's placement rows.

    Each usable chapter must contain exactly the expected number of distinct
    placement items.  Rows from mixed evidence origins are rejected together
    so real and synthetic placement can never be silently combined.
    """
    if questions_per_chapter < 1 or shrinkage_k <= 0:
        return {}

    valid_rows: list[tuple[int, Mapping[str, Any]]] = []
    origins: set[str] = set()
    for row in rows:
        if not is_placement_response(row):
            continue
        chapter = _chapter_number(row.get("chapter"))
        if chapter is None:
            continue
        origin = str(row["evidence_origin"])
        origins.add(origin)
        valid_rows.append((chapter, row))

    if len(origins) != 1:
        return {}

    by_chapter: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for chapter, row in valid_rows:
        by_chapter[chapter].append(row)

    priors: dict[int, float] = {}
    for chapter in PLACEMENT_CHAPTERS:
        chapter_rows = by_chapter.get(chapter, [])
        item_ids = [str(row.get("item_id") or "") for row in chapter_rows]
        if (
            len(chapter_rows) != questions_per_chapter
            or any(not item_id for item_id in item_ids)
            or len(set(item_ids)) != questions_per_chapter
        ):
            continue
        correct = sum(1 for row in chapter_rows if row["correct"])
        n = len(chapter_rows)
        raw_score = correct / n
        weight = n / (n + shrinkage_k)
        priors[chapter] = (
            weight * raw_score
            + (1.0 - weight) * params.initial_mastery
        )
    return priors


def _load_completed_placement_rows(db: Any, student_id: str) -> list[dict[str, Any]]:
    """Load only completed, provenance-complete placement response facts."""
    try:
        rows = db.execute(
            """
            SELECT r.student_id, r.word_id, r.item_id, r.correct,
                   r.evidence_origin, r.resolver_version,
                   r.diagnostic_exposure_id, r.bkt_eligible,
                   r.activity_type, s.lesson_number AS chapter
            FROM vocab_quiz_responses AS r
            JOIN placement_test_attempts AS a
              ON a.id = r.attempt_id
             AND a.student_id = r.student_id
             AND a.status = 'completed'
            LEFT JOIN custom_stories AS s ON s.id = r.lesson_id
            WHERE r.student_id = %s
              AND r.bkt_eligible = TRUE
              AND r.activity_type = 'diagnostic'
              AND r.diagnostic_exposure_id LIKE 'placement:%%'
              AND r.resolver_version = ANY(%s)
            ORDER BY r.occurred_at_utc ASC NULLS LAST, r.id ASC
            """,
            (student_id, list(PLACEMENT_RESOLVER_VERSIONS)),
        ).fetchall()
    except Exception:
        # Placement is optional learner context.  A missing or malformed
        # placement projection must never make vocabulary mastery unavailable.
        return []
    return [dict(row) for row in rows]


def get_student_chapter_placement_priors(
    db: Any, student_id: str, params: BktConfig = BKT_CONFIG,
) -> dict[int, float]:
    """Resolve the student's usable placement prior by canonical chapter."""
    return compute_chapter_placement_priors(
        _load_completed_placement_rows(db, student_id),
        params,
    )


def _normalize_word(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).strip().split())


def _story_word_ids(story: Mapping[str, Any]) -> set[str]:
    """Return canonical word ids represented by one published story."""
    assessment_word_ids = {
        _normalize_word(item.get("targetWord")): str(item["wordId"])
        for item in (story.get("vocab_assessment") or [])
        if isinstance(item, dict) and item.get("targetWord") and item.get("wordId")
    }
    word_ids: set[str] = set(assessment_word_ids.values())

    def add_words(raw_words: Any) -> None:
        if not isinstance(raw_words, str):
            return
        for word in raw_words.split(","):
            normalized = _normalize_word(word)
            if normalized:
                word_ids.add(assessment_word_ids.get(normalized, normalized))

    for frame in story.get("frames") or []:
        if isinstance(frame, dict):
            add_words(frame.get("vocabulary"))
    story_vocabulary = story.get("story_vocabulary") or {}
    if isinstance(story_vocabulary, Mapping):
        for tier_content in story_vocabulary.values():
            if isinstance(tier_content, dict):
                add_words(tier_content.get("vocabulary"))
    return word_ids


def get_published_word_chapters(db: Any, word_ids: Iterable[str]) -> dict[str, int]:
    """Map unambiguous published vocabulary ids to canonical chapter numbers."""
    requested = {_normalize_word(word_id) for word_id in word_ids if word_id}
    if not requested:
        return {}
    try:
        stories = db.execute(
            """
            SELECT id, lesson_number, frames, story_vocabulary, vocab_assessment
            FROM custom_stories
            WHERE published = TRUE
            """
        ).fetchall()
    except Exception:
        return {}

    candidates: dict[str, set[int]] = defaultdict(set)
    for story in stories:
        chapter = _chapter_number(story.get("lesson_number"))
        if chapter is None:
            continue
        for word_id in _story_word_ids(story):
            normalized = _normalize_word(word_id)
            if normalized in requested:
                candidates[normalized].add(chapter)
    return {
        word_id: next(iter(chapters))
        for word_id, chapters in candidates.items()
        if len(chapters) == 1
    }


def initial_priors_by_word(
    db: Any,
    student_id: str,
    word_chapters: Mapping[str, Any],
    params: BktConfig = BKT_CONFIG,
) -> dict[str, float]:
    """Return chapter-derived initial priors, omitting unmapped words."""
    chapter_priors = get_student_chapter_placement_priors(db, student_id, params)
    return {
        word_id: chapter_priors[chapter]
        for word_id, chapter_value in word_chapters.items()
        if (chapter := _chapter_number(chapter_value)) in chapter_priors
    }
