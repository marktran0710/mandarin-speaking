# Study audio capture contract — `STUDY_PCM16K_v1`

Companion to `reports/technical_verification/AUDIO_INPUT_CONTRACT.md`. That
document defines what the **backend accepts**; this one defines what the
**study client produces** and how it gets there.

Applies to: `OMPAL_R2_PASS_v1` (scientific, frozen) served by
`OMPAL_R2_PASS_v1.1` under `OMPAL_AUDIO_CONTRACT_v1`.

---

## 1. Output contract

Every study attempt reaching the API is:

| property | value |
|---|---|
| container | WAV (RIFF), 44-byte canonical header |
| encoding | signed 16-bit PCM, little endian |
| sample rate | 16000 Hz |
| channels | 1 |
| samples | finite; clamped to [-1, 1] before quantisation |
| duration | known and reported by the client |

Nothing lossy is used at any stage. MediaRecorder and WebM/Opus are **not** part
of this path.

## 2. Why not MediaRecorder

The existing app records `audio/webm` (Opus) in five components. Phase TV2
established that the validated backend cannot decode WebM at all, and that Opus
is lossy. The study path therefore captures raw PCM through WebAudio instead.
The legacy recorders are untouched; they serve other features.

## 3. Where resampling happens — stated plainly

The microphone and the browser audio graph run at the **hardware rate**. Measured
in the validated browser: `AudioContext.sampleRate` = **48000 Hz** (Chrome 150,
Windows 11).

**The physical microphone does not produce 16 kHz.** Nothing in this project
claims it does.

The conversion is:

```
microphone (hardware rate, typically 48000 Hz)
  -> AudioWorklet PCM capture at AudioContext.sampleRate   [no conversion]
  -> STUDY_PCM16K_v1 conversion in src/study/pcm16k.ts     [the ONE conversion]
  -> 16-bit PCM WAV at 16000 Hz
  -> upload
  -> backend strict_native accepts, resamples nothing      [no second conversion]
```

We deliberately do **not** construct `new AudioContext({sampleRate: 16000})`.
That would hand the conversion to each browser's internal resampler, and
different browsers would then produce different waveforms from the same speech —
exactly the failure mode this contract exists to prevent.

## 4. Exactly one conversion implementation

`STUDY_PCM16K_v1` is specified once and implemented twice:

* `src/study/pcm16k.ts` — runs in the participant's browser
* `backend/pronunciation/wav2vec_tone/study_pcm16k.py` — the verification mirror

Specification:

| parameter | value |
|---|---|
| target rate | 16000 Hz |
| identity rule | source rate == 16000 → samples pass through **untouched** |
| ratio | L/M reduced by `gcd(16000, source_rate)` |
| filter | Blackman-windowed sinc, linear phase |
| cutoff | `0.5 / max(L, M)` normalised to the upsampled rate |
| taps | `2 * (16 * max(L, M)) + 1` |
| gain | L |
| evaluation | polyphase; only non-zero upsampled taps are touched |
| edge handling | source index clamped to `[0, n-1]` (constant extension) |

Blackman rather than Kaiser deliberately: no modified Bessel function is
required, so the two implementations cannot drift through a different `I0`
approximation.

**Verified identical across three engines.** The same four vectors were run in
Chrome V8 150, Node V8 (vitest) and CPython 3.12. Quantised PCM checksums:

| vector | Chrome | Python | |
|---|---|---|---|
| identity_16k | −2072182784 | −2072182784 | match |
| from_48k | −1075798195 | −1075798195 | match |
| from_44100 | 996538447 | 996538447 | match |
| short_80ms_48k | 429885382 | 429885382 | match |

Float agreement: max delta `1.11e-16`. Quantised samples: **0 differing**.

## 5. No header relabelling

Capturing at 48 kHz and simply labelling the bytes 16 kHz would make the
waveform play three times too slowly and would destroy every tone contour. The
conversion changes the sample count, and duration is asserted on both sides:

| source | input frames | output frames | input ms | output ms |
|---|---|---|---|---|
| 48000 Hz, 0.25 s | 12000 | 4000 | 250.0 | 250.0 |
| 44100 Hz, 0.2 s | 8820 | 3200 | 200.0 | 200.0 |
| 16000 Hz, 0.1 s | 1600 | 1600 | 100.0 | 100.0 (identity) |

Worst duration drift across 9 rate × duration combinations: **0.0000 ms**.

## 6. No double resampling

The client emits 16 kHz; the backend runs the `strict_native` profile, which
**refuses** anything that would require resampling (`sample_rate_not_native`).
Verified end to end: a study-converted upload reports
`source_sample_rate = 16000, resampled = False, rate_profile = strict_native`.

Every inference records `capture_sample_rate`, `pcm_spec_version`,
`source_sample_rate` and `resampled`, so any inconsistency is detectable in the
research log rather than silent.

## 7. Recording lifecycle

```
getUserMedia({ audio: { channelCount: 1,
                        echoCancellation: false,
                        noiseSuppression: false,
                        autoGainControl: false } })
  -> AudioContext (hardware rate)
  -> MediaStreamAudioSourceNode
  -> AudioWorkletNode 'study-capture'   (ScriptProcessor fallback)
  -> Float32 chunks accumulated in the page
  -> stop(): concatenate -> buildStudyWav -> Blob
  -> POST multipart to /api/pronunciation/tone-attempt
```

Browser DSP (echo cancellation, noise suppression, auto gain) is switched off:
the frozen model was fitted on unprocessed corpus audio and none of those
filters were part of it.

## 8. UI gating

The only client-side gate is technical: **did the capture produce any frames?**
An empty capture yields the neutral technical message and is not submitted.

There is deliberately **no** duration threshold, loudness threshold or quality
heuristic in the client. Inventing one would add a pronunciation-quality rule
that was never frozen scientifically. A 40 ms capture is still submitted, and
the backend's frozen 60–982 ms envelope — measured from the training tokens —
decides it.

## 9. Validated environment

| | |
|---|---|
| validated browser | **Chrome 150, Windows 11** |
| observed `AudioContext.sampleRate` | 48000 Hz |
| not validated | Firefox, Safari, Edge, any mobile browser |

Cross-browser support is **not** claimed. The study protocol must restrict
participants to the validated browser, or a browser must be added to this table
only after the harness has been run on it.

Recommended controlled-study hardware envelope, given that device variation was
not validated broadly:

* one lab computer category, one validated microphone model
* the validated browser
* a quiet room
* the same capture settings for every participant

The first human study is legitimately a **controlled** deployment validation,
not a claim of general-device robustness.

## 10. Fixtures

Technical fixtures produced through this exact path live in
`data/technical_verification/tv3_browser_fixtures/` and are named
`PREFLIGHT_ONLY_*`. They cover T1–T4, silence, very short speech and a technical
failure. They may **never** enter human-validation analysis.

## 11. What this contract does not claim

It constrains capture so the frozen model is asked the same question it was
fitted to answer. It says nothing about whether the resulting judgments are
correct. Human criterion validation remains required.
