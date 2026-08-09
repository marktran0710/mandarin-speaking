# Unified KPI dashboard

- Status: **NEEDS_DATA**
- Release status: **EXPERIMENTAL**
- Failed metrics: none
- Missing data: model_version, schema_version, sealed_test_set, speaker_count, character_alignment_success, human_usable_boundaries, phone_boundary_within_30ms, phone_gold_count, phone_f1, phone_group_min_f1, tone_accuracy, tone_macro_f1, detection_coverage, unknown_rate, correct_balanced_accuracy, correct_sensitivity, correct_specificity, audio_qc_auc, audio_qc_retention, audio_qc_unusable_recall, audio_qc_reviewed_count, audio_qc_unusable_count, high_confidence_precision, calibration_ece, speaker_min_balanced_accuracy, t1_precision, t1_recall, t1_f1, t1_test_support, t2_precision, t2_recall, t2_f1, t2_test_support, t3_precision, t3_recall, t3_f1, t3_test_support, t4_precision, t4_recall, t4_f1, t4_test_support, t5_precision, t5_recall, t5_f1, t5_test_support, speaker_leakage

| Metric | Actual | Threshold | Result |
|---|---:|---:|---|
| model_version | missing | = 1.0 | FAIL |
| schema_version | missing | = 1.0 | FAIL |
| sealed_test_set | missing | = 1.0 | FAIL |
| speaker_count | missing | >= 40 | FAIL |
| character_alignment_success | missing | >= 0.95 | FAIL |
| human_usable_boundaries | missing | >= 0.9 | FAIL |
| phone_boundary_within_30ms | missing | >= 0.8 | FAIL |
| phone_gold_count | missing | >= 300 | FAIL |
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
| audio_qc_reviewed_count | missing | >= 300 | FAIL |
| audio_qc_unusable_count | missing | >= 100 | FAIL |
| high_confidence_precision | missing | >= 0.92 | FAIL |
| calibration_ece | missing | <= 0.1 | FAIL |
| speaker_min_balanced_accuracy | missing | >= 0.7 | FAIL |
| t1_precision | missing | >= 0.8 | FAIL |
| t1_recall | missing | >= 0.8 | FAIL |
| t1_f1 | missing | >= 0.8 | FAIL |
| t1_test_support | missing | >= 50 | FAIL |
| t2_precision | missing | >= 0.8 | FAIL |
| t2_recall | missing | >= 0.8 | FAIL |
| t2_f1 | missing | >= 0.8 | FAIL |
| t2_test_support | missing | >= 50 | FAIL |
| t3_precision | missing | >= 0.8 | FAIL |
| t3_recall | missing | >= 0.8 | FAIL |
| t3_f1 | missing | >= 0.8 | FAIL |
| t3_test_support | missing | >= 50 | FAIL |
| t4_precision | missing | >= 0.8 | FAIL |
| t4_recall | missing | >= 0.8 | FAIL |
| t4_f1 | missing | >= 0.8 | FAIL |
| t4_test_support | missing | >= 50 | FAIL |
| t5_precision | missing | >= 0.8 | FAIL |
| t5_recall | missing | >= 0.8 | FAIL |
| t5_f1 | missing | >= 0.8 | FAIL |
| t5_test_support | missing | >= 50 | FAIL |
| speaker_leakage | missing | <= 0 | FAIL |
