"""Canonical Taiwan Mandarin pinyin conversion for all backend consumers."""

from typing import List, Tuple

from pypinyin import Style, lazy_pinyin, pinyin

import taiwan_pinyin


# Importing this module is safe in isolation (for tests and scripts) and in
# the FastAPI process, where main.py also applies the same idempotent map.
taiwan_pinyin.apply()


def canonical_pinyin(text: str) -> str:
    """Return tone-marked Taiwan Mandarin pinyin for a phrase."""
    value = (text or "").strip()
    if not value:
        return ""
    return " ".join(
        lazy_pinyin(value, style=Style.TONE, neutral_tone_with_five=False)
    )


def canonical_pinyin_tone3(text: str) -> str:
    """Return the same canonical reading with numeric tone marks."""
    value = (text or "").strip()
    if not value:
        return ""
    return " ".join(
        lazy_pinyin(value, style=Style.TONE3, neutral_tone_with_five=True)
    )


def canonical_syllable_parts(text: str) -> List[Tuple[str, str]]:
    """Return canonical initial/final pairs for tone diagnostics."""
    value = (text or "").strip()
    if not value:
        return []

    initials = pinyin(value, style=Style.INITIALS, strict=True)
    finals = pinyin(value, style=Style.FINALS, strict=True)
    parts: List[Tuple[str, str]] = []
    for index in range(len(finals)):
        initial = initials[index][0] if index < len(initials) else ""
        final = finals[index][0] if index < len(finals) else ""
        parts.append((initial, final))
    return parts
