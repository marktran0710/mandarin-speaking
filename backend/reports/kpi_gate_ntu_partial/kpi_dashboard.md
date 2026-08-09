# Unified KPI dashboard

- Status: **NEEDS_DATA**
- Release status: **EXPERIMENTAL**
- Failed metrics: speaker_count, character_alignment_success, human_usable_boundaries, phone_gold_count, tone_macro_f1, correct_balanced_accuracy, correct_sensitivity, audio_qc_reviewed_count, audio_qc_unusable_count, speaker_min_balanced_accuracy, t1_precision, t1_recall, t1_f1, t1_test_support, t2_precision, t2_recall, t2_f1, t2_test_support, t3_precision, t3_recall, t3_f1, t3_test_support, t4_precision, t4_recall, t4_f1, t4_test_support, t5_precision, t5_recall, t5_f1, t5_test_support
- Missing data: phone_boundary_within_30ms, tone_accuracy, detection_coverage, unknown_rate, audio_qc_auc, audio_qc_retention, audio_qc_unusable_recall, high_confidence_precision, calibration_ece, speaker_leakage

| Metric | Actual | Threshold | Result |
|---|---:|---:|---|
| model_version | 1.0 | = 1.0 | PASS |
| schema_version | 1.0 | = 1.0 | PASS |
| sealed_test_set | 1.0 | = 1.0 | PASS |
| speaker_count | 25.0 | >= 40 | FAIL |
| character_alignment_success | 0.0 | >= 0.95 | FAIL |
| human_usable_boundaries | 0.0 | >= 0.9 | FAIL |
| phone_boundary_within_30ms | missing | >= 0.8 | FAIL |
| phone_gold_count | 0.0 | >= 300 | FAIL |
| phone_f1 | 1.0 | >= 0.8 | PASS |
| phone_group_min_f1 | 1.0 | >= 0.8 | PASS |
| tone_accuracy | missing | >= 0.8 | FAIL |
| tone_macro_f1 | 0.0 | >= 0.8 | FAIL |
| detection_coverage | missing | >= 0.8 | FAIL |
| unknown_rate | missing | <= 0.2 | FAIL |
| correct_balanced_accuracy | 0.5 | >= 0.8 | FAIL |
| correct_sensitivity | 0.0 | >= 0.8 | FAIL |
| correct_specificity | 1.0 | >= 0.8 | PASS |
| audio_qc_auc | missing | >= 0.8 | FAIL |
| audio_qc_retention | missing | >= 0.8 | FAIL |
| audio_qc_unusable_recall | missing | >= 0.8 | FAIL |
| audio_qc_reviewed_count | 56.0 | >= 300 | FAIL |
| audio_qc_unusable_count | 0.0 | >= 100 | FAIL |
| high_confidence_precision | missing | >= 0.92 | FAIL |
| calibration_ece | missing | <= 0.1 | FAIL |
| speaker_min_balanced_accuracy | 0.5 | >= 0.7 | FAIL |
| t1_precision | 0.0 | >= 0.8 | FAIL |
| t1_recall | 0.0 | >= 0.8 | FAIL |
| t1_f1 | 0.0 | >= 0.8 | FAIL |
| t1_test_support | 0.0 | >= 50 | FAIL |
| t2_precision | 0.0 | >= 0.8 | FAIL |
| t2_recall | 0.0 | >= 0.8 | FAIL |
| t2_f1 | 0.0 | >= 0.8 | FAIL |
| t2_test_support | 0.0 | >= 50 | FAIL |
| t3_precision | 0.0 | >= 0.8 | FAIL |
| t3_recall | 0.0 | >= 0.8 | FAIL |
| t3_f1 | 0.0 | >= 0.8 | FAIL |
| t3_test_support | 0.0 | >= 50 | FAIL |
| t4_precision | 0.0 | >= 0.8 | FAIL |
| t4_recall | 0.0 | >= 0.8 | FAIL |
| t4_f1 | 0.0 | >= 0.8 | FAIL |
| t4_test_support | 0.0 | >= 50 | FAIL |
| t5_precision | 0.0 | >= 0.8 | FAIL |
| t5_recall | 0.0 | >= 0.8 | FAIL |
| t5_f1 | 0.0 | >= 0.8 | FAIL |
| t5_test_support | 0.0 | >= 50 | FAIL |
| speaker_leakage | missing | <= 0 | FAIL |
