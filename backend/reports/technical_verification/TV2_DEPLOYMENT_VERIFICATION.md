# Phase TV2 — deployment ingest hardening and end-to-end verification

**Scientific system** `OMPAL_R2_PASS_v1` — unchanged, sha256 `8101bcaf8c92e1e3…`
**Deployment implementation** `OMPAL_R2_PASS_v1.1`
**Audio contract** `OMPAL_AUDIO_CONTRACT_v1`
**fitted_model_sha256** `0dcee1d87c69c5b2…`
**Date** 2026-08-09
**Result** **B. DEPLOYMENT IMPLEMENTATION NOT YET SAFE FOR HUMAN EXPOSURE**

TV2 checks: 106 total — 100 PASS, 2 FAIL, 4 diagnostic.
Deployment API tests: 44 passed.
Acceptance criteria met: **10 of 12**.

---

## The primary question

> Can the exact frozen scientific model be packaged and exposed through a
> deterministic, sample-rate-safe, input-contract-safe production inference path
> without changing its scientific decision function?

**The model half: yes, proven.** The scientific decision function is provably
untouched — bit-level equivalence on all 1424 Train and 322 Dev tokens.

**The exposure half: not yet.** Two blockers remain, neither of them scientific,
both requiring a decision that is not mine to make.

---

## 1. Historical training-time audio contract

Traced from code and measured from files, not assumed.

The R2-lineage loader is `align_ompal_pilot.load_audio`: `sf.read` → mono by
channel mean → `scipy.signal.resample_poly` to 16 kHz **if needed**. Tokens were
then cut by torchaudio MMS_FA CTC forced alignment at `original_0ms` boundaries
and written at 16 kHz.

Measured over all 314 source utterances behind Train/Dev/native reference:
**every one is natively 16 kHz, mono, PCM_16.** Nothing was missing. So the
resample branch never executed during training — the frozen model has only ever
seen natively-16 kHz audio.

A second loader exists, `extract_embeddings.load_audio_16k_mono`, which uses
`np.interp`. It feeds the wav2vec embedding path, **not** the R2/Praat path.
Using it for deployment would have been the wrong resampler; `resample_poly` is
the R2 lineage.

## 2. TV-F1 — root cause and resolution

**Root cause:** every call site read audio as `audio, _ = sf.read(...)` and
discarded the returned rate, then handed the samples to Praat as though they
were 16 kHz. The rate was never compared against the frozen assumption.

**Classification: A — serving-only implementation bug.** The training pipeline
already contained the correct behaviour; serving simply never called it.
Adopting `load_audio` in the serving path cannot change how frozen material is
represented, because Train/Dev/native files are natively 16 kHz and pass through
the resample branch untouched — verified: 0 refusals, 0 resampling, deltas
exactly 0 on the reference set.

**Resolution.** Ingest now reads the declared rate, refuses sub-16 kHz outright,
and (permissive profile) canonicalises ≥16 kHz with `resample_poly`.

**Residual, disclosed rather than absorbed.** Canonicalisation is not lossless
for short tokens. Census over all 108 native-reference tokens × {44.1, 48} kHz
= 216 comparisons: **214 unchanged, 2 flipped**, both on the same 100 ms /
11-voiced-frame token (0.4082 → 0.4730, crossing `t_pass`). Worst score delta
0.0649.

Because the frozen model never saw resampled audio, the default profile is
**strict_native**: non-native rates are refused (`sample_rate_not_native`)
rather than silently absorbed. The validation study must run strict.

> A first draft of this suite reported "0 decision changes" — it had sampled
> only T1 and T2 tokens, and T1 can never PASS, so it structurally could not
> observe a flip. The census above replaced it.

## 3. TV-F2 — root cause and input contract

**Root cause (from Phase TV):** the contour is time-normalised across the voiced
span, so anything that changes which frames the pitch tracker calls voiced
rescales the whole time axis. Padding a token with 100 ms of silence made the
tracker report extra voiced frames (23 → 29, first F0 189 → 354 Hz) and moved
the contour by up to 14.53 ST.

**Classification: scientific/model limitation** — the trajectory code is
arithmetically correct. It cannot be "fixed" without changing the
representation.

**The contract question, answered from the data.** The frozen system consumes
**already-segmented target-token audio**: `boundary_policy = original_0ms`,
single aligner across all 2176 rows. It was never designed to consume a raw
recording with surrounding silence.

A silence-based detector is impossible and was not built: the frozen tokens
themselves carry leading unvoiced material — median 35.6 ms, p95 125 ms, max
300 ms over 1677 Train+Dev tokens. "No silence" is simply not the rule.

**Resolution: reproduce the segmentation stage rather than detect its absence.**
The deployment path reruns the same aligner, romanisation and integer rounding.
Verified against the manifest for token `00100114_00`: start delta **0.0 ms**,
end delta **0.0 ms**.

Bounds where segmentation cannot be verified (`pre_segmented` mode): duration
envelope 60–982 ms, measured from the frozen tokens. Out-of-contract padding was
verified never to upgrade a RETRY into a PASS (0/12); 1 of 12 decisions differed
in the safe direction.

## 4. TV-F3 — fix

`validate_expected_tone()` runs **before any feature is constructed**. Accepts
`"1"`–`"4"` and `"T1"`–`"T4"` (case-insensitive, trimmed), normalised to the
frozen internal label. Rejects `None`, int, float, bool, bytes, list, dict,
arbitrary objects, `""`, `"0"`, `"5"`, `"T5"`, `"two"` — 14 invalid forms
tested, **0 leaked**.

An integer can no longer reach `design()` and be scored through the T1 reference
branch. **No valid input's score changed:** max delta 0.0 across the reference
set; `"T2"` and `"2"` route identically.

**Classification: implementation bug fix** — it restores the tone contract the
frozen design already defined.

## 5. Persisted fitted-model artefact

`data/technical_verification/frozen_inference_bundle.{npz,json}` — produced by
the existing frozen full-Train fitting procedure, then captured. It carries
fitted coefficients and intercept, imputer medians, scaler mean/scale/var, the
83 feature-column names in exact order, C, class_weight, solver, max_iter, seed,
the full trajectory configuration, threshold, enabled tones, Train split and
cache content hashes, and software versions.

The classifier no longer refits on process start (previously 1.2 s of the
serving path). Preprocessing is applied inline — exact elementwise operations,
proven bit-identical below — so serving does not depend on sklearn's private
fitted-state attributes, which change between releases.

## 6. Scientific equivalence proof

| set | n | max score delta | PASS/RETRY disagreements |
|---|---|---|---|
| Train | 1424 | 3.33e-16 | **0** |
| Dev | 322 | 2.22e-16 | **0** |
| golden reference | 12 | 0.0 | **0** |

Coefficients and intercept: **max delta exactly 0.0**.
Feature column names and order: identical, first mismatch `none`.

Deltas at 2–3e-16 are last-bit floating-point noise from operation ordering,
three orders of magnitude inside the 1e-12 tolerance. OMPAL Test was not
touched.

**The scientific decision function is unchanged.** Under §13 of the brief this
qualifies as a deployment implementation version, `OMPAL_R2_PASS_v1.1`. The
frozen scientific artefact was not overwritten and its hash is unchanged.

## 7. Real fitted-model hash

| hash | value | binds |
|---|---|---|
| `fitted_model_sha256` | `0dcee1d87c69c5b2…` | coefficients, intercept, imputer statistics, scaler parameters, feature schema, scientific config, decision policy, audio contract |
| `model_config_sha256` | `cd911b6e67b28c41…` | only `{C, class_weight, points}` — retained under its honest name |
| `feature_schema_sha256` | `c3a204cdb96c7531…` | the 83 column names in order |

Verified that **every bound quantity moves the hash**: perturbing a
coefficient, the intercept, an imputer statistic, a scaler mean, a feature name
or `t_pass` all change it (6/6).

## 8. Canonical production inference path

`infer_tone_attempt()` in `deployment_inference.py` owns the whole chain:
validation → audio contract → segmentation → trajectory → 83-column vector →
persisted coefficients → exact `t_pass` → tone gate → PASS/RETRY → structured
log. It never raises; every failure returns RETRY with a structured code.

Verified by AST scan (not text grep): **zero executable threshold comparisons**
outside the imported frozen `decide()`. The HTTP layer contains no `t_pass`, no
`0.42274`, no `predict_proba`, no `raw_score`. The derivation-time `pass_mask()`
and the serving `decide()` still agree on 4000 random cases.

**Startup fails closed.** Eight integrity checks; tampering with the fitted
hash, system hash, policy hash, feature-schema hash, bundle content hash or the
column order each raises `ContractViolation` and refuses to serve (6/6).

## 9. Legacy-route audit

| surface | verdict |
|---|---|
| `routers/tones.py` | clean — two GET endpoints serving static reference contours, no judgement |
| `deployment_api.py` | **not mounted in main.py** — verified; mounting is the act that exposes the system |
| **`praat_analyzer.py`** | **BLOCKER — a second active pronunciation engine** |

`praat_analyzer.py` emits exactly what the frozen policy forbids:

* `tone_accuracy: float` — a percentage, rendered to students as
  `{Math.round(record.praatMetrics.tone_accuracy)}%` in `RecordCard.tsx`
* `detected_tone: int` — a produced-tone diagnosis
* `_tone_mismatch_diagnosis()` — e.g. *"Your pitch fell — Tone 2 rises…"*

It is a different product surface (whole-story recording analytics, reached via
`main.py` and `routers/benchmark.py`), not a route that intercepts OMPAL
requests. But a study participant using this app would receive percentage tone
scores and produced-tone diagnoses from a non-frozen engine, which both
contradicts the frozen learner-output contract and contaminates the validation.

**I did not change it.** It is a shipped feature and the call is the project
owner's. Options: keep it out of the study client entirely; disable it for study
participants; or accept and document the exposure.

## 10. Browser and API integration

`deployment_api.py` provides `POST /api/tone-confirm/attempt`, deliberately
unmounted. `tests/test_deployment_inference_api.py` — **44 tests, all passing**
— drives the real request path.

| check | result |
|---|---|
| response shape is exactly `{status, message}` | all cases |
| status is PASS or RETRY | all cases |
| failures return HTTP 200 + RETRY, never 4xx/5xx | all cases |
| no forbidden term in any response | clean |
| no digit in any response | clean |
| research log retains the score server-side | yes, never crosses HTTP |
| research log carries all 14 required fields | yes |

**Browser format — BLOCKER.** The frontend records `audio/webm` (Opus).
libsndfile cannot decode WebM; ffmpeg is not on PATH; `av` and `imageio-ffmpeg`
are absent; `pydub`/`audioread` need an ffmpeg backend. The legacy analyser hits
the same wall (*"Send WAV audio for analysis"*).

An Ogg/Opus 48 kHz fixture — same codec, decodable container — decodes,
canonicalises to 16 kHz, and preserves the verdict in 4/4 cases under the
permissive profile. **The codec is fine; the container is unreadable.** See
`AUDIO_INPUT_CONTRACT.md` §8 for the two remediation options.

## 11. End-to-end robustness

Tolerances pre-registered before results were inspected.

| transformation | worst contour delta | tolerance | decisions |
|---|---|---|---|
| amplitude × 0.8 | 5.9e-09 ST | 0.05 | preserved |
| amplitude × 1.2 | 9.8e-09 ST | 0.05 | preserved |
| lossless WAV rewrite | 0.0 ST | 1e-09 | preserved |
| 44.1 kHz round trip | 0.0062 ST | 1.00 | preserved |
| 48 kHz round trip | 0.00027 ST | 1.00 | preserved |
| Opus 48 kHz browser-style | 0.385 ST | 3.00 | preserved |

All in-contract transformations hold. Out-of-contract padding is reported
separately (§3) and never upgrades a verdict to PASS.

**Determinism.** 10 repetitions: score delta 0.0, 0 verdict changes, 0 failure-
code changes. Process restart: identical `fitted_model_sha256`, score delta 0.0,
0 decision changes. Stress: 300 calls, 0 crashes, 0 instability, hash stable.

**Latency** (pre-segmented token already on disk; excludes capture, upload and
alignment): median 1.51 ms, IQR 1.20–1.74 ms, p95 2.31 ms. The 1.2 s per-call
refit is gone.

## 12. Fail-safe behaviour

**0 unsafe PASS** across 15 malformed-input cases plus 44 API tests. Silence,
empty, 10 ms, white noise, NaN, Inf, corrupted, unsupported, missing, stereo,
oversized, sub-16 kHz, non-native rate and every invalid tone form all resolve
to RETRY with a declared failure code. All failure codes come from the declared
vocabulary. Failure paths emit only the two frozen learner messages.

## 13. Final deployment verification matrix

`data/technical_verification/tv2_verification_matrix.csv` — 106 rows.

| category | checks | | category | checks |
|---|---|---|---|---|
| silence/boundary contract | 17 | | audio decoding | 5 |
| artifact identity | 17 | | legacy-route isolation | 4 |
| fail-safe | 15 | | API integration | 3 |
| frozen-scientific equivalence | 9 | | privacy | 3 |
| sample-rate handling | 9 | | determinism | 3 |
| expected-tone validation | 7 | | restart | 3 |
| policy | 5 | | stress | 3 |
| logging | 2 | | feature schema | 1 |

## 14. Human-exposure readiness

| criterion | status |
|---|---|
| scientific model equivalent on Train/Dev | MET |
| fitted model artefact uniquely hashable | MET |
| TV-F1 resolved under the enforced input contract | MET |
| TV-F2 resolved or strictly bounded by the contract | MET |
| TV-F3 fixed | MET |
| actual serving path verified | MET |
| **browser-like input path verified** | **UNMET** |
| **no active legacy decision path bypasses frozen inference** | **UNMET** |
| 0 unsafe PASS on malformed audio | MET |
| 0 decision nondeterminism | MET |
| startup fails closed on artefact mismatch | MET |
| learner response exposes no raw score or verdict | MET |

**Do not expose the system to teacher or student use.** Two blockers:

1. **WebM cannot be decoded.** The production upload physically cannot reach the
   model. Fix: ship ffmpeg, or capture 16 kHz PCM in the study client
   (recommended — it also satisfies the strict rate profile).
2. **A second pronunciation engine is live** and emits percentage scores and
   produced-tone diagnoses. Requires a product decision.

Neither is scientific. Neither requires re-validating the model.

## 15. OMPAL Test lock

| check | result |
|---|---|
| Test predictions | NO |
| Test scores | NO |
| Test metrics | NO |
| Test rows in feature cache | 0 |
| TV2 reference set ∩ Test | empty |
| inference bundle contains Test material | no |
| independent seal verifier | exit 0, SEALED |

## 16. Interpretation

> The production implementation is **not yet** technically ready for controlled
> human validation. The frozen scientific decision function is proven unchanged
> and is served correctly, deterministically and fail-safe; two deployment-layer
> blockers remain outside the model.

This says nothing about whether the pronunciation judgments are correct. Human
criterion validation remains required and remains postponed. The Phase D2 gate
is unchanged: `STUDY_START_READY = NO`.

---

*Artefacts: `data/technical_verification/` — `tv2_verification_matrix.csv`,
`tv2_summary.json`, `deployment_golden_reference.json`,
`frozen_inference_bundle.{npz,json}`, `tv2_metamorphic_results.csv`,
`tv2_failsafe_matrix.csv`. Code: `deployment_inference.py`,
`deployment_api.py`, `verify_deployment_inference.py`,
`tests/test_deployment_inference_api.py`.*
