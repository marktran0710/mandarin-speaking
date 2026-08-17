# OMPAL sample fixture — attribution

The 16 `.wav` files in `wav/` and their metadata in `metadata.json` are a
small subset of the OMPAL corpus, vendored for fast, offline, real-speech
regression tests (see `../test_tone_scorer_ompal_regression.py` and
`../test_asr_real_audio.py`).

**Source:** [phantomhsieh/OMPAL-corpus](https://github.com/phantomhsieh/OMPAL-corpus)
**License:** CC BY 4.0

> OMPAL corpus (phantomhsieh/OMPAL-corpus), licensed CC BY 4.0. 82 native
> and 1,768 French-L1 learner Mandarin utterances with expert ratings.
> (Citation text reused from `backend/benchmarking/ompal_corpus.py:CORPUS_CITATION`.)

## What was selected and why

16 utterances (of 1,850 total) were picked by `select_ompal_subset.py`
(vendored alongside this file for reproducibility — not run in CI, only
by hand if the subset needs regenerating) to cover:

- Both populations: native speakers and French-L1 learners.
- All four lexical tones (1-4) across the sample.
- A mix of unanimous-rater-consensus "tone correct" and "tone incorrect"
  words — utterances with rater disagreement on any word were excluded, so
  every reference label here is unambiguous.

Only short utterances (2-6 words) were considered, to keep vendored audio
small and the reference transcripts easy to read directly in test code.

## Population caveat

Per `ompal_corpus.py`'s own docstring: these are native speakers and
French-L1 learners reading prompted sentences. This fixture validates that
the ASR/tone-scoring pipeline behaves sanely on **real human speech** with
**known correct labels** — it is not a claim that this sample represents
this app's actual (multi-L1) student population. See
`backend/reports/ompal_real_world_validation_protocol.md` for the fuller
population-generalization discussion.
