# OMPAL integration

The current Wav2Vec2/Praat pronunciation rubric can be evaluated offline against
OMPAL's expert sentence ratings using `scripts.research.ompal.run_rubric`.
This complements the older `prepare`, `run_system`, and `analyze` workflow,
which evaluates the legacy tone-feedback pipeline.

From `backend/`:

```powershell
git clone https://github.com/phantomhsieh/OMPAL-corpus.git benchmarking/external/OMPAL-corpus
python -m scripts.research.ompal.run_rubric --corpus benchmarking/external/OMPAL-corpus --fold 1 --plan-only
python -m scripts.research.ompal.run_rubric --corpus benchmarking/external/OMPAL-corpus --fold 1 --limit 5 --out output/ompal/smoke.json
python -m scripts.research.ompal.run_rubric --corpus benchmarking/external/OMPAL-corpus --fold 1 --out output/ompal/fold1.json
```

Repeat full runs for folds 2–5 with separate reports. Official folds overlap:
do not pool them as independent samples or fit thresholds using test labels.
Calibration must use training speakers and preserve held-out tests.

Native references come only from the selected test fold and must match the exact
sentence text. Missing references or audio are skipped. The runner uses the same
extraction, Wav2Vec2, fluency and prosody functions as the application without
cloud feedback calls, database writes or threshold changes. Configured Wav2Vec2
dependencies and model assets are required for pronunciation; unavailable
pronunciation remains null while acoustic dimensions can run.

Reports include individual decisions, policy settings, annotation SHA-256,
coverage, MAE and Pearson correlation. Degraded evidence is excluded from
agreement metrics and counted separately. Constant scores or too few pairs
produce null correlation. `--limit` marks smoke runs and prioritizes matched
references; `--plan-only` checks pairing
without acoustic models and does not produce assessment results. Reports contain
absolute local audio paths: review before sharing.

OMPAL accuracy is compared with our pronunciation score as a **proxy**. Our
reference similarity rubric is not the paper's trained regression model and does
not supply binary consonant/vowel correctness. This integration does not assert
that the app reproduces the paper's results or is teacher-calibrated.

The paper's baseline combines `wav2vec2-large-960h` representations with
text/pinyin and duration features in a trained BLSTM regression network. Selecting
that encoder alone does not load the trained scoring head. The linked corpus
repository supplies audio, annotations and splits, but no scoring checkpoint or
inference implementation. Deploying that baseline requires trained artifacts
from the authors or a separately trained and validated implementation.

Source: [OMPAL corpus](https://github.com/phantomhsieh/OMPAL-corpus),
[paper](https://www.isca-archive.org/interspeech_2025/hsieh25b_interspeech.html).
Corpus license: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Credit: Wen-Wei Hsieh, Hao-Wei Chi, Kuan-Chen Wang, Ping-Cheng Yeh, Te-hsin Liu,
and Chen-Yu Chiang. OMPAL: Bridging Speech and Learning with an Open-Source
Mandarin Pronunciation Assessment Corpus for Global Learners. Interspeech 2025,
2415–2419, DOI: 10.21437/Interspeech.2025-983.
