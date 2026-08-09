import csv
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pronunciation.wav2vec_tone.audit_t3_sandhi import (  # noqa: E402
    SealedTestViolation,
    audit_t3_sandhi,
    load_metadata,
    load_predictions,
    load_train_dev_split_map,
    write_artifacts,
)


def _write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_t3_audit_flags_t3_plus_t3_without_rewriting_gold(tmp_path):
    cache = tmp_path / "train_dev.npz"
    np.savez(cache, token_ids=np.asarray(["u_00", "u_01", "u_02"]),
             split=np.asarray(["train", "train", "dev"]))
    metadata_path = tmp_path / "metadata.csv"
    metadata_fields = [
        "utterance_id", "token_index", "speaker_id", "expected_tone",
        "alignment_success", "alignment_status_detail", "praat_flags",
    ]
    _write_csv(metadata_path, metadata_fields, [
        {"utterance_id": "u", "token_index": "0", "speaker_id": "s1", "expected_tone": "3",
         "alignment_success": "1", "alignment_status_detail": "ok", "praat_flags": ""},
        {"utterance_id": "u", "token_index": "1", "speaker_id": "s1", "expected_tone": "3",
         "alignment_success": "1", "alignment_status_detail": "ok", "praat_flags": "weak_voicing"},
        {"utterance_id": "u", "token_index": "2", "speaker_id": "s1", "expected_tone": "1",
         "alignment_success": "0", "alignment_status_detail": "failed", "praat_flags": ""},
    ])
    prediction_path = tmp_path / "predictions.csv"
    _write_csv(prediction_path, ["token_id", "produced_tone_proxy", "predicted_tone"], [
        {"token_id": "u_00", "produced_tone_proxy": "T3", "predicted_tone": "T2"},
        {"token_id": "u_01", "produced_tone_proxy": "T3", "predicted_tone": "T1"},
        {"token_id": "u_02", "produced_tone_proxy": "T1", "predicted_tone": "T1"},
    ])

    split_map = load_train_dev_split_map(cache)
    metadata, columns = load_metadata(metadata_path, split_map)
    report = audit_t3_sandhi(metadata, load_predictions(prediction_path, metadata), columns)

    assert report["protocol"]["sealed_test_accessed"] is False
    assert report["t3_summary"]["mapping"] == {"T3_to_T1": 1, "T3_to_T2": 1}
    first = report["rows"][0]
    assert first["sandhi_context"] == "T3_plus_T3"
    assert first["sandhi_interpretation"] == "possible_surface_T2_not_gold_override"
    assert first["lexical_target"] == "T3"
    assert first["surface_label_status"] == "needs_data_no_surface_label"
    assert report["rows"][1]["pitch_flag_status"] == "pitch_flagged"
    assert "needs_data_no_surface_label" in report["t3_summary"]["needs_data"]

    paths = write_artifacts(report, tmp_path / "t3_audit")
    assert all(path.is_file() for path in paths)


def test_t3_audit_rejects_a_split_cache_that_contains_sealed_test(tmp_path):
    cache = tmp_path / "train_dev.npz"
    np.savez(cache, token_ids=np.asarray(["a", "b"]), split=np.asarray(["train", "test"]))

    with pytest.raises(SealedTestViolation, match="TEST LOCK VIOLATION"):
        load_train_dev_split_map(cache)


def test_t3_audit_refuses_prediction_missing_from_train_dev_metadata(tmp_path):
    cache = tmp_path / "train_dev.npz"
    np.savez(cache, token_ids=np.asarray(["u_00"]), split=np.asarray(["train"]))
    metadata_path = tmp_path / "metadata.csv"
    _write_csv(metadata_path, ["utterance_id", "token_index", "speaker_id", "expected_tone"], [
        {"utterance_id": "u", "token_index": "0", "speaker_id": "s1", "expected_tone": "3"},
    ])
    predictions_path = tmp_path / "predictions.csv"
    _write_csv(predictions_path, ["token_id", "predicted_tone"], [
        {"token_id": "not_train_dev", "predicted_tone": "T3"},
    ])

    metadata, _ = load_metadata(metadata_path, load_train_dev_split_map(cache))
    with pytest.raises(ValueError, match="absent from Train/Dev metadata"):
        load_predictions(predictions_path, metadata)


def test_t3_audit_rejects_explicit_sealed_metadata_rows(tmp_path):
    cache = tmp_path / "train_dev.npz"
    np.savez(cache, token_ids=np.asarray(["u_00"]), split=np.asarray(["train"]))
    metadata_path = tmp_path / "metadata.csv"
    _write_csv(metadata_path, ["token_id", "split", "expected_tone"], [
        {"token_id": "u_00", "split": "test", "expected_tone": "3"},
    ])

    with pytest.raises(SealedTestViolation, match="TEST LOCK VIOLATION"):
        load_metadata(metadata_path, load_train_dev_split_map(cache))
