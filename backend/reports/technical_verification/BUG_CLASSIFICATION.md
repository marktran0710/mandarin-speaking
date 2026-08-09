# Phase TV — issue classification

Every issue found during technical verification of `OMPAL_R2_PASS_v1` is
classified as **implementation bug** or **scientific/model limitation**. Neither
is silently treated as the other.

**Nothing in this document was fixed in code.** Every candidate fix either
touches the frozen chain (forbidden without a new system version) or belongs in
a not-yet-existing serving layer. The frozen artefacts are byte-identical to
what they were before this run.

Definitions used:

- **Implementation bug** — the code does not do what the frozen spec already
  says it should. Fixable now, because fixing it *restores* frozen behaviour.
- **Scientific/model limitation** — the code does exactly what the frozen spec
  says; the spec itself has a consequence. Cannot be "fixed" without changing
  the model, which requires a new system version and a new validation set.

---

## TV-F1 — sample rate is read and discarded

**Test** TV073 · **Severity** HIGH · **Classification** IMPLEMENTATION BUG
(missing input validation) — *does not require a new system version*

`trajectory_from_segment()` hardcodes `SAMPLE_RATE = 16000`. Every call site
reads audio with `audio, _ = sf.read(...)` and throws the returned rate away.
Praat is therefore told the audio is 16 kHz whatever it actually is.

Measured on one native-reference token, same speech, genuinely resampled:

| actual rate | raw score | decision effect |
|---|---|---|
| 16 000 Hz (baseline) | 0.418525 | — |
| 8 000 Hz | 0.443864 | contour shifted up to 1.98 ST |
| 44 100 Hz | 0.415709 | contour shifted up to 1.05 ST |
| 48 000 Hz | **0.656886** | contour shifted up to 3.56 ST |

At 48 kHz the score crosses `t_pass = 0.42274`, so the same utterance flips from
PASS to RETRY purely because of the container rate.

Why it is an implementation bug and not a model limitation: the frozen
representation *specifies* a 16 kHz input. The code does not enforce the
specification it already has. Adding a rate check restores intended behaviour.

**Why this is urgent for the postponed study:** browser `MediaRecorder` and most
phone capture default to 44.1 or 48 kHz. If the fresh-validation capture path
delivers anything other than 16 kHz, the study measures a different system than
the one that was frozen.

**Allowed fix** (serving/ingest layer, outside the frozen chain): validate the
declared rate at ingest and reject or explicitly resample to 16 kHz before the
audio reaches `trajectory_from_segment`.

**Not allowed without a new version:** changing `SAMPLE_RATE`, adding
resampling *inside* the trajectory function, or changing the pitch floor and
ceiling to compensate.

---

## TV-F2 — the contour is anchored to redetected voiced-span edges

**Tests** TV078 / TV079 / TV080, mechanism isolated by TV084 / TV085 / TV086
**Severity** HIGH · **Classification** SCIENTIFIC / MODEL LIMITATION —
*cannot be fixed without a new system version*

Adding 100 ms of digital silence to a token — a transformation that changes no
speech content — moved the contour by up to **14.53 ST** and flipped one
PASS/RETRY decision.

Mechanism, isolated:

| padding cases | voiced span | worst contour delta |
|---|---|---|
| 3 / 12 | unchanged | 0.0065 ST |
| 9 / 12 | changed | 14.53 ST |

All 9 span changes were caused by the pitch tracker returning *extra* voiced
frames. Example: 23 → 29 voiced frames, first voiced F0 189 → 354 Hz (an octave
artefact at the silence/speech onset). Because the frozen representation
time-normalises across the voiced span and centres on the token median, one
spurious edge frame rescales the entire time axis and injects an outlier.

The trajectory code is **arithmetically correct** — TV046 reproduces it exactly
from an independent re-derivation. The sensitivity is a property of the frozen
representation, not a coding error. That is precisely why it cannot be fixed
here: trimming silence, gating edge frames, or anchoring the time axis
differently would all change trajectory computation.

**Consequence to carry into the study, not a code change:** the frozen system is
only defined for tokens produced by the same forced aligner and the same
boundary policy as Train. Segmentation is part of the frozen system even though
it sits outside the model.

**If someone later decides to change it:** STOP. New system version, re-freeze,
new independent validation set, re-run D0.

---

## TV-F3 — expected tone accepted as a non-string

**Test** TV059 · **Severity** MEDIUM · **Classification** IMPLEMENTATION BUG
(missing input validation) — *does not require a new system version*

`design()` compares tone labels as strings (`tones == "2"`). Passing the integer
`2` matches nothing, so all three dummies stay `[0, 0, 0]` and the utterance is
scored **as if it were T1** — silently, with no error.

Today this fails safe by coincidence rather than by design: the policy layer
refuses PASS because `2 not in {"2", "3", "4"}` (TV060 confirms RETRY). The
safety therefore depends on two independent components disagreeing about types
in exactly the right direction. Nothing enforces that coupling, and a future
caller that normalises the enabled-tone set to integers would produce a T1-scored
PASS.

**Allowed fix** (serving layer): validate `expected_tone ∈ {"1","2","3","4"}` at
the entry point and raise or return a hard failure otherwise.

---

## Non-issues, recorded so they are not rediscovered

**Solver seed.** The D0 preflight runs with seed 20260808 while the C8 policy
was derived with seed 0. Scores are bit-identical (TV016) — the frozen
configuration uses lbfgs, for which `random_state` is unused. Not a defect.

**Dead guard at `phase_c6_f0_trajectory.py:202.** `if any(...) and False: pass`
is unreachable code sitting beside the live TEST LOCK guard at lines 204–205.
The live guard and the cache guard both work; the seal verifier passes 5/5.
Cosmetic only, and it lives inside the frozen chain, so it was left alone.

**All-NaN feature row scores instead of failing.** The median imputer inside
`fit_predict` replaces an all-NaN row with Train medians and returns 0.494891.
This is correct behaviour for the imputer; the availability guard upstream is
what prevents it becoming a verdict (TV104). Recorded because any future caller
that skips that guard loses the protection.

---

## Operational note on artefact binding

The recorded C8 `model_hash` is `sha256({C, class_weight, points})` — the
training *configuration*, not the training data or the fitted weights. It would
not detect a swapped feature cache, an altered Train split, or a different
trajectory cache.

There is also **no persisted model artefact**: the classifier is refitted from
`dev_features_train_dev.npz` + `phase_c6_trajectories.npz` on every process
start (1.21 s). Reproducibility therefore rests entirely on those two caches
staying byte-identical.

Not a defect in itself, and deliberately not changed. Mitigated instead by
recording genuine content hashes in `golden_reference.json`:

```
train_trajectory_sha256, train_tone_sha256, train_label_sha256,
manifest_split_sha256, feature_cache_sha256, trajectory_cache_sha256,
model_coefficient_sha256 = bce84b07cc594bb5...
```

Re-running `verify_frozen_system.py` after any future software change will
detect drift in any of them.

---

## Summary

| id | severity | classification | blocks human study? |
|---|---|---|---|
| TV-F1 sample rate discarded | HIGH | implementation bug | yes — fix the capture/ingest path first |
| TV-F2 voiced-span anchoring | HIGH | model limitation | no — but the study must reuse the Train boundary policy |
| TV-F3 non-string expected tone | MEDIUM | implementation bug | no — fails safe today, fix before serving |

No issue found in this phase required a change to `t_pass`, `C`, the features,
the F0 settings, or the decision logic. The frozen system is unmodified.
