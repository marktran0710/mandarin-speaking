# Unified KPI dashboard

- Status: **NEEDS_DATA**
- Release status: **EXPERIMENTAL**
- Failed metrics: human_usable_boundaries, phone_gold_count, audio_qc_reviewed_count, audio_qc_unusable_count
- Missing data: model_version, schema_version, sealed_test_set, phone_boundary_within_30ms, phone_f1, phone_group_min_f1, tone_accuracy, tone_macro_f1, detection_coverage, unknown_rate, correct_balanced_accuracy, correct_sensitivity, correct_specificity, audio_qc_auc, audio_qc_retention, audio_qc_unusable_recall, high_confidence_precision, calibration_ece, speaker_min_balanced_accuracy, t1_precision, t1_recall, t1_f1, t2_precision, t2_recall, t2_f1, t3_precision, t3_recall, t3_f1, t4_precision, t4_recall, t4_f1

| Metric | Actual | Threshold | Result |
|---|---:|---:|---|
| model_version | missing | = 1.0 | FAIL |
| schema_version | missing | = 1.0 | FAIL |
| sealed_test_set | missing | = 1.0 | FAIL |
| speaker_count | 45.0 | >= 40 | PASS |
| character_alignment_success | 1.0 | >= 0.95 | PASS |
| human_usable_boundaries | 0.81 | >= 0.9 | FAIL |
| phone_boundary_within_30ms | missing | >= 0.8 | FAIL |
| phone_gold_count | 0.0 | >= 300 | FAIL |
| phone_f1 | missing | >= 0.8 | FAIL |
| phone_group_min_f1 | missing | >= 0.8 | FAIL |
| tone_accuracy | missing | >= 0.8 | FAIL |
| tone_macro_f1 | missing | >= 0.8 | FAIL |
| detection_coverage | missing | >= 0.8 | FAIL |
| unknown_rate | missing | <= 0.2 | FAIL |
| correct_balanced_accuracy | missing | >= 0.8 | FAIL |
| correct_sensitivity | missing | >= 0.8 | FAIL |
| correct_specificity | missing | >= 0.8 | FAIL |
| audio_qc_auc | missing | >= 0.8 | FAIL |
| audio_qc_retention | missing | >= 0.8 | FAIL |
| audio_qc_unusable_recall | missing | >= 0.8 | FAIL |
| audio_qc_reviewed_count | 0.0 | >= 300 | FAIL |
| audio_qc_unusable_count | 0.0 | >= 100 | FAIL |
| high_confidence_precision | missing | >= 0.92 | FAIL |
| calibration_ece | missing | <= 0.1 | FAIL |
| speaker_min_balanced_accuracy | missing | >= 0.7 | FAIL |
| t1_precision | missing | >= 0.8 | FAIL |
| t1_recall | missing | >= 0.8 | FAIL |
| t1_f1 | missing | >= 0.8 | FAIL |
| t1_test_support | 553.0 | >= 50 | PASS |
| t2_precision | missing | >= 0.8 | FAIL |
| t2_recall | missing | >= 0.8 | FAIL |
| t2_f1 | missing | >= 0.8 | FAIL |
| t2_test_support | 468.0 | >= 50 | PASS |
| t3_precision | missing | >= 0.8 | FAIL |
| t3_recall | missing | >= 0.8 | FAIL |
| t3_f1 | missing | >= 0.8 | FAIL |
| t3_test_support | 272.0 | >= 50 | PASS |
| t4_precision | missing | >= 0.8 | FAIL |
| t4_recall | missing | >= 0.8 | FAIL |
| t4_f1 | missing | >= 0.8 | FAIL |
| t4_test_support | 775.0 | >= 50 | PASS |
| speaker_leakage | 0.0 | <= 0 | PASS |
