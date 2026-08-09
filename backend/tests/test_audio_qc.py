from pathlib import Path

import soundfile as sf

from benchmarking.audio_qc import scan, write_report


def test_audio_qc_decodes_and_detects_duplicate(tmp_path: Path):
    root = tmp_path / "audio"
    root.mkdir()
    samples = [0.1, -0.1, 0.0, 0.05] * 4000
    sf.write(root / "S1.wav", samples, 16000)
    (root / "S1-copy.wav").write_bytes((root / "S1.wav").read_bytes())

    report = scan(root)

    assert report["file_count"] == 2
    assert report["decoded_count"] == 2
    assert report["duplicate_group_count"] == 1
    assert all("duplicate_content" in row["qc_reasons"] for row in report["rows"])


def test_audio_qc_writes_json_and_csv(tmp_path: Path):
    root = tmp_path / "audio"
    root.mkdir()
    sf.write(root / "S2.wav", [0.0] * 8000, 16000)
    output = tmp_path / "reports" / "qc.json"

    write_report(scan(root), output)

    assert output.exists()
    assert output.with_suffix(".csv").exists()
