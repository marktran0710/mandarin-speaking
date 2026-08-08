# Phase C3 — structural tone conditioning

Phase C2 diagnosed the failure as structural: expected tone entered additively
into a linear model can shift the intercept per tone but cannot flip the sign of
an acoustic weight, while a falling contour is evidence of *correctness* for T4
and of *error* for T2. This phase corrects that and asks whether the signal
already present in the frozen Praat features becomes usable.

Test was not touched. Selection ran inside Train only; Dev was opened once,
after the winner was frozen.

## 1. Train grouped-CV setup

1424 tokens, 32 speakers, 241 Incorrect (16.9%). `GroupKFold(5)` grouped by
`speaker_id` — never token-level random CV. Metrics come from pooled
out-of-fold predictions, with per-fold scores reported for stability.

Preprocessing order, refitted inside every fold on that fold's training
speakers only:

1. median impute the continuous Praat features
2. standardise them
3. build tone dummies — **never standardised**
4. build interactions from the **already-scaled** base features

Step 4 matters: forming products before scaling would leave every interaction
column carrying its parents' raw scale, and the single penalty `C` would then
mean something different for each one.

## 2. Candidate designs

**P0** — 10 Praat features + 3 tone dummies (reference T1) = 13 columns.
Reproduces the structurally limited Phase C model.

**P1 (primary)** — 10 features + 3 dummies + 10×3 interactions = **43 columns**,
reference-coded on T1 so the design is non-redundant. This allows a different
effective slope per tone: T1's slope is the base coefficient, and each other
tone's is base + interaction.

**P2 (secondary)** — four independent per-tone models on the same 10 features.
All four tones had adequate support (T1 65, T2 52, T3 35, T4 89 Incorrect
across 32 speakers), so none had to be refused.

Grid: `class_weight` {None, balanced} × `C` {0.01, 0.1, 1, 10}. No other
classifier family, no feature search, no feature removal.

## 3. Train out-of-fold results

Prevalence floor for PR-AUC is **0.169**.

| model | best config | PR-AUC | ROC-AUC | Bal. acc. | fold PR-AUC (mean ± sd) |
|---|---|---|---|---|---|
| **P0 additive** | balanced, C=0.01 | 0.175 | **0.463** | 0.514 | 0.187 ± 0.062 |
| **P1 interaction** | balanced, C=10 | **0.250** | **0.586** | 0.566 | 0.250 ± 0.107 |
| P2 per-tone | balanced, C=0.01 | 0.271 | 0.609 | 0.596 | — |

P0 sits *at or below* the floor, and its ROC-AUC of 0.463 is **below chance** —
the additive model is not merely weak, it is mildly anti-predictive on unseen
speakers, exactly as Phase C2 predicted from the within-tone inversion.

## 4. P0 → P1: the structural comparison

| metric | P0 | P1 | Δ |
|---|---|---|---|
| PR-AUC (Incorrect) | 0.175 | 0.250 | **+0.075** |
| ROC-AUC | 0.463 | 0.586 | **+0.123** |
| Balanced accuracy | 0.514 | 0.566 | +0.052 |
| Incorrect F1 | 0.293 | 0.327 | +0.034 |

Allowing acoustic effects to vary by expected tone moves ROC-AUC from below
chance to meaningfully above it, and lifts PR-AUC from the prevalence floor to
roughly 1.5× it. The improvement is not a tuning artefact: it appears across
the whole `C` range for P1 (0.220–0.250 PR-AUC at C ≥ 1) while no P0
configuration exceeds 0.175.

**Stability is the caveat.** Fold-level PR-AUC for P1 is 0.250 ± 0.107 across
five speaker groups. That spread is large relative to the effect, so the
improvement is directionally consistent but its magnitude is not tightly
determined by 32 speakers.

P2 scores slightly higher than P1 (0.271 vs 0.250) but the gap is well inside
that fold noise. **P1 is selected** as pre-specified: it pools information
across tones, uses one shared regulariser, and is more data-efficient than
fitting four models on as few as 35 minority tokens each.

## 5. Frozen Train-CV winner

`P1`, `class_weight=balanced`, `C=10.0`, 43-column reference-coded design,
seed 0. Frozen before Dev was opened. Protocol SHA-256
`6971a0f462d66039f59d79bb633d87b276d7362af3e78ee84ff7052e984c889b`.

## 6. Tone-specific coefficients

Positive pushes toward **Incorrect**. T1 is the reference; other tones show the
effective slope (base + interaction).

| feature | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| slope_mid_to_end | −0.486 | −0.302 | **+1.384** | −0.246 |
| rel_f0_75 | −0.788 | +0.146 | **+1.165** | −0.754 |
| rel_f0_end | +0.949 | +0.103 | **−2.001** | +1.391 |

These are phonetically coherent, and they are exactly the reversals the
additive model could not express.

For **T3** (the dipping tone) a *rising* late slope and a *high* late F0 push
strongly toward Incorrect (+1.384, +1.165), while a high endpoint pushes toward
Correct (−2.001). A correct T3 falls then rises from a low point; a learner who
keeps the pitch high through the second half has failed to produce the dip, and
the model penalises precisely that.

For **T1** and **T4**, a high endpoint pushes toward Incorrect (+0.949, +1.391)
— for a level T1 and a falling T4, the pitch should not be high at the end. The
signs are opposite to T3 on the same feature, which is the whole point of the
interaction design.

T2 coefficients sit near zero on all three, consistent with it being the tone
the model handles worst (below).

Caution: these come from one fit on 1424 tokens with 43 columns and should be
read as directionally interpretable, not as stable effect estimates.

## 7. Per-tone Train OOF (selected P1)

| tone | n | Incorrect | PR-AUC | ROC-AUC | Bal. acc. |
|---|---|---|---|---|---|
| T1 | 384 | 65 | 0.288 | 0.599 | 0.570 |
| T2 | 320 | 52 | 0.170 | **0.475** | 0.476 |
| T3 | 192 | 35 | 0.254 | 0.654 | 0.657 |
| T4 | 528 | 89 | 0.298 | 0.589 | 0.580 |

T2 remains at chance on Train OOF. The rising tone is not being detected, and
that is a real residual failure rather than a small-sample artefact — 320
tokens with 52 Incorrect is the second-largest cell.

## 8. One-time Dev confirmation

The frozen model, refit on all of Train, evaluated once on Dev (322 tokens,
6 speakers, 55 Incorrect):

| metric | value |
|---|---|
| PR-AUC (Incorrect) | **0.385** |
| ROC-AUC | **0.726** |
| Balanced accuracy | 0.672 |
| Macro-F1 | 0.612 |
| Incorrect precision | 0.318 |
| Incorrect recall | 0.618 |
| Incorrect F1 | 0.420 |
| Accuracy | 0.708 |
| **False rejection rate** | **0.273** |
| **False acceptance rate** | **0.382** |
| Brier | 0.211 |

Per tone:

| tone | n | Incorrect | PR-AUC | ROC-AUC |
|---|---|---|---|---|
| T1 | 82 | 11 | 0.190 | 0.599 |
| T2 | 74 | 10 | 0.261 | 0.717 |
| T3 | 40 | 10 | 0.504 | 0.737 |
| T4 | 126 | 24 | 0.534 | 0.777 |

Against Phase C's best (Dev PR-AUC 0.221, ROC 0.548, FRR 0.40, FAR 0.42), this
is a clear improvement on every axis. Critically, **no tone is inverted any
more** — in Phase C2, T1 and T2 sat at ROC 0.355; here the worst is T1 at 0.599.

**Read the Dev numbers with care.** Dev PR-AUC (0.385) is markedly higher than
the Train OOF estimate (0.250), and Dev ROC (0.726) higher than Train OOF
(0.586). With six speakers and 55 Incorrect tokens, Dev is a small and possibly
favourable sample. The Train-CV figure, pooled over 32 speakers and five folds,
is the more trustworthy expectation. The honest summary is "clear improvement,
best estimate around PR-AUC 0.25–0.30", not "PR-AUC 0.385".

## 9. Real-world interpretation

The technical question — does correct tone conditioning rescue the existing
acoustic signal — is answered **yes**. Discrimination is now above chance on
Train OOF and on Dev, the per-tone inversions are gone, and the learned
coefficients are phonetically readable, which matters for a system that must
eventually explain itself to a learner.

The deployment question is still answered **no**, and nothing here should be
read as approaching readiness:

- At the default threshold the system rejects **27% of correctly pronounced
  tokens** and passes **38% of genuine errors**. A learner would still be
  corrected wrongly about once in four attempts.
- Incorrect precision is 0.318: roughly two of every three "wrong" verdicts
  would be unjustified.
- T2 is at chance on Train OOF (0.475) — the system cannot currently judge the
  rising tone, which is one of the commonest L2 difficulties.
- Fold-to-fold PR-AUC varies by ±0.107, so per-speaker behaviour is not stable.
- Brier 0.211 with no calibration work yet.

Threshold selection, calibration and an uncertainty/retry policy are the
appropriate next steps now that discrimination exists — they were not worth
doing at chance level, and are explicitly deferred rather than done here.

## 10. What remains true regardless

OMPAL success would not establish real-world readiness. A fresh validation set
with real learner recordings and at least two independent Mandarin raters is
still required, measuring human–human agreement first as the ceiling, then
system–human agreement, sensitivity, specificity, FRR and FAR. Produced-tone
confusion (T3→T2 and similar) still cannot be validated from OMPAL, which never
records which tone was actually produced.

**Test remains sealed.** It should not be opened until the feature
representation, calibration, threshold and uncertainty policy are all frozen.
