from __future__ import annotations

import pytest

from scripts.seed_quiz_assessments import BANKS, _parts, find_story_for_part


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return self.rows


def test_catalog_covers_only_the_requested_lesson5_parts():
    assert tuple(BANKS) == ("5-2", "5-3")
    assert [path.name for path in BANKS.values()] == [
        "l5-2-vocab-assessment.csv",
        "l5-3-vocab-assessment.csv",
    ]
    assert _parts(None) == ["5-2", "5-3"]
    assert _parts("5-3") == ["5-3"]


def test_story_resolution_requires_one_existing_lesson_part_story():
    db = _FakeCursor([{"id": "story-5-2", "title": "Wallet"}])

    assert find_story_for_part(db, "5-2") == {"id": "story-5-2", "title": "Wallet"}
    assert db.calls[0][1] == (5, 2)

    with pytest.raises(LookupError, match="No existing story"):
        find_story_for_part(_FakeCursor([]), "5-3")
    with pytest.raises(LookupError, match="multiple stories"):
        find_story_for_part(_FakeCursor([{"id": "a"}, {"id": "b"}]), "5-2")
