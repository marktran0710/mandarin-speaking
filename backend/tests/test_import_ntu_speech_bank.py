from pathlib import Path

from benchmarking.import_ntu_speech_bank import build_manifest, write_manifest


def test_importer_creates_unlabelled_auditable_manifest(tmp_path: Path):
    audio_dir = tmp_path / "French learners" / "Beginner level" / "Speaker 3"
    audio_dir.mkdir(parents=True)
    (audio_dir / "sample.wav").write_bytes(b"RIFF")
    rows = build_manifest(tmp_path)
    assert len(rows) == 1
    assert rows[0]["speaker_id"] == "3"
    assert rows[0]["learner_l1"] == "french"
    assert rows[0]["tone_label_status"] == "needs_annotation"
    assert rows[0]["phone_boundary_status"] == "needs_annotation"
    output = tmp_path / "manifest.csv"
    write_manifest(rows, output)
    assert output.exists()


def test_sidecar_can_select_verified_public_passage(tmp_path: Path):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "S1_Sarah Wright.m4a").write_bytes(b"audio")
    sidecar = tmp_path / "sidecar.csv"
    sidecar.write_text(
        "audio_path,speaker_id,learner_l1,level,transcript_key\n"
        "S1_Sarah Wright.m4a,S1,american,beginner,beginner\n",
        encoding="utf-8",
    )
    catalog = Path(__file__).parents[1] / "benchmarking" / "ntu_transcript_catalog.json"
    rows = build_manifest(audio_dir, sidecar, catalog)
    assert rows[0]["level"] == "beginner"
    assert rows[0]["learner_l1"] == "american"
    assert rows[0]["transcript"].startswith("他們都很忙。")
