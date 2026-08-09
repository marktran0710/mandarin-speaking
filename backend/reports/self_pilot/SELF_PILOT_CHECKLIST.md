# Researcher self-pilot — run sheet and checklist

**System** `OMPAL_R2_PASS_v1.1` · `fitted_model_sha256 0dcee1d87c69c5b2…`
**Status** harness verified (32/32); **Runs A, B and C outstanding**

This is a workflow rehearsal. Nothing recorded here may be used for accuracy,
PASS precision, sensitivity, specificity, agreement or kappa — the researcher is
not an independent criterion. The 16 items are still awaiting teacher review;
running them here is **not** item approval and does not advance the D2 gate.

---

## Before you start

```bash
# 1. backend in study mode (pick a free port; 8000 may already be in use)
cd backend
OMPAL_STUDY_MODE=1 python -m uvicorn main:app --port 8010

# 2. frontend
npm run dev

# 3. confirm the frozen identity before recording anything
curl http://127.0.0.1:8010/api/pronunciation/tone-attempt/health
```

Expected health response:

```json
{"ready": true,
 "scientific_version": "OMPAL_R2_PASS_v1",
 "deployment_version": "OMPAL_R2_PASS_v1.1",
 "audio_contract_version": "OMPAL_AUDIO_CONTRACT_v1",
 "fitted_model_sha256": "0dcee1d87c69c5b2586fa9612b142a6ac5ef48cd37cd06dfac984a5d463c586c"}
```

If the hash differs, **stop** — do not record.

Environment must match the validated envelope: **Chrome 150 on Windows 11**,
validated microphone, quiet room. Nothing else was verified.

---

## Run A — natural production (16 recordings)

One first attempt per item, recorded naturally. Do not retry to "get a PASS" —
the first attempt is the trial.

| # | item | character | pinyin | tone | done | notes |
|---|---|---|---|---|---|---|
| 1 | I01 | 貓 | māo | T1 | ☐ | |
| 2 | I02 | 高 | gāo | T1 | ☐ | |
| 3 | I03 | 天 | tiān | T1 | ☐ | |
| 4 | I04 | 花 | huā | T1 | ☐ | |
| 5 | I05 | 人 | rén | T2 | ☐ | |
| 6 | I06 | 門 | mén | T2 | ☐ | |
| 7 | I07 | 茶 | chá | T2 | ☐ | |
| 8 | I08 | 魚 | yú | T2 | ☐ | |
| 9 | I09 | 狗 | gǒu | T3 | ☐ | |
| 10 | I10 | 水 | shuǐ | T3 | ☐ | |
| 11 | I11 | 馬 | mǎ | T3 | ☐ | |
| 12 | I12 | 筆 | bǐ | T3 | ☐ | |
| 13 | I13 | 飯 | fàn | T4 | ☐ | |
| 14 | I14 | 話 | huà | T4 | ☐ | |
| 15 | I15 | 菜 | cài | T4 | ☐ | |
| 16 | I16 | 電 | diàn | T4 | ☐ | |

## Run B — repeat (16 recordings)

The same 16 prompts again, recorded the same way. Purpose: exercise the repeat
workflow, confirm nothing overwrites, and see whether any recording is wildly
unstable.

Agreement between your two repetitions is **not** model accuracy. It is you,
twice.

## Run C — deliberate challenge (6 recordings)

Fixed in advance so nothing is improvised mid-run. These are diagnostic probes,
**not** verified Mandarin tone errors.

| item | target | manipulation | done |
|---|---|---|---|
| I05 人 | T2 | say it with a **level** contour instead of rising | ☐ |
| I07 茶 | T2 | say it with a **falling** contour instead of rising | ☐ |
| I09 狗 | T3 | say it with a **rising** contour instead of dipping | ☐ |
| I11 馬 | T3 | say it with a **level** contour instead of dipping | ☐ |
| I13 飯 | T4 | say it with a **level** contour instead of falling | ☐ |
| I16 電 | T4 | say it with a **rising** contour instead of falling | ☐ |

The question is only: *does the system react in a technically plausible way?*
Do not compute accuracy from these.

---

## Experience checklist

Answer after finishing all three runs. These drive **logistics and wording
only** — never model behaviour.

| question | answer |
|---|---|
| Was the recording button clear? | |
| Was it obvious when recording started and stopped? | |
| Was the PASS message understandable? | |
| Was the RETRY message understandable? | |
| **Did RETRY feel like "you said it wrong", despite the neutral wording?** | |
| Was retrying easy? | |
| Were any responses unexpectedly slow? | |
| Did any item cause confusion? | |
| Were 話 or 電 awkward shown alone, without context? | |
| Was anything about the T3 prompts confusing? | |
| Did any trial need manual recovery? | |

The RETRY question is the important one. The whole policy rests on RETRY meaning
"not confirmed", not "wrong". If it does not land that way for you, it will not
land for a learner, and the wording — not the model — must change.

---

## Known gaps found by code review (before you run)

These are UI issues found by reading the study components. Fixing them is
allowed (wording, layout, button behaviour); none touches the model.

1. **No recording-duration feedback.** `ToneAttemptPanel` shows only a
   Record/Stop button. There is no timer and no level meter, so it is easy to
   stop too early. The frozen contract refuses tokens below 60 ms with a
   technical message that does not explain the cause.
2. **No microphone level indicator.** A dead or muted microphone is
   indistinguishable from a quiet room until after the attempt.
3. **`ToneAttemptPanel` has no visible recording state beyond the button
   label.** `SelfPilotRunner` adds an explicit "● Recording — speak now"
   status; the participant panel should get the same treatment.
4. **`話` and `電` shown alone** are the two items already flagged as needing a
   teacher decision on isolated vs in-word presentation. Note during Run A
   whether they feel awkward, and record it for the teacher packet.
5. **No per-item progress indicator** in the participant panel.

---

## After the runs

```bash
cd backend
python -m pronunciation.wav2vec_tone.export_self_pilot
```

Then check, in `data/self_pilot/self_pilot_summary.json`:

* `safety.t1_gate_violations` == 0 — **any T1 PASS is a technical failure**
* `safety.unsafe_pass_count` == 0
* `processing.technical_failures` — any unexpected code
* `totals.per_run` — 16 / 16 / 6 as planned

If a discovered issue would require changing the model, the threshold, the F0
settings, the tone gate or the decision rule: **stop** and report it as a
system-version issue. It is not a self-pilot fix.
