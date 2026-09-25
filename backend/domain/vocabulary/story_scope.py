"""Canonical identifiers for one story's vocabulary-learning scope."""

from __future__ import annotations


def canonical_story_id(story_id: str | None) -> str | None:
    """Return the source story id behind teacher/topic and legacy tier ids."""
    if not story_id:
        return None
    value = str(story_id).strip()
    if value.startswith("teacher-"):
        value = value[len("teacher-"):]
    for suffix in ("-medium", "-hard"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value or None


def story_scope_ids(story_id: str | None) -> list[str]:
    """All current and legacy ids that represent one story's learning scope."""
    if not story_id:
        return []
    canonical = canonical_story_id(story_id)
    if not canonical:
        return [str(story_id)]
    return sorted({
        str(story_id),
        canonical,
        f"teacher-{canonical}",
        f"teacher-{canonical}-medium",
        f"teacher-{canonical}-hard",
    })
