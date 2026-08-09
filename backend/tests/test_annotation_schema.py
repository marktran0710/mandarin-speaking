from benchmarking.annotation_schema import (
    ANNOTATION_COLUMNS,
    blank_annotation_row,
    validate_annotation_row,
)


def test_blank_row_is_complete_and_safe_for_import():
    row = blank_annotation_row({"speaker_id": "s1", "expected_tone": "T3"})
    assert tuple(row) == ANNOTATION_COLUMNS
    assert row["row_type"] == "audio"
    assert row["audio_qc_status"] == "needs_review"
    assert validate_annotation_row(row) == []


def test_t5_and_unknown_are_not_collapsed():
    row = blank_annotation_row({"expected_tone": "T5", "detected_tone": "Unknown"})
    errors = validate_annotation_row(row)
    assert any("T5 and Unknown" in error for error in errors)


def test_gold_phone_requires_boundaries_and_labels():
    row = blank_annotation_row({
        "row_type": "phone",
        "speaker_id": "s1",
        "expected_tone": "T1",
        "produced_tone": "T1",
        "correct_incorrect": "correct",
        "dataset_split": "sealed_test",
        "is_sealed_test": True,
        "audio_qc_status": "usable",
        "audio_qc_expected_usable": True,
        "phone_expected": "sh",
    })
    errors = validate_annotation_row(row, require_gold=True)
    assert "phone_start_ms is required for gold phone rows" in errors
    assert "phone_end_ms is required for gold phone rows" in errors
