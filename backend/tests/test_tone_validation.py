import csv
import math
import struct
import wave

import pytest

from benchmarking.tone_validation import (
    ToneBenchmarkRow,
    build_evaluation_report,
    load_benchmark_csv,
    speaker_disjoint_split,
)
from scripts.benchmark_tones import initialize_benchmark_workspace, score_audio_manifest


def _row(recording_id, speaker_id, tone, human_label, system_score, detected_tone=None, human_score=None):
    return ToneBenchmarkRow(
        recording_id=recording_id,
        speaker_id=speaker_id,
        expected_tone=tone,
        human_label=human_label,
        system_score=system_score,
        detected_tone=detected_tone,
        human_score=human_score,
    )


def test_report_calculates_pass_fail_metrics_by_tone_and_audit_rows():
    rows = [
        _row("r1", "s1", 1, True, 90, 1, 95),   # TP
        _row("r2", "s2", 1, False, 20, 2, 15),  # TN
        _row("r3", "s3", 2, False, 80, 2, 25),  # FP
        _row("r4", "s4", 2, True, 30, 4, 80),   # FN
    ]

    report = build_evaluation_report(rows, threshold=70)

    assert report["pass_fail_agreement"] == {
        "n": 4,
        "true_positive": 1,
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 1,
        "accuracy": 0.5,
        "precision": 0.5,
        "recall": 0.5,
        # Recall's counterpart on the negative class: of the 2 items the human
        # marked incorrect, 1 was also failed by the system.
        "specificity": 0.5,
        "balanced_accuracy": 0.5,
        "f1": 0.5,
        "cohen_kappa": 0.0,
        "matthews_correlation": 0.0,
        # Each rate carries the denominator it was divided by, so it can never
        # be quoted against the wrong base.
        "false_acceptance_count": 1,
        "false_acceptance_rate": 0.5,
        "false_acceptance_denominator": 2,
        "false_rejection_count": 1,
        "false_rejection_rate": 0.5,
        "false_rejection_denominator": 2,
    }
    assert report["by_expected_tone"]["1"]["accuracy"] == 1.0
    assert report["by_expected_tone"]["2"]["accuracy"] == 0.0
    assert report["tone_detection"]["accuracy"] == 0.5
    assert report["score_agreement"]["mean_absolute_error"] == pytest.approx(28.75)
    assert report["audit"]["disagreement_count"] == 2
    assert {entry["recording_id"] for entry in report["audit"]["disagreements"]} == {"r3", "r4"}


def test_speaker_disjoint_split_is_deterministic_and_never_leaks_a_speaker():
    rows = [
        _row(f"r{speaker}-{attempt}", f"speaker-{speaker}", 1, True, 90)
        for speaker in range(6)
        for attempt in range(2)
    ]

    first = speaker_disjoint_split(rows, seed=7)
    second = speaker_disjoint_split(rows, seed=7)

    assert first == second
    split_speakers = {
        name: {row.speaker_id for row in split_rows}
        for name, split_rows in first.items()
    }
    assert split_speakers["train"].isdisjoint(split_speakers["dev"])
    assert split_speakers["train"].isdisjoint(split_speakers["test"])
    assert split_speakers["dev"].isdisjoint(split_speakers["test"])
    assert all(first.values())


def test_load_benchmark_csv_rejects_duplicate_recordings_and_bad_schema(tmp_path):
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=["recording_id", "speaker_id", "expected_tone", "human_label", "system_score"],
        )
        writer.writeheader()
        writer.writerow({"recording_id": "r1", "speaker_id": "s1", "expected_tone": 1, "human_label": "pass", "system_score": 90})
        writer.writerow({"recording_id": "r1", "speaker_id": "s2", "expected_tone": 2, "human_label": "fail", "system_score": 20})

    with pytest.raises(ValueError, match="duplicate recording_id"):
        load_benchmark_csv(path)


def test_score_audio_manifest_runs_praat_and_separates_data_errors(tmp_path):
    audio_path = tmp_path / "rising.wav"
    sample_rate = 16_000
    duration = 0.8
    phase = 0.0
    frames = []
    for index in range(int(sample_rate * duration)):
        progress = index / (sample_rate * duration)
        frequency = 150.0 + 80.0 * progress
        phase += 2.0 * math.pi * frequency / sample_rate
        frames.append(struct.pack("<h", int(12_000 * math.sin(phase))))
    with wave.open(str(audio_path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(b"".join(frames))

    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=["recording_id", "speaker_id", "audio_path", "expected_tone", "human_label"],
        )
        writer.writeheader()
        writer.writerow({
            "recording_id": "valid-1", "speaker_id": "speaker-1",
            "audio_path": "rising.wav", "expected_tone": 2, "human_label": "pass",
        })
        writer.writerow({
            "recording_id": "missing-1", "speaker_id": "speaker-2",
            "audio_path": "missing.wav", "expected_tone": 4, "human_label": "fail",
        })

    scored_path = tmp_path / "scored.csv"
    errors_path = tmp_path / "errors.csv"
    scored_count, error_count = score_audio_manifest(manifest, scored_path, errors_path)

    assert (scored_count, error_count) == (1, 1)
    scored_rows = list(csv.DictReader(scored_path.open(encoding="utf-8")))
    assert scored_rows[0]["recording_id"] == "valid-1"
    assert 0 <= float(scored_rows[0]["system_score"]) <= 100
    assert int(scored_rows[0]["pitch_frame_count"]) >= 4
    error_rows = list(csv.DictReader(errors_path.open(encoding="utf-8")))
    assert error_rows[0]["recording_id"] == "missing-1"
    assert "not found" in error_rows[0]["error"]


def test_initialize_workspace_creates_template_without_overwriting_it(tmp_path):
    manifest, created = initialize_benchmark_workspace(tmp_path / "private-data")
    assert created is True
    assert (manifest.parent / "audio").is_dir()
    assert manifest.read_text(encoding="utf-8").strip() == (
        "recording_id,speaker_id,audio_path,expected_tone,human_label,human_score"
    )

    manifest.write_text(manifest.read_text(encoding="utf-8") + "keep,this,row,1,pass,90\n")
    same_manifest, created_again = initialize_benchmark_workspace(tmp_path / "private-data")
    assert same_manifest == manifest
    assert created_again is False
    assert "keep,this,row" in manifest.read_text(encoding="utf-8")
