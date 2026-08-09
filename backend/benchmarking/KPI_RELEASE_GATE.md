# Unified character/phone/tone KPI gate

The owner-pilot gate currently evaluates T1-T4. T5 is explicitly deferred,
remains separate from `Unknown`, and is reported as deferred rather than used
to block the four-tone engineering pilot. Missing required evidence is
`NEEDS_DATA`; measured regressions are `BLOCKED`.

```powershell
python backend/scripts/gate_kpi_release.py `
  --report path/to/kpi_report.json `
  --rows path/to/per_character.jsonl `
  --output-dir backend/reports/kpi_gate
```

The command writes an auditable bundle containing the KPI report, row export,
tone confusion matrix, phone-boundary report, and Markdown dashboard.

Required owner-pilot gates include character alignment, human-usable
boundaries, phone-boundary accuracy within 30 ms, overall/per-phone F1,
T1-T4 accuracy and macro-F1, per-tone T1-T4 precision/recall/F1, coverage and
Unknown rate, correct/incorrect balanced accuracy/sensitivity/specificity,
audio-QC AUC/retention/recall, high-confidence PASS precision, calibration ECE,
speaker robustness, provenance, and a speaker-disjoint sealed test set.
Dataset support remains at least 40 speakers, 50 test segments per T1-T4, 300
gold phone rows, 300 reviewed audio segments, and 100 unusable audio cases.

Release statuses:

- `EXPERIMENTAL` — required evidence is missing (`NEEDS_DATA`).
- `OWNER_PILOT_READY` — every current internal KPI passes.
- `TEACHER_VALIDATED` — internal KPI passes and teacher validation is recorded.
- `BLOCKED` — at least one measured KPI fails.

## Deferred T5

The default evaluator uses `KpiThresholds(require_t5=False)`. T5 checks are
omitted from the current owner-pilot gate and returned in `deferred_metrics`.
T5 must never be merged with `Unknown` or used in teacher-facing claims. A
future full-release run can set `require_t5=True` to restore the strict
five-tone requirement.

The OMPAL adapter uses its learner T1-T4 gold labels and keeps native-reference
rows separate. It does not fabricate V2 predictions, phone gold, audio-QC gold,
or T5 support.
