import json
import subprocess
import sys

from benchmarking.leakage_guard import audit_rows


def _row(sample, speaker, split, **extra):
    return {
        "sample_id": sample,
        "speaker_id": speaker,
        "dataset_split": split,
        "source_sample_id": sample,
        **extra,
    }


def test_clean_speaker_disjoint_manifest_passes_and_is_deterministic():
    rows = [
        _row("tr-1", "speaker-tr", "train", audio_sha256="a"),
        _row("dev-1", "speaker-dev", "dev", audio_sha256="b"),
        _row("te-1", "speaker-test", "sealed_test", audio_sha256="c"),
    ]
    first = audit_rows(rows, require_sealed_test=True)
    second = audit_rows(rows, require_sealed_test=True)
    assert first.passed
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.split_counts == {"dev": 1, "sealed_test": 1, "train": 1}


def test_guard_rejects_speaker_source_and_byte_content_leakage():
    rows = [
        _row("train", "speaker-a", "train", source_sample_id="original", audio_sha256="same"),
        _row("test", "speaker-a", "sealed_test", source_sample_id="original", audio_sha256="same"),
    ]
    audit = audit_rows(rows, require_sealed_test=True)
    assert not audit.passed
    assert any("speaker leakage" in error for error in audit.errors)
    assert any("source-group leakage" in error for error in audit.errors)
    assert any("audio-content leakage" in error for error in audit.errors)


def test_augmentation_is_train_only_and_duplicate_ids_fail():
    rows = [
        _row("copy", "speaker-a", "train", augmentation_recipe="noise_snr_20"),
        _row("copy", "speaker-b", "sealed_test", augmentation_recipe="noise_snr_20"),
    ]
    audit = audit_rows(rows)
    assert not audit.passed
    assert any("augmentation is allowed only" in error for error in audit.errors)
    assert any("duplicate sample id" in error for error in audit.errors)


def test_cli_writes_auditable_json(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("\n".join(json.dumps(row) for row in [
        _row("tr", "a", "train"),
        _row("test", "b", "sealed_test"),
    ]) + "\n", encoding="utf-8")
    output = tmp_path / "audit.json"
    result = subprocess.run(
        [sys.executable, "backend/scripts/audit_benchmark_leakage.py", str(manifest),
         "--require-sealed-test", "--output", str(output), "--json"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is True
