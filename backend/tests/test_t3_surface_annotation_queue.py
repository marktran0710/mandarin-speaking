import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pronunciation.wav2vec_tone.prepare_t3_surface_annotation_queue import (  # noqa: E402
    SealedPartitionViolation,
    load_explicit_train_metadata,
    load_train_fusion_oof,
    prepare_queue,
    write_artifacts,
)


def _write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _prediction(token_id, target, predicted, scores, **extra):
    return {
        "token_id": token_id,
        "produced_tone_proxy": target,
        "predicted_tone": predicted,
        "nested_selected_candidate": "fusion;C=0.03",
        "score_type": "uncalibrated_linear_svm_margin",
        **{f"decision_score_T{tone}": str(scores[tone - 1]) for tone in range(1, 5)},
        **extra,
    }


def test_train_t3_queue_prioritizes_errors_context_and_margin_without_gold_promotion(tmp_path):
    prediction_path = tmp_path / "fusion_train_oof.csv"
    fields = list(_prediction("u_00", "T3", "T2", [-1.0, 0.3, 0.2, -0.4]))
    _write_csv(prediction_path, fields, [
        _prediction("u_00", "T3", "T2", [-1.0, 0.3, 0.2, -0.4]),
        _prediction("u_01", "T3", "T3", [-1.0, 0.1, 0.11, -0.5]),
        _prediction("u_02", "T1", "T1", [0.9, 0.1, -0.2, -0.3]),
    ])
    metadata_path = tmp_path / "train_metadata.csv"
    _write_csv(metadata_path, [
        "token_id", "split", "speaker_id", "utterance_id", "token_index", "expected_tone",
        "source_utterance_path", "alignment_success", "alignment_status_detail", "praat_flags",
    ], [
        {"token_id": "u_00", "split": "train", "speaker_id": "s1", "utterance_id": "u", "token_index": "0",
         "expected_tone": "3", "source_utterance_path": "private-data/ompal/wav/SPEAKERs1/u.wav",
         "alignment_success": "1", "alignment_status_detail": "ok", "praat_flags": ""},
        {"token_id": "u_01", "split": "train", "speaker_id": "s1", "utterance_id": "u", "token_index": "1",
         "expected_tone": "3", "source_utterance_path": "private-data/ompal/wav/SPEAKERs1/u.wav",
         "alignment_success": "1", "alignment_status_detail": "ok", "praat_flags": "weak_voicing"},
        {"token_id": "u_02", "split": "train", "speaker_id": "s1", "utterance_id": "u", "token_index": "2",
         "expected_tone": "1", "source_utterance_path": "private-data/ompal/wav/SPEAKERs1/u.wav",
         "alignment_success": "1", "alignment_status_detail": "ok", "praat_flags": ""},
    ])

    predictions = load_train_fusion_oof(prediction_path)
    metadata, columns = load_explicit_train_metadata(metadata_path)
    report = prepare_queue(predictions, metadata, columns, low_margin_quantile=0.5)

    assert report["protocol"]["sealed_test_accessed"] is False
    assert report["queue_summary"]["reason_counts"]["T3_error"] == 1
    first = report["rows"][0]
    assert first["token_id"] == "u_00"
    assert "T3_error" in first["queue_reasons"]
    assert "T3_plus_T3_context" in first["queue_reasons"]
    assert first["token_audio_path"] == "benchmark_token_segments/u_00.wav"
    assert first["gold_status"] == "not_gold"
    assert first["auto_promotion_prohibited"] is True
    assert first["human_perceived_tone"] == ""
    assert first["pitch_provenance"] == "praat_flags="

    paths = write_artifacts(report, tmp_path / "queue")
    assert all(path.is_file() for path in paths)
    assert "preannotation" in paths[2].read_text(encoding="utf-8")


def test_queue_rejects_dev_or_test_inputs(tmp_path):
    prediction_path = tmp_path / "fusion_oof.csv"
    fields = list(_prediction("u_00", "T3", "T2", [-1.0, 0.2, 0.1, -0.4], split="dev"))
    _write_csv(prediction_path, fields, [
        _prediction("u_00", "T3", "T2", [-1.0, 0.2, 0.1, -0.4], split="dev"),
    ])
    with pytest.raises(SealedPartitionViolation, match="TRAIN-ONLY LOCK VIOLATION"):
        load_train_fusion_oof(prediction_path)

    metadata_path = tmp_path / "metadata.csv"
    _write_csv(metadata_path, ["token_id", "split"], [{"token_id": "u_00", "split": "test"}])
    with pytest.raises(SealedPartitionViolation, match="TRAIN-ONLY LOCK VIOLATION"):
        load_explicit_train_metadata(metadata_path)


def test_queue_marks_missing_metadata_as_needs_data_not_inferred():
    report = prepare_queue([
        _prediction("u_00", "T3", "T2", [-1.0, 0.2, 0.1, -0.4]),
    ], low_margin_quantile=1.0)

    row = report["rows"][0]
    assert row["context_status"] == "needs_data_train_metadata_not_supplied"
    assert row["source_audio_status"] == "needs_data_train_metadata_not_supplied"
    assert row["sandhi_context"] == "needs_data_train_metadata_not_supplied"


def test_queue_accepts_nucleus_candidate_provenance_field():
    prediction = _prediction("u_00", "T3", "T2", [-1.0, 0.2, 0.1, -0.4])
    prediction.pop("nested_selected_candidate")
    prediction["selected_candidate"] = "fusion_plus_voiced_nucleus"

    report = prepare_queue([prediction], low_margin_quantile=1.0)

    assert report["rows"][0]["model_candidate"] == "fusion_plus_voiced_nucleus"
