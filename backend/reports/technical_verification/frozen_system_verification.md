# Phase TV — frozen-system technical verification

**System under test** `OMPAL_R2_PASS_v1`
**System sha256** `8101bcaf8c92e1e33feda00c236e10943a09e7146d09ead6de673af43b287436`
**Date** 2026-08-09
**Runner** `python -m pronunciation.wav2vec_tone.verify_frozen_system`
**Result** **FROZEN SYSTEM TECHNICALLY VERIFIED — HUMAN VALIDATION STILL REQUIRED**

---

## What this report does and does not support

Supported:

> The frozen implementation behaves as specified: deterministic processing,
> policy compliance, fail-safe behaviour, and software/runtime integrity.

Not supported, and not claimed anywhere in this document:

> The system accurately evaluates real CFL learners.

No teacher and no learner was contacted. No human validation data exists. Human
criterion validation remains required before any real-world assessment-accuracy
claim, and remains blocked at the Phase D2 gate (`STUDY_START_READY = NO`).

---

## Headline numbers

| | |
|---|---|
| checks executed | 127 (121 PASS, 5 FAIL, 1 diagnostic) |
| acceptance criteria met | 10 / 10 |
| findings requiring disclosure | 3 (1 HIGH input contract, 1 HIGH representation sensitivity, 1 MEDIUM input validation) |
| decision nondeterminism on identical inputs | 0 |
| unsafe PASS from malformed input | 0 |
| OMPAL Test seal | intact (5/5, verified independently) |

---

## 1. Frozen artefact integrity

Every hash was recomputed from the artefact on disk before any test ran.

| artefact | recorded | recomputed | verdict |
|---|---|---|---|
| `fresh_validation_system_FROZEN.json` | `8101bcaf8c92e1e3…` | `8101bcaf8c92e1e3…` | match |
| `ompal_phase_c8_policy_FROZEN.json` | `cc4aa4ef797f752b…` | `cc4aa4ef797f752b…` | match |
| `ompal_phase_c6_protocol_FROZEN.json` | `1afe6c5b1da4dece…` | `1afe6c5b1da4dece…` | match |
| C8 model hash | `cd911b6e67b28c41…` | `cd911b6e67b28c41…` | match |

Cross-artefact consistency also holds: `t_pass`, the enabled-tone set, the pitch
settings (60–500 Hz, 5 ms step, 20 points) and the classifier constants
(C = 0.1, `class_weight = balanced`) agree between the system file, the C8
policy and the executing code. The Train split is the frozen 1424 rows /
32 speakers.

**Two integrity observations, recorded rather than fixed:**

1. `t_pass` is **0.42274**, not the abbreviated `0.4227` that appears in the
   handover documentation. Both parse to the same IEEE double in both frozen
   artefacts (TV033); the abbreviated form is a rounding in prose only. All
   boundary tests here use 0.42274.
2. The recorded "model hash" is `sha256({C, class_weight, points})` — a hash of
   the training *configuration*, not of the training data or the fitted
   coefficients. It cannot detect a changed feature cache or a changed Train
   split. This is why `golden_reference.json` now additionally records content
   hashes for the trajectory cache, the feature cache, the manifest, the Train
   labels and the fitted coefficient vector (`bce84b07cc594bb5…`).

## 2. Policy unit tests

| assertion | result |
|---|---|
| T1 never returns PASS across a 1006-point score sweep | PASS |
| trajectory unavailable → RETRY for all four expected tones | PASS |
| NaN score with trajectory marked available → RETRY | PASS |
| T2/T3/T4 satisfying the frozen PASS rule → PASS (600/600) | PASS |
| T2/T3/T4 outside the frozen PASS rule → RETRY (600/600) | PASS |
| only `PASS` / `RETRY` ever emitted | PASS |
| scalar `decide()` agrees with vectorised `pass_mask()` on 4000 random cases | PASS |

The last row matters: the policy exists twice in the codebase — `pass_mask()` in
`phase_c8_confirmation_policy.py` derived the threshold, `decide()` in
`preflight_fresh_validation.py` serves it. They are now proven to implement one
rule, with 0 disagreements.

## 3. Threshold boundary

**Implemented operator: `score <= t_pass` → PASS.**

The score is `predict_proba[:, 1]` = P(incorrect), so **low scores PASS**. This
is the opposite of the intuitive reading and is documented here so no future
change inverts it silently.

| input | decision |
|---|---|
| one ULP below 0.42274 | PASS |
| exactly 0.42274 | PASS |
| one ULP above 0.42274 | RETRY |
| 0.422730 | PASS |
| 0.422740 | PASS |
| 0.422750 | RETRY |

The transition is one ULP wide (1.110e-16). There is no ambiguous interval and
no floating-point flat spot at the boundary.

## 4. Determinism and process restart

20 repetitions of the full production chain over the 13-item technical
reference set:

| quantity | maximum variation |
|---|---|
| F0 trajectory | 0.000e+00 |
| R2 raw score | 0.000e+00 |
| PASS/RETRY verdict | 0 changes |
| failure code | 0 changes |

A cold child process (fresh interpreter, fresh model fit) reproduced the same
frozen hash, the same fitted coefficient hash, bit-identical scores and
identical decisions. **A server restart cannot change a learner decision.**

The solver seed is also irrelevant: seed 0 (C8 derivation) and seed 20260808
(D0 preflight) produce bit-identical scores, because the frozen configuration
uses lbfgs. The preflight's different seed was never a divergence.

## 5. F0 trajectory verification

Verified against an independent re-derivation written directly from the frozen
spec, not by calling the module: 12 × 20 points, semitone conversion
`12·log2(Hz)`, time-normalised across the voiced span, token-median centred.

| invariant | observed |
|---|---|
| exactly 20 points | all |
| all values finite | 11/11 available tokens |
| median-centred | worst \|median\| = 7.1e-15 |
| independent re-derivation matches module output | max delta 0.000e+00 |
| sample grid strictly increasing | yes |
| no raw-Hz value leaked into a semitone slot | max 3.04 ST |

## 6. Expected-tone routing

For fixed audio routed through controlled expected-tone metadata:

- T1 activates no dummy (correct — it is the reference level)
- T2 → `[1,0,0]`, T3 → `[0,1,0]`, T4 → `[0,0,1]`
- exactly the matching trajectory×tone interaction block is populated
- four distinct scores result (T1=0.4185, T2=0.4276, T3=0.7066, T4=0.6845)

No tone-index shift, no ignored `expected_tone`, no wrong one-hot column.

Design matrix: **83 columns**, verified *by name and formula*, not by count —
20 trajectory + 3 reference-coded dummies + 60 interactions, each column checked
against its expected value for each of the four tones.

*The four scores above are a software-routing result. They are not four
pronunciation judgments of the same recording.*

## 7. Audio input robustness

19 cases. **0 unsafe PASS.** Everything unprocessable resolved to RETRY with a
named failure code:

| case | trajectory | decision | code |
|---|---|---|---|
| normal valid WAV / mono 16 kHz | yes | scored | — |
| digital silence | no | RETRY | `insufficient_voiced_frames` |
| very short (10 ms) / empty | no | RETRY | `too_short_for_pitch` |
| corrupted / unsupported / missing file | no | RETRY | `unreadable_input` |
| NaN samples / Inf samples | no | RETRY | `insufficient_voiced_frames` |
| white noise (unvoiced) | no | RETRY | `insufficient_voiced_frames` |
| stereo input | no | RETRY | `multichannel_input` |
| clipped / very low / very high amplitude | yes | scored | — |
| DC offset constant | no | RETRY | `insufficient_voiced_frames` |
| **8 / 44.1 / 48 kHz** | yes | **scored, silently** | — see finding TV-F1 |

No preprocessing was changed to make any case pass.

## 8. Metamorphic tests

Tolerances were fixed in the source **before** any result was inspected.

| transformation | worst contour delta | tolerance | verdict |
|---|---|---|---|
| amplitude × 0.8 | 5.9e-09 ST | 0.05 | within |
| amplitude × 1.2 | 9.8e-09 ST | 0.05 | within |
| lossless WAV rewrite | 0.0 ST | 1e-09 | within |
| leading silence 100 ms | **14.53 ST** | 0.25 | **exceeded** |
| trailing silence 100 ms | **1.17 ST** | 0.25 | **exceeded** |

One decision flipped under leading silence (5/6 preserved). The tolerances were
**not** relaxed after the fact.

**The sensitivity is explained, not unexplained.** Mechanism isolation:

- 3 of 12 padding cases left the voiced span unchanged → worst delta
  **0.0065 ST** (harmless)
- 9 of 12 changed the voiced span → deltas up to **14.53 ST**
- all 9 span changes came from the pitch tracker reporting *extra* voiced
  frames, e.g. 23 → 29 frames with the first voiced F0 moving 189 → 354 Hz
  (an onset octave artefact at the silence/speech boundary)

Because the contour is time-normalised across the voiced span and centred on its
median, a single spurious edge frame both rescales the time axis and injects an
outlier. Padding itself is harmless; span redetection is the whole effect.

## 9. Fail-safe tests

| trigger | behaviour |
|---|---|
| sub-30 ms audio | `(None, too_short_for_pitch)` |
| insufficient voiced frames | `(None, insufficient_voiced_frames)` |
| NaN F0 / Inf F0 | no usable trajectory, RETRY |
| invalid expected tone (`None`, `''`, `'5'`, `'0'`, `'T2'`, `2`, `2.0`, `'  2  '`) | RETRY in all 8 cases |
| tampered threshold in the frozen file | self-hash mismatch detected; run would halt |
| all-NaN trajectory reaching the scorer | rejected upstream, RETRY |

**No silent PASS was reachable by any route tested.**

One subtlety worth recording: the median imputer inside `fit_predict` will
happily replace an all-NaN feature row with Train medians and return a
plausible score (0.494891 observed). The guard that prevents this from becoming
a verdict lives *upstream*, in the availability check. Any future caller that
scores without that check loses the protection.

## 10. Logging and privacy

All ten required research-log fields are present: system version, system hash,
timestamp, item ID, expected tone, trajectory availability, raw score, decision,
failure reason, processing latency. No participant-identifying field is required
for technical inference.

Learner-facing output is exactly two frozen strings. Neither contains a digit, a
score, a probability, a percentage, the words *wrong* / *incorrect* / *instead
of*, a produced-tone diagnosis, or an error trace.

`OMPAL_R2_PASS_v1` currently has **no HTTP route and no UI binding**. The only
learner-facing surfaces are the two message constants in
`preflight_fresh_validation.py`. The live app's `routers/tones.py` is a separate
legacy path and is not this system; when this system is eventually wired up, the
privacy checks here must be re-run against the real response payload.

## 11. Runtime and stress

| metric | value |
|---|---|
| model cold start (fit) | 1.21 s |
| first inference | 8.85 ms |
| warm median | 2.29 ms |
| IQR | 2.00 – 3.36 ms |
| p95 | 6.01 ms |
| files processed | 12 (11 scored, 1 safe RETRY, 0 hard failures) |
| stress calls | 500 in 2.27 s (220 calls/s) |
| crashes / resource errors / decision instability | 0 / 0 / 0 |
| heap growth over 500 calls | 0.019 MB |
| model reload during run | none (coefficient hash stable) |

**Latency scope, stated so it is not over-read:** these numbers are for
pre-extracted single-token audio already on disk. They exclude capture, upload,
forced alignment and token segmentation, and are **not** an end-user latency
estimate. Latency is reported, not used as a pass/fail criterion.

## 12. Golden regression set

`data/technical_verification/golden_reference.json` — 12 entries drawn from
OMPAL `native_reference` tokens only (non-Test, non-validation). Each entry
carries audio reference ID, expected tone, trajectory sha256 (tol 1e-9), raw
score (tol 1e-9), expected PASS/RETRY, expected failure status, plus the system
hash, the coefficient hash, the 83 design column names and the training-input
content hashes.

Expected values describe **what the frozen implementation does today**. They are
not correctness labels for pronunciation.

## 13. OMPAL Test lock

| check | result |
|---|---|
| Test predictions produced | NO |
| Test scores produced | NO |
| Test metrics produced | NO |
| Test rows in feature cache | 0 |
| Test rows in trajectory cache | 0 |
| technical reference set ∩ Test | empty |
| independent seal verifier `verify_ompal_test_seal.py` | exit 0, SEALED |
| Test split still defined in manifest | 322 rows (sealed, not deleted) |

## 14. Acceptance

All ten criteria from the Phase TV brief are met:

- frozen hashes match
- 0 policy violations
- 0 unsafe PASS from malformed or unprocessable input
- 0 decision nondeterminism on identical inputs
- feature ordering exactly matches the frozen definition
- expected-tone routing verified
- trajectory implementation verified
- no learner-facing raw-score leak
- technical reference batch completes without unexplained failures
- stress test shows no decision instability

Three findings fall **outside** those criteria and are therefore disclosed
rather than absorbed. They are not waived. See `BUG_CLASSIFICATION.md`.

## 15. Interpretation

> The frozen implementation has passed technical verification for deterministic
> processing, policy compliance, fail-safe behaviour, and software/runtime
> integrity.

> This does not establish pronunciation-assessment validity for real learners.
> Human criterion validation remains required before claiming real-world
> assessment accuracy.

## 16. Preconditions this run adds to the human study

None of these change the model. All three concern the **input contract** — the
guarantee that audio reaching the frozen system was produced the same way the
Train tokens were.

1. **Sample rate must be 16 kHz at the point of pitch extraction.** Verify at
   ingest; reject or resample explicitly. Browser `MediaRecorder` defaults to
   48 kHz, which this run showed shifts a score from 0.4185 to 0.6569 on the
   same speech.
2. **Token boundaries must come from the same aligner and boundary policy as
   Train.** Do not hand the system a hand-trimmed or silence-padded clip.
3. **Expected tone must be passed as a string `"1"`–`"4"`.**

If a fix for any of these changes sample rate, codec, channels, gain,
normalisation, token boundaries or trajectory computation, that is a
**representation change** — stop, declare a new system version, re-freeze and
re-run the D0 preflight. Nothing in this run did that.

---

*Artefacts: `data/technical_verification/` — `verification_matrix.csv` (127
rows), `technical_verification_summary.json`, `golden_reference.json`,
`audio_robustness_matrix.csv`, `metamorphic_results.csv`,
`synthetic_contours.csv`, `logging_sample.csv`.*
