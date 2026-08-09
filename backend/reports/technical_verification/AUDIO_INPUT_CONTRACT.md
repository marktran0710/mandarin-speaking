# Audio input contract — `OMPAL_AUDIO_CONTRACT_v1`

Applies to: `OMPAL_R2_PASS_v1` (scientific, frozen) served by
`OMPAL_R2_PASS_v1.1` (deployment implementation).

Every clause below is **derived from the pipeline that produced the frozen
training features**, not chosen for convenience. Where a bound is numeric, the
measurement that produced it is given. Nothing here claims robustness that
Phase TV2 did not verify.

---

## 1. Where this contract comes from

The frozen R2 features were built by this chain:

```
private-data/ompal/wav/SPEAKERxxxxx/xxxxxxxx.wav
  -> align_ompal_pilot.load_audio()
       sf.read(dtype="float32")
       mono by channel mean if multichannel
       scipy.signal.resample_poly to 16 kHz if rate != 16000
  -> torchaudio MMS_FA CTC forced alignment (with_star=True)
  -> token = audio[round(start*16000) : round(end*16000)]     boundary_policy=original_0ms
  -> sf.write(..., 16000)
  -> parselmouth.Sound(segment, 16000).to_pitch(0.005, 60, 500)
  -> 20-point time-normalised semitone trajectory, token-median centred
```

Measured over the corpus behind Train, Dev and native reference
(314 source utterances, none missing):

| split | utterances | sample rate | channels | subtype |
|---|---|---|---|---|
| train | 240 | 16000 (all) | 1 (all) | PCM_16 (all) |
| dev | 54 | 16000 (all) | 1 (all) | PCM_16 (all) |
| native_reference | 20 | 16000 (all) | 1 (all) | PCM_16 (all) |

**The `resample_poly` branch never fired during training.** Every frozen feature
comes from audio that was natively 16 kHz mono PCM_16. That single fact drives
most of this contract.

---

## 2. Supported format

| property | requirement |
|---|---|
| container/codec | anything libsndfile decodes (WAV, FLAC, OGG/Vorbis, OGG/Opus, AIFF, …) |
| **not** supported | **WebM** — see §8, open blocker |
| sample type | any; decoded to float32 |
| channels | 1 preferred; multichannel is downmixed by channel mean, exactly as training did |

## 3. Sample rate

Two profiles. The deployment default and the **required profile for the
validation study** is strict.

| profile | source rate | behaviour |
|---|---|---|
| **strict_native** (default) | exactly 16000 Hz | accepted, no resampling |
| strict_native | > 16000 Hz | **refused** — `sample_rate_not_native` |
| strict_native | < 16000 Hz | **refused** — `sample_rate_below_contract` |
| permissive_resample | ≥ 16000 Hz | resampled to 16 kHz with `resample_poly`, flagged `resampled=true` |
| permissive_resample | < 16000 Hz | **refused** — `sample_rate_below_contract` |

**Why strict is the default.** Resampling is not lossless for short tokens.
Measured across all 108 native-reference tokens at 44.1 and 48 kHz
(216 comparisons): 214 verdicts unchanged, **2 flipped**. Both flips were the
same 100 ms token whose voiced span is only 11 frames; its score moved
0.4082 → 0.4730 and crossed `t_pass = 0.42274`. Worst score delta 0.0649.

**Why sub-16 kHz is refused outright in both profiles.** Upsampling invents
bandwidth the model never saw. It was measured to flip a near-threshold verdict
and cannot be justified from the training contract.

Native 16 kHz input is unaffected by either gate: 0 refusals, 0 resampling,
deltas exactly 0.

## 4. Channel handling

Multichannel input is reduced to mono by **mean across channels** — the same
operation `align_ompal_pilot.load_audio` performed during training. No channel
selection, no weighting.

## 5. Expected segmentation state

**The frozen system consumes one already-segmented target token**, not a raw
recording.

| property | value |
|---|---|
| boundary source | torchaudio MMS_FA CTC forced alignment (with_star=True) |
| boundary policy | `original_0ms` — cut exactly at the alignment span, no padding |
| token duration envelope | 60 – 982 ms |

Two supported input modes:

* **`align`** *(recommended for production)* — supply the full utterance plus
  the syllable pinyin sequence and a token index. The deployment path reruns
  the same aligner with the same romanisation and the same integer rounding.
  Verified: reproduced boundaries for token `00100114_00` to **0.0 ms** on both
  the start and the end of the manifest-recorded span.
* **`pre_segmented`** — supply a token already cut by that aligner and policy.
  Provenance cannot be verified from the waveform; the caller attests it.

Duration outside 60–982 ms is refused with `token_duration_out_of_contract`.
That envelope is the measured min/max over the 1677 Train+Dev tokens that
produced the frozen features — a plausibility bound, not a trimming rule.

## 6. Allowed leading and trailing silence

**None may be added.** This is a provenance requirement, not an acoustic one.

The frozen tokens themselves *do* contain leading unvoiced material — measured
over 1677 Train+Dev tokens, leading unvoiced runs to a median of 35.6 ms, p95
125 ms and a maximum of 300 ms. So "no silence" is not the rule and cannot be
used as a detector.

The rule is that boundaries must come from the aligner. Adding 100 ms of
digital silence to an already-cut token changed the contour by up to 14.53
semitones in Phase TV, because the pitch tracker then reports extra voiced
frames and the contour is time-normalised across the voiced span. Under TV2's
enforced contract this remains out-of-contract input; it was verified that such
padding **never turns a RETRY into a PASS** (0 upgrades in 12 cases), and 1 of
12 decisions differed in the safe direction.

Do not trim silence to compensate. Any new trimming heuristic would change
trajectory computation and would require a **new scientific system version**.

## 7. Amplitude

No amplitude requirement. F0 extraction is amplitude-invariant in the frozen
configuration: amplitude × 0.8 and × 1.2 moved the contour by 5.9e-09 and
9.8e-09 semitones respectively, with 0 decision changes.

Clipped, very quiet and very loud audio are accepted and scored. Digital
silence, DC offset and unvoiced noise produce no trajectory and return RETRY.

## 8. Browser recording — OPEN BLOCKER

The frontend records with `MediaRecorder` at `audio/webm` (Opus), read from
`src/components/PhrasePracticeDrill.tsx`.

**The backend cannot decode WebM.** libsndfile does not list WEBM; `ffmpeg` is
not on PATH; `av` and `imageio-ffmpeg` are not installed; `pydub` and
`audioread` are present but both need an ffmpeg backend. The legacy
`praat_analyzer._load_sound` hits the same wall — its own error text says
*"Send WAV audio for analysis."*

Verified with an Ogg/Opus 48 kHz fixture (same codec, decodable container):
decode works, canonicalisation to 16 kHz works, and the verdict is preserved in
4/4 cases under the permissive profile. So the **codec** is not the problem; the
**container** is.

Two remediations, both a decision for the project owner:

1. Add ffmpeg to the deployment image and decode WebM → 16 kHz mono WAV at
   ingest. Keeps the current frontend, but then the study runs on the
   permissive profile with its measured ~1 % instability, plus Opus loss.
2. **Recommended for the study:** capture natively at 16 kHz PCM in the study
   client (WebAudio `AudioContext({sampleRate: 16000})` + manual WAV encode).
   This satisfies the strict profile, removes resampling and Opus entirely, and
   reproduces the training condition exactly.

## 9. Trajectory-unavailable behaviour

If no usable trajectory can be built, the result is **always RETRY** — never
PASS, never an error shown to the learner.

| condition | failure code |
|---|---|
| < 30 ms of audio | `too_short_for_pitch` |
| fewer than 3 voiced frames | `insufficient_voiced_frames` |
| Praat raised | `praat_error` |
| non-finite trajectory values | `non_finite_trajectory` |

## 10. Malformed-input behaviour

Every one of these returns HTTP 200 with `{"status": "RETRY"}` and the ordinary
retry message. The learner cannot tell a technical failure from a
low-confidence attempt — which is the frozen contract: RETRY means "not
confirmed", never "wrong".

| input | failure code |
|---|---|
| unreadable / corrupted / unsupported / missing file | `unreadable_audio` |
| zero-length decode | `empty_audio` |
| rate below 16 kHz | `sample_rate_below_contract` |
| resampled rate under the strict profile | `sample_rate_not_native` |
| token outside 60–982 ms | `token_duration_out_of_contract` |
| expected tone not one of `1`–`4` / `T1`–`T4` | `invalid_expected_tone` |
| anything unanticipated | `unhandled_exception` |

Verified: **0 unsafe PASS** across 15 malformed-input cases and 44 API tests.

## 11. Expected tone

Accepted: `"1"`, `"2"`, `"3"`, `"4"`, `"T1"`, `"T2"`, `"T3"`, `"T4"`
(case-insensitive, surrounding whitespace stripped), normalised to the frozen
internal label `"1"`–`"4"`.

Rejected before any feature is built: `None`, any int, any float, `bool`,
`bytes`, list, dict, arbitrary objects, `""`, `"0"`, `"5"`, `"T5"`, `"two"`.

Validation changes no valid input's score (max delta 0.0 across the reference
set).

## 12. Operational constraint — aligner process isolation

The forced aligner must run in its **own process, started cold**. Loading torch
into an interpreter that has already exercised numpy/scipy/sklearn/parselmouth
faults with `0xC0000005` on this platform regardless of environment variables.
Segmentation therefore belongs in a dedicated worker, not in the request
handler.

## 13. What this contract does not claim

It does not claim the system judges pronunciation correctly. It constrains the
inputs so that the frozen model is asked the same question it was fitted to
answer. Human criterion validation is still required and is still postponed.
