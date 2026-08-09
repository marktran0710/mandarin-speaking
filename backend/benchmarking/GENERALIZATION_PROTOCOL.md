# Generalisation protocol: improve quality without memorising the benchmark

Use the frozen OMPAL speaker split for all V2 development.  A speaker belongs
to exactly one of `train`, `dev`, or `sealed_test`; use OMPAL native speakers
only as a separate reference analysis.  The `sealed_test` is opened once for a
candidate whose architecture, training recipe, calibration, and thresholds
were selected using training and development data only.

## Required guard

Run this before any model fit and before every KPI evaluation:

```powershell
python backend/scripts/audit_benchmark_leakage.py `
  backend/pronunciation/wav2vec_tone/data/ompal_full_tone_benchmark_manifest_split.csv `
  --require-sealed-test `
  --output backend/reports/ompal_leakage_audit.json
```

The command fails for speaker overlap, duplicate sample IDs, a recording/source
group in multiple splits, byte-identical content in multiple splits (when a
SHA-256 is supplied), or any augmented sample outside `train`.

For new manifests, include `audio_sha256`, `source_sample_id`, and
`augmentation_recipe`.  `source_sample_id` is the original, unaugmented
recording/token identity; all derivative files remain in `train` with it.

## Legitimate ways to improve V2

Only apply these to training audio, with a deterministic recipe and seed stored
in the training artifact:

- Loudness normalisation to a fixed target, mono conversion and resampling to
  the fixed model rate.  Never normalise using test-set statistics.
- Mild perturbations that do not change the intended tone: gain ±3 dB, additive
  room/noise mix at 15–30 dB SNR, and short codec/reverberation simulation.
- Time masking/specaugment on learned features, plus a small time shift that
  preserves each labelled syllable boundary after it is shifted equally.
- Class-balanced sampling of *training speakers*, especially Incorrect and
  under-represented T1–T4 examples.  Do not duplicate dev/test rows.
- Train on broadly useful self-supervised speech features and calibrate score
  thresholds on `dev` only.  Freeze calibration before sealed evaluation.

Do **not** pitch-shift a labelled Mandarin tone to manufacture a different
tone label, use source/teacher IDs as features, tune a threshold on sealed
test, or include two encodes/trims of one recording in different splits.

## Evidence required for a claimed improvement

Record the model/code/data hashes, split audit artifact, training seed,
augmentation recipe, dev-selected threshold and one final sealed-test report.
Report macro-F1 and per-tone metrics, balanced accuracy, calibration and
per-speaker results.  A gain only on a single speaker, prompt or test retry is
diagnostic information, not a release-quality improvement.
