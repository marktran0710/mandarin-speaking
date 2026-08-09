# Annotation manifest

`annotation_schema.py` defines the canonical CSV/JSONL fields used by the
character, phone, tone, and audio-QC benchmark.  The NTU importer emits one
`audio` row per recording with annotation fields empty.  A reviewer may add
`character` and `phone` rows using the same file; set `parent_id` to the
recording/character `annotation_id` so the hierarchy remains auditable.

## Review workflow

1. Import downloaded audio into an unassigned manifest:

   ```powershell
   python backend/benchmarking/import_ntu_speech_bank.py `
     path/to/ntu-speech-bank `
     --output backend/private-data/ntu_speech_bank_manifest.csv
   ```

2. Fill transcript/Pinyin, speaker metadata, and `dataset_split`.  Splits must
   be speaker-disjoint.  For sealed rows use both `dataset_split=sealed_test`
   and `is_sealed_test=true`.
3. Add one character row per Hanzi with `char_start_ms`/`char_end_ms`, an
   expected T1–T5 label, produced tone, correctness, and alignment usability.
4. Add one phone row per phone (`/d/`, `/a/`, `/sh/`, `/ng/`, etc.) with gold
   start/end boundaries.  `phone_boundary_error_ms` is the frozen system's
   absolute error against that gold boundary; do not fill it while creating
   the gold annotation.
5. Review audio quality once per recording.  Mark `usable` or `unusable` and
   record reason codes such as `noise`, `clipping`, `truncation`,
   `low_volume`, `unvoiced`, or `alignment_error`.
6. Only after a second reviewer/teacher has checked the rows, set
   `review_status=approved` and use them for a sealed KPI run.

Before annotation, run the non-destructive technical audio scan.  It records
decoder status, duration, sample rate, channels, signal-health indicators and
content hashes in a separate report; it does not mark audio as human-reviewed:

```powershell
python backend/benchmarking/audio_qc.py `
  backend/private-data/ntu_speech_bank `
  --output backend/reports/ntu_audio_qc.json
```

M4A files need an installed decoder (for example, ffmpeg) before they can be
included in the decoded inventory.  Duplicate hashes should be retained in
the audit report but counted once in a sealed benchmark.

## Label rules

The transcript-derived neutral-tone candidates are listed in
`ntu_t5_preannotation_candidates.json`. They are review hints only: keep
`expected_tone` blank until the corresponding audio token is aligned and
verified. In particular, reduplicated nouns and lexical candidates such as
`爸爸`, `大夫`, or `時候` can retain a full lexical tone for a given learner.

- `expected_tone` and `produced_tone` are `T1`, `T2`, `T3`, `T4`, or `T5`.
- `detected_tone` may additionally be `Unknown`.  `Unknown` is an abstention,
  never a substitute for T5.  A T5 segment without a trained neutral model is
  recorded as `detected_tone=Unknown` with a separate
  `neutral_model_unavailable` status in the V2 result, and remains missing
  for the release gate.
- `correct_incorrect=ambiguous` and `audio_qc_status=needs_review` are not
  eligible for sealed scoring.
- Use milliseconds for all boundaries.  Do not estimate boundaries or tones
  when the recording is unusable.
- TTS and synthetic audio can be used for smoke tests only; never include it in
  learner KPI rows.

## Validation

Validate rows before import into the gate:

```python
from benchmarking.annotation_schema import validate_annotation_row

errors = validate_annotation_row(row, require_gold=True)
if errors:
    print("; ".join(errors))
```

For a complete file-level check, use the bundled validator.  It returns a
non-zero status and reports row numbers when a review is incomplete:

```powershell
python backend/scripts/validate_annotation_manifest.py `
  backend/private-data/ntu_speech_bank_manifest.csv `
  --require-gold
```

The release gate still enforces 40 speakers, 50 test segments for every tone,
300 gold phone rows, 300 reviewed audio segments (including 100 unusable),
and all KPI thresholds.  Missing T5 data therefore remains `NEEDS_DATA` even
when a four-tone engineering benchmark is complete.
