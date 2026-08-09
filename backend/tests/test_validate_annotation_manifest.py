from pathlib import Path

from scripts.validate_annotation_manifest import main


def test_manifest_validator_accepts_importer_rows(tmp_path: Path):
    path = tmp_path / "manifest.csv"
    path.write_text("speaker_id,expected_tone\ns1,T1\n", encoding="utf-8")
    assert main([str(path)]) == 0


def test_manifest_validator_reports_incomplete_gold_rows(tmp_path: Path):
    path = tmp_path / "manifest.csv"
    path.write_text("speaker_id,expected_tone\ns1,T1\n", encoding="utf-8")
    assert main([str(path), "--require-gold"]) == 1
