"""Guard the NTU public-text catalog against encoding/label regressions."""

import json
from pathlib import Path


CATALOG = Path(__file__).parents[1] / "benchmarking" / "ntu_transcript_catalog.json"


def test_catalog_is_utf8_and_contains_both_public_passages():
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert payload["encoding"] == "UTF-8"
    assert set(payload["texts"]) == {"beginner", "intermediate"}
    assert payload["texts"]["beginner"].startswith("他們都很忙。")
    assert payload["texts"]["beginner"].endswith("一張床。")
    assert payload["texts"]["intermediate"].startswith("今天早上我有一節聽力課。")
    assert payload["texts"]["intermediate"].endswith("今天肯定不會遲到了。")


def test_catalog_warns_against_flattened_filename_inference():
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    note = payload["note"].lower()
    assert "flattened" in note
    assert "must come from an explicit sidecar" in note
