# Pronunciation rubric pilot

The active Practice Speaking, Conversation Speaking and admin pronunciation evaluator returns three separate dimensions and no `/100` total. Pronunciation uses Wav2Vec2 reference-relative initial/final segment similarity and Praat F0 lexical-tone evidence. An optional librosa adapter compares the teacher and student recordings with MFCC/DTW, speaker-relative pYIN F0 and timing evidence. Fluency and Prosody use the existing Praat feature extraction. GPT-6 Luna receives only scalar measurements, errors and rubric decisions; it receives neither audio nor embedding/F0 arrays and cannot choose scores. Its written explanation is stored with the attempt.

## Dimensions

- **Pronunciation:** Wav2Vec2 compares initial and final spans against the matching teacher recording. This is reference-relative segment evidence, not a standalone phoneme classifier. Praat F0 supplies the lexical-tone evidence; tone errors are kept separate from initial/final errors.
- **Fluency:** Praat reports total and speaking duration, target syllables per second, articulation rate, raw pause count/time/mean/ratio, and unnecessary pause measures. Reference pauses and script punctuation are treated as expected breaks. The score criteria are excess pause ratio, unnecessary pause fraction, mean excess pause, and log distance from the reference speech rate.
- **Prosody:** Praat reports speaker median normalized semitone contours, within syllable pitch samples, pitch range and movement, per syllable voiced duration, relative timing, rhythm similarity and rate stability. Pause count and time do not affect Prosody. Relative durations divide by each speaker's total; pitch uses semitones relative to each speaker's own median.

A score is the **lowest level passed across that dimension's criteria**. Levels 5, 4, 3 and 2 have configurable thresholds; a failed level 2 criterion gives level 1. Fluency and Prosody still return a 1–5 rubric level when alignment or paired pitch evidence is weak. Criteria that cannot be measured reliably use the neutral level 3 and are marked `evidence: degraded`; the dimension stores `evidence_quality: degraded` and explicit evidence reasons. Every result stores raw measurements, each criterion's value and threshold, the selected level, reason, policy and pipeline provenance. The teacher admin view shows these decisions.

## Optional librosa comparison

Set `PRONUNCIATION_LIBROSA_COMPARISON_ENABLED=true` (the default) to compare the teacher recording for the selected scene or conversation turn with the student's recording. Install `librosa>=0.10.0` if it is absent; the development image already includes it through `backend/requirements-local-asr.txt`. The production base image deliberately omits that dependency.

Each recording is loaded as mono 16 kHz audio and trimmed at the edges. The adapter compares z-scored MFCC sequences aligned by dynamic time warping. Voiced pYIN F0 is normalized around each speaker's median and compared in semitones; active-span duration and pause ratio provide timing evidence. The admin and learner views plot pitch contours on the reference timeline using the stored DTW path, with gaps where pitch is unavailable. Students receive scalar measurements and aligned contours under `reference_comparison`; full extraction settings and DTW paths remain in admin/debug output. The comparison is stored and replayed with the speaking attempt.

Practice Speaking and Conversation Speaking show the three separate 1–5 rubric scores by default. No overall score is calculated. To temporarily hide them, set `VITE_SHOW_VOICE_RUBRIC_SCORES=false` before building the frontend. Student access to `POST /api/pronunciation/evaluate` is also enabled by default and can be restricted with `PRONUNCIATION_SCORE_STUDENT_VISIBLE=false` in the backend.

Raw distances, durations, pause ratios, coverage, contours, DTW path, library version and effective parameters are kept in `debug.librosa_comparison`. GPT receives scalar measurements and evidence caveats only. The convenience transforms are `exp(-MFCC distance / scale)`, `exp(-pitch MAE in semitones / scale)`, `exp(-abs(log(duration ratio)))`, and timing similarity as duration similarity times `exp(-absolute pause-ratio difference)`. They are uncalibrated engineering transforms, not pronunciation grades or probabilities of correct pronunciation. Parameters can be tuned with the `PRONUNCIATION_LIBROSA_*` settings in `backend/.env.example` and do not set rubric scores.

If only pitch is unavailable, the result retains MFCC and timing evidence, sets pitch measurements to null and records `evidence_quality: degraded`. If librosa is absent, audio is unusable, or the configured duration limit is exceeded, the optional comparison records `status: unavailable` while Praat/Wav2Vec2 continue. DTW uses a configurable frame limit to bound memory and stores the frame stride used for longer recordings.

## Threshold status and configuration

Defaults in `domain/pronunciation/rubric.py` are engineering starting points, explicitly marked `uncalibrated_engineering_defaults`. They are not taken from a validated assessment paper. Use them for a research pilot only; do not interpret 1–5 as a validated proficiency measure. To override, set `PRONUNCIATION_RUBRIC_POLICY_JSON` in backend environment configuration. The JSON object accepts `pronunciation_limits`, `fluency_limits`, `prosody_limits`, `pause_duration_tolerance_seconds`, `pitch_distance_scale_semitones`, `pitch_range_floor_semitones`, `min_alignment_confidence`, and `min_pitch_syllable_coverage`. Each criteria map must include all its existing feature names. Each threshold array has four numbers for levels 5 through 2:

- Fluency limits are maximums and must be in ascending order. For example, `[0.05, 0.12, 0.25, 0.40]` means excess pause ratio up to 0.05 meets level 5, up to 0.12 meets level 4, and so on.
- Prosody limits are minimum similarities and must be in descending order. For example, `[0.90, 0.75, 0.55, 0.30]` applies to each listed similarity measure.

Wav2Vec2 can be selected with `PRONUNCIATION_WAV2VEC2_MODEL`, `PRONUNCIATION_WAV2VEC2_LAYER` and `PRONUNCIATION_WAV2VEC2_CACHE_DIR`. The initial and final spans currently use a documented 34% boundary after the detected Mandarin initial; this is a segmentation hyperparameter and should be calibrated with teacher ratings alongside the similarity thresholds.

Invalid policy fails evaluation explicitly. Store the exact returned `scoring_policy` alongside teacher ratings so each trial can be reproduced.

## Teacher validation

The repository already has `teacher_pronunciation_ratings` for blind independent teacher pronunciation/fluency/prosody ratings keyed to the saved audio record. For calibration, collect multiple teachers' independent ratings, export the score dimensions and raw measurements from `audio_records.praat_metrics->'pronunciation_evaluation'`, join by `audio_record_id`, split validation by student (and preferably prompt), then estimate thresholds on training students only. Report inter-rater agreement, per dimension, rank correlation and absolute error on held-out students. Do not call the defaults validated until held-out results support them.

The `pronunciation_try` command prints the same three independent decisions for local recordings. It requires the configured GPT feedback provider; it has no local feedback fallback.
