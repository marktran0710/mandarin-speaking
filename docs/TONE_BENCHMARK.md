# Mandarin tone benchmark protocol

This project treats the tone score as a **prediction to validate**, not a
claim of ground truth. The benchmark tool compares a frozen app score against
recordings independently labelled by qualified human raters.

## 1. Prepare the external audio manifest

Create the private workspace and CSV template first:

```powershell
cd backend
python -m scripts.benchmark_tones init --output-dir .\private-data
```

This creates `private-data/external_manifest.csv` and
`private-data/audio/`. Existing manifests are never overwritten. Both remain
outside Git through `.gitignore`.

Use one row for one prompted syllable attempt. Paths may be absolute or relative
to the manifest CSV. Keep the final external set separate from threshold
selection, feature changes, and model training.

```csv
recording_id,speaker_id,audio_path,expected_tone,human_label,human_score
ext-001,learner-17,audio/001.wav,2,pass,90
ext-002,learner-17,audio/002.wav,3,fail,30
```

Required columns:

- `recording_id` — unique and stable; never use a student's real name.
- `speaker_id` — stable pseudonymous learner ID. It prevents speaker leakage.
- `audio_path` — WAV file path, relative to this CSV or absolute.
- `expected_tone` — `1`, `2`, `3`, or `4` from the prompt.
- `human_label` — blinded human judgement: `pass`/`fail`, `correct`/`incorrect`, or `true`/`false`.

Optional field:

- `human_score` — a human rubric score from 0 to 100; enables MAE and Spearman correlation.

Use at least two trained Mandarin raters. Resolve disagreement before creating
the final `human_label`, and retain the original ratings plus the adjudication
reason in a secure researcher-only file. Do not put raw student audio in Git.

## 2. Run the frozen production scorer

The simplest option runs scoring and evaluation together. `--threshold` must
already have been selected on development data:

```powershell
cd backend
python -m scripts.benchmark_tones run `
  --input .\private-data\external_manifest.csv `
  --threshold 70 `
  --output-dir .\private-data\benchmark-run
```

The terminal prints a short agreement summary and creates
`external_scored.csv`, `external_errors.csv`, and
`external_tone_report.json`.

To run only the exact Praat extraction and tone-shape scorer used by the
application:

```powershell
cd backend
python -m scripts.benchmark_tones score `
  --input .\private-data\external_manifest.csv `
  --output .\private-data\external_scored.csv `
  --errors .\private-data\external_errors.csv
```

Missing files and recordings with too few voiced F0 frames are written to the
error CSV and excluded. They are never converted into zero pronunciation
scores, because audio/data failures are not learner pronunciation failures.

The scored output adds `system_score`, `detected_tone`, `pitch_frame_count`,
and `detector_confidence`. Review every error before running evaluation.

## 3. Split internal data safely

Only internal development data may be split. Every recording from a learner
must stay in exactly one split:

```powershell
cd backend
python -m scripts.benchmark_tones split `
  --input .\private-data\internal_scored.csv `
  --output-dir .\private-data\splits
```

This creates `train.csv`, `dev.csv`, and `test.csv` by `speaker_id`, never by
row. Use train/dev to change features or choose a threshold. Do **not** tune
against the external corpus.

## 4. Evaluate the frozen system externally

After choosing a threshold on development data, run one final report:

```powershell
cd backend
python -m scripts.benchmark_tones evaluate `
  --input .\private-data\external_scored.csv `
  --threshold 70 `
  --output .\private-data\reports\external-tone-report.json
```

The JSON report includes:

- pass/fail accuracy, precision, recall, F1, and Cohen's kappa;
- the same pass/fail metrics for each expected tone (so T2–T3 failures cannot hide);
- a T1–T4 confusion matrix when `detected_tone` is supplied;
- MAE and Spearman correlation when human rubric scores are supplied;
- a bounded list of AI/human disagreement IDs for teacher audit.

Report the number of speakers and recordings together with every metric. A
high accuracy on an imbalanced set can mislead; Cohen's kappa and per-tone F1
make that visible.

## 5. Enforce the student-release gate

Generating a report does not authorize a release. Run the independent gate
after the external report is created:

```powershell
cd backend
python -m scripts.gate_tone_release `
  --report .\private-data\reports\external-tone-report.json
```

The default gate requires all of the following:

- at least 800 recordings from at least 40 speakers;
- pass/fail accuracy >= 0.85 and Cohen's kappa >= 0.70;
- F1 >= 0.80 independently for each of tones 1, 2, 3, and 4;
- false-positive rate <= 0.05;
- mean absolute score error <= 12 and Spearman correlation >= 0.75.

Every metric is mandatory. A missing, null, non-numeric, infinite, or
out-of-range value fails the release. The false-positive rate may be supplied
as `pass_fail_agreement.false_positive_rate`; reports generated by the current
benchmark tool provide `false_positive` and `true_negative`, from which the
gate derives the same rate.

Exit code `0` means all checks passed, `1` means the benchmark is below the
release bar, and `2` means the report could not be read or parsed. CI/CD must
only publish student-facing tone feedback after exit code `0`. Example:

```yaml
- name: Validate Mandarin tone feedback for student release
  working-directory: backend
  run: python -m scripts.gate_tone_release --report ./artifacts/external-tone-report.json
```

Thresholds can be overridden explicitly, for example
`--min-recordings 1200 --min-accuracy 0.90`. Overrides should only make the
gate stricter for a production release; relaxing a threshold requires a
documented expert review and a new validation plan.

## What this does not validate

An ASR transcript alone is not a human tone label. A native-speaker corpus
without learner mistakes is also not enough to validate learner feedback. The
external set should resemble the intended students in age, L1/accent, device,
noise conditions, and prompt style. Treat scores with low agreement as
practice guidance, not high-stakes assessment.
