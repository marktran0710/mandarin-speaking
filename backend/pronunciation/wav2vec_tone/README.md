# Mandarin tone classification — Phase 1 (experimental)

Frozen Mandarin wav2vec2 → mean-pooled embedding → logistic regression →
tone 1/2/3/4 probabilities.

```
WAV → wav2vec2 (frozen) → last_hidden_state → mean-pool → LogisticRegression → P(tone)
```

## Isolation

This module is **experimental and separate from the production scoring path**.

- It imports nothing from the running application.
- Nothing in the application imports it.
- Removing this directory cannot affect what students receive.

Note in particular that `backend/tone_scoring/` is **not** a safe home for
experiments: `praat_analyzer.py` imports from it, so that package is live.

Phase 1 deliberately excludes: fine-tuning, Praat/F0 features, CTC, and
phoneme recognition.

## 1. Install

Everything is already in the backend environment. To install standalone:

```bash
cd backend
pip install -r pronunciation/wav2vec_tone/requirements.txt
```

No GPU is needed — the encoder runs inference only and nothing is fine-tuned.

The default checkpoint is `TencentGameMate/chinese-wav2vec2-base`
(Mandarin-pretrained; tone is precisely what an English-only model has least
reason to encode). It is already in this machine's Hugging Face cache, so the
first run does not download.

## 2. Prepare the CSV

```csv
audio_path,speaker_id,pinyin,tone
audio/001.wav,S001,ma1,1
audio/002.wav,S002,ma2,2
audio/003.wav,S003,hao3,3
audio/004.wav,S004,shi4,4
```

- `audio_path` — WAV, absolute or relative **to the CSV file**. Any sample rate
  or channel count; it is resampled to 16 kHz mono automatically.
- `speaker_id` — must be stable per speaker. This drives the split, so getting
  it wrong invalidates every number below.
- `pinyin` — carried through for inspection; not used as a feature.
- `tone` — 1, 2, 3 or 4. Neutral tone is out of scope for Phase 1.

Each clip should contain **one syllable**: the embedding is mean-pooled over
the whole file, so a multi-syllable clip averages several tones into one
vector.

At least **two speakers** are required, and more is much better — the split
holds out whole speakers.

## 3. Extract embeddings

```bash
cd backend
python -m pronunciation.wav2vec_tone.extract_embeddings \
    --csv path/to/tones.csv \
    --out pronunciation/wav2vec_tone/models/embeddings.npz
```

Unreadable files are reported and skipped, never filled with zeros — a zero
vector is indistinguishable from a real measurement once it reaches the
classifier.

## 4. Train

```bash
python -m pronunciation.wav2vec_tone.train_classifier \
    --embeddings pronunciation/wav2vec_tone/models/embeddings.npz \
    --out pronunciation/wav2vec_tone/models/tone_classifier.joblib
```

Prints train and test accuracy plus the gap between them. A wide gap means the
probe is fitting the training voices rather than tone.

The saved file contains **only the classifier**, not wav2vec2 — the encoder is
frozen, so its weights reproduce exactly from the checkpoint name.

## 5. Evaluate

```bash
python -m pronunciation.wav2vec_tone.evaluate \
    --embeddings pronunciation/wav2vec_tone/models/embeddings.npz \
    --model pronunciation/wav2vec_tone/models/tone_classifier.joblib \
    --json pronunciation/wav2vec_tone/models/report.json
```

Reports accuracy, macro F1, per-tone precision/recall/F1, and the confusion
matrix. Read the **per-tone** numbers, not just accuracy: tone 3 is the rarest
and most reduced in connected speech, so a classifier can look fine overall
while barely recognising it.

Pass the same `--test-ratio` and `--seed` used in training, or the evaluation
will score speakers the classifier was trained on. A warning fires if the
held-out set does not match.

## 6. Predict one file

```bash
python -m pronunciation.wav2vec_tone.predict \
    --audio sample.wav \
    --model pronunciation/wav2vec_tone/models/tone_classifier.joblib
```

```json
{
  "predicted_tone": 3,
  "probabilities": {
    "tone_1": 0.03,
    "tone_2": 0.12,
    "tone_3": 0.79,
    "tone_4": 0.06
  }
}
```

## Speaker-independent splitting

Whole speakers are assigned to train or test — never individual recordings. A
classifier that has heard a speaker during training can recognise that voice's
habits instead of the tone, score well in testing, and fail on the first new
learner. Splitting by recording is the easiest way to produce a number that
means nothing.

The split is seeded, so it is reproducible; `train_classifier.py` records which
speakers were held out inside the saved model.

## Expectations

Set honestly, from measurements already taken in this repository:

- Frozen wav2vec2 embeddings have already been tried on the related
  tone-*scoring* task here and scored **worse** than hand-designed acoustic
  features (kappa 0.074 vs 0.085). Frozen embeddings plus a linear head is the
  weakest of the three ways to use wav2vec2.
- Published Mandarin tone recognition exceeds **90%** on native, well-segmented
  speech. Connected L2 speech with imperfect segmentation is considerably
  harder.
- Our existing hand-designed features reach **53%** on 4-way tone
  identification under a speaker-disjoint split. That is the number to beat for
  this module to be worth pursuing.

Phase 1 exists to measure the frozen-embedding baseline cleanly, not because it
is expected to win.
