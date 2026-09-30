# "像老師的聲音" score: evaluation and design (2026-09-30)

The percentage students see after a recording is `modelSimilarity`
(`frontend/src/entities/speech/modelSimilarity.ts`): how closely their pitch
follows the teacher's recording, word by word. It is practice feedback only -
never used to pass, fail or unlock anything - and it is **not validated against
teacher ratings**. Everything below is a property check on real teacher
contours, not a measure of agreement with a human.

## What was wrong with the original (`legacy`)

Mean per-word Pearson r, floored at 0. Pearson is blind to size, so:

- With a clean tracker, a nearly flat attempt (10% of the model's range) with a
  tiny wobble in the right direction scored **72** (median) and a half-range
  attempt scored 93.
- A run of frames the pitch tracker reports an octave off (which it can hold
  for many frames on creaky voice) dragged real attempts down, and the same
  errors sit in the teacher's stored contour (148 of 654 word contours, 23%,
  contain one).
- Unrelated words already score r about 0.36 after the window-shift search, so
  anything below ~36% carried no information.

## What v2 does

1. `foldOctaveBlocks` (`pitchCleaning.ts`): a Viterbi pass that shifts points by
   0 or +-12 semitones to minimise frame-to-frame jumps, with a switch penalty
   so genuine resets between syllables (7-9 st) and tone-4 falls are kept. Applied to
   the student's curve and to each teacher word.
2. Word score = shape factor x range factor.
   - shape: `(r - 0.4) / (0.85 - 0.4)`, clamped to 0..1.
   - range: student pitch range (10th-90th percentile, semitones) divided by the
     model's (floored at 3 st), `(ratio - 0.2) / (0.6 - 0.2)`, clamped. One-sided:
     moving more than the model is never penalised; 60% of the model's range is
     full credit.
3. Sentence score = mean of the word scores. `algorithm: "legacy"` keeps the old
   score for comparison and as an instant rollback.

DTW was re-tested in a separate comparison and again rejected: after alignment
it scored no better than the same distance without alignment (AUC 0.962 vs
0.968) while forgiving late or wrongly timed attempts.

## Results (synthetic degradations of 82 real teacher sentences, 640 attempts per class)

AUC = probability a natural re-recording outscores the degraded one (0.5 = coin flip).

| degraded version | legacy | v2 |
|---|---|---|
| flat (x0.1 range) | 0.902 | 1.000 |
| half range (x0.4) | 0.621 | 0.957 |
| mirrored | 1.000 | 1.000 |
| time-reversed | 0.998 | 0.999 |
| other word's shape | 0.992 | 0.994 |
| random walk (tracker junk) | 0.990 | 0.999 |
| **overall (these six), octave errors injected** | **0.917** | **0.992** |
| overall, clean tracker | 0.947 | 0.993 |

Score a student would see (p10 / median / p90), octave errors injected:

| class | legacy | v2 |
|---|---|---|
| natural re-recording | 69 / 87 / 97 | 67 / 88 / 100 |
| flat (x0.1) | 45 / 64 / 78 | 0 / 2 / 10 |
| half range (x0.4) | 61 / 82 / 95 | 40 / 56 / 68 |
| narrow (x0.6, ambiguous) | 64 / 85 / 96 | 61 / 85 / 99 |
| random walk | 8 / 29 / 55 | 0 / 9 / 24 |
| other word | 4 / 30 / 54 | 11 / 29 / 50 |

Octave-error robustness: a natural re-recording loses 9 points under legacy
(96 -> 87) and 3 under v2 (91 -> 88).

Where v2 does **not** help: an attempt that is right but delayed by 35% (ambiguous
by construction) and "other word" shapes score about the same as before, and a
model-shape-only variant (cleaning + rescaling without the range factor) was
*worse* than legacy (AUC 0.901 vs 0.917) - **all of the discrimination gain comes
from the range factor.**

## Real learner attempts (limits apply)

44 of 114 stored attempts have a lined-up model voice; the other 70 have a
script/word mismatch, so no score is shown. **All of them come from one
account (the developer's test student) and repeat a handful of recordings**, so
treat this as a sanity check only: Spearman(legacy, v2) = 0.83 (rankings agree),
median 60 -> 42, v2 lower in 37 of 44. The drop is mostly the removal of the
~30-point floor unrelated words used to get.

## Teacher contours regenerated with a speaker-adaptive tracker

`extract_pitch_two_pass` (`domain/speech/acoustics/audio_features.py`) fits the
pitch range to the speaker (0.75 x q25 .. 2.5 x q75 of their own f0) instead of a
fixed 75-500 Hz window and is now used when the teacher's model contour is
generated. All 82 stored teacher recordings were re-tracked
(`python -m scripts.backfill_model_contours --regenerate --apply --backup ...`;
the replaced contours are in `backend/output/contours_before_regen_20260930.json`,
git-ignored, so the change can be reverted).

| | before | after |
|---|---|---|
| word contours ending >8 st away from their body | 20% | 16% |
| word contours wider than 12 st | 24% | 19% |
| word contours with an octave-error block | 23% | 21% |
| v2 overall AUC (synthetic, tracker errors injected) | 0.991 | 0.987 |

A modest cleanup, not a fix for everything: the two-pass tracker resolved about a
quarter of the one-syllable words that contained an octave-error block (38 -> 29
of 299); the rest persist under every tracker tried and may be genuine creak. The
AUC change is inside the noise of the synthetic set. Scoring curves
(`sentenceReferenceCurves`) were deliberately left on the original tracker.

## Known limits / next steps

- The range policy (`rhoFull` 0.6) is a pedagogical choice, not a fitted value:
  sweeping it moves the AUC of the "half range" class from 0.86 (0.5) to 0.99 (0.7).
- Teacher contours still run wide (median word range ~8 st, 103 words over 12 st
  after cleaning): multi-syllable words legitimately include resets and some
  large steps may be genuine creak. Learner recordings still use the fixed-range
  tracker; moving them to `extract_pitch_two_pass` is the obvious next experiment.
- Recalibrate `DEFAULT_SIMILARITY_PARAMS` when real teacher ratings or many more
  learners' attempts exist. Reproduce everything with
  `frontend/scripts/model-similarity-eval/`.
