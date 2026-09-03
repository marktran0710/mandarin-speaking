import csv
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_stories_from_csv.py"
SPEC = importlib.util.spec_from_file_location("update_stories_from_csv", SCRIPT)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


def test_update_preserves_existing_metadata_and_writes_bom_export(tmp_path):
    source = tmp_path / "source.csv"
    fixture = tmp_path / "stories.json"
    export = tmp_path / "stories.csv"
    fieldnames = [
        "lesson_number", "lesson_sub_order", "story_id", "story_title",
        "published", "learning_goal", "narrative_mode", "linear",
        "first_frame_is_example", "frame_index", "frame_json",
    ]
    rows = []
    materials = []
    for lesson_number, lesson_sub_order in sorted(updater.TARGET_LESSONS):
        story_id = f"story-{lesson_number}-{lesson_sub_order}"
        rows.append({
            "lesson_number": str(lesson_number),
            "lesson_sub_order": str(lesson_sub_order),
            "story_id": story_id,
            "story_title": f"Updated {story_id}",
            "published": "True",
            "learning_goal": "ignored CSV goal",
            "narrative_mode": "ignored CSV mode",
            "linear": "True",
            "first_frame_is_example": "True",
            "frame_index": "0",
            "frame_json": json.dumps({"prompt": f"new {story_id}"}),
        })
        materials.append({
            "id": story_id,
            "title": "Old title",
            "frames": [{"prompt": "old"}],
            "published": False,
            "lesson_number": lesson_number,
            "lesson_sub_order": lesson_sub_order,
            "learning_goal": "preserved goal",
            "created_at": "2024-01-01T00:00:00Z",
            "narrative_mode": "preserved mode",
            "linear": True,
            "first_frame_is_example": True,
            "quiz_material_snapshot": {"keep": True},
        })
    untouched = {"id": "untouched", "title": "Keep", "frames": [], "published": False}
    materials.append(untouched)
    fixture.write_text(json.dumps(materials), encoding="utf-8")
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    updater.update_fixture(source, fixture)
    updater.update_export(source, export)

    updated = json.loads(fixture.read_text(encoding="utf-8"))
    first = updated[0]
    assert first["title"] == "Updated story-5-1"
    assert first["frames"] == [{"prompt": "new story-5-1"}]
    assert first["published"] is True
    assert first["created_at"] == "2024-01-01T00:00:00Z"
    assert first["quiz_material_snapshot"] == {"keep": True}
    assert set(updater.OMITTED_FIXTURE_FIELDS).isdisjoint(first)
    assert updated[-1] == untouched
    assert export.read_bytes().startswith(b"\xef\xbb\xbf")
    with export.open(encoding="utf-8-sig", newline="") as handle:
        exported = csv.DictReader(handle)
        assert set(updater.OMITTED_EXPORT_COLUMNS).isdisjoint(exported.fieldnames)
        assert list(exported) == [
            {field: row[field] for field in exported.fieldnames}
            for row in rows
        ]
