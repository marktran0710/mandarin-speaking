import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_verified_quiz_questions.py"
SPEC = importlib.util.spec_from_file_location("import_verified_quiz_questions", SCRIPT)
assert SPEC and SPEC.loader
importer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(importer)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "questions_verified_v3_book_locked.csv"
FIXTURE = ROOT / "backend" / "scripts" / "data" / "custom_stories.json"


def test_locked_export_is_complete_and_matches_fixture():
    rows = importer.read_verified_questions(SOURCE)
    snapshots = importer.build_approved_snapshots(rows)

    assert len(rows) == 3474
    assert len(snapshots) == 12
    assert {row["validation_status"] for row in rows} == {"ok"}
    assert {row["source"] for row in rows} == {"verified_v3_book_locked"}
    assert {row["tier"] for row in rows} == set(importer.TIERS)
    assert {row["question_type"] for row in rows} == importer.QUESTION_TYPES

    fixture_ids = {
        story["id"]
        for story in json.loads(FIXTURE.read_text(encoding="utf-8"))
        if isinstance(story, dict)
    }
    assert set(snapshots) <= fixture_ids
    assert all(set(levels) == set(importer.TIERS) for levels in snapshots.values())
    assert all(all(entry["word"] and entry["translation"] for entry in entries)
               for levels in snapshots.values() for entries in levels.values())
    assert all(
        candidate["sentence"].count(entry["word"]) == 1
        for levels in snapshots.values()
        for entries in levels.values()
        for entry in entries
        for candidate in entry["cloze"]
    )


def test_seed_fixture_keeps_verified_bank_unpublished():
    stories = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_ids = {
        row["story_id"]
        for row in importer.read_verified_questions(SOURCE)
    }
    assert all(
        story.get("quiz_approved_snapshot") is None
        for story in stories
        if story.get("id") in source_ids
    )


def test_publish_fixture_only_changes_approved_snapshot(tmp_path):
    fixture = tmp_path / "custom_stories.json"
    fixture.write_text(json.dumps([
        {"id": story_id, "title": "Fixture", "frames": [], "quiz_material_snapshot": {"keep": True}}
        for story_id in sorted(importer.build_approved_snapshots(importer.read_verified_questions(SOURCE)))
    ]), encoding="utf-8")

    rows_written, stories_written = importer.publish_fixture(SOURCE, fixture)
    updated = json.loads(fixture.read_text(encoding="utf-8"))

    assert (rows_written, stories_written) == (3474, 12)
    assert all(story["quiz_material_snapshot"] == {"keep": True} for story in updated)
    assert all(set(story["quiz_approved_snapshot"]) == set(importer.TIERS) for story in updated)
