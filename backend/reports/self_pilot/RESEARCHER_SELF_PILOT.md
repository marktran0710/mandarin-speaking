# Researcher self-pilot — status report

**System** `OMPAL_R2_PASS_v1` (scientific, frozen) served by `OMPAL_R2_PASS_v1.1`
**fitted_model_sha256** `0dcee1d87c69c5b2586fa9612b142a6ac5ef48cd37cd06dfac984a5d463c586c` — unchanged
**Date** 2026-08-09
**Verdict** **B. RESEARCHER SELF-PILOT FOUND TECHNICAL/WORKFLOW ISSUES — FIX BEFORE HUMAN VALIDATION**

The verdict label is imperfect and I want to be exact about why it was chosen.
The harness found **no defects** — 32/32 checks pass. It is B because **Runs A,
B and C have not been performed**. They need the researcher's own voice, and I
have no microphone and am not the researcher. A would assert that a self-pilot
passed when its three substantive runs never happened.

---

## What was built

| deliverable | purpose |
|---|---|
| `pronunciation/wav2vec_tone/self_pilot.py` | namespace, 16 prompts, fixed Run C plan, trial schema, metric guard |
| `routers/self_pilot.py` | `/api/self-pilot/*` — same frozen engine, separate log |
| `src/study/SelfPilotRunner.tsx` | researcher runner UI for Runs A / B / C |
| `pronunciation/wav2vec_tone/export_self_pilot.py` | descriptive summary; refuses validity statistics |
| `pronunciation/wav2vec_tone/verify_self_pilot_harness.py` | the voice-free checks, executed below |
| `reports/self_pilot/SELF_PILOT_CHECKLIST.md` | run sheet the researcher follows |

The scientific path is untouched: the self-pilot route calls the same
`infer_tone_attempt` as the study route. Only the log destination differs.

## What was executed

32 harness checks, **all passing**. 19 technical rows written, all
`run = T_technical`, all flagged `PILOT_ONLY=YES` / `RESEARCHER_SELF_TEST=YES`.

### Section 7 — T1 gate

| check | result |
|---|---|
| three synthetic T1 probes | RETRY, RETRY, RETRY (internal 0.4625) |
| **a real T1 token scoring 0.418525 — below `t_pass` 0.42274** | **RETRY** |

The second row is the one that matters. My first version of this check only used
synthetic probes that scored *above* the threshold, so the threshold alone would
have refused them and the gate was never exercised. Replacing them with a
native-reference T1 token whose score sits below `t_pass` proves the **gate**,
not the threshold, is what refuses it. 0 T1 gate violations.

### Section 8 — failure paths

| case | outcome | code |
|---|---|---|
| silence | RETRY | `insufficient_voiced_frames` |
| empty recording | RETRY | `unreadable_audio` |
| very short recording | RETRY | `token_duration_out_of_contract` |
| stopped too early | RETRY | `token_duration_out_of_contract` |
| invalid expected tone | RETRY | `invalid_expected_tone` |
| missing expected tone | RETRY | `invalid_expected_tone` |
| microphone denied (empty capture) | RETRY | `unreadable_audio` |
| corrupted payload | RETRY | `unreadable_audio` |

**0 unsafe PASS.** Every case returned HTTP 200 with a neutral technical
message; none implied a pronunciation error.

### Determinism, logging, isolation

* identical input, 5 calls → 1 distinct decision, internal score delta `0.000e+00`
* repeat attempts append rather than replace: 16 → 18 rows, distinct trial ids
* 18 audio files, 18 unique names, all prefixed `PILOT_ONLY_`
* every row carries both pilot flags; the schema has all 10 required fields
* the validity-metric guard rejects `pass_precision`, `accuracy`, `kappa`,
  `sensitivity`, `specificity`, `f1_score` (6/6)
* **0 fresh-validation artefacts changed**; `fresh_validation_items_FROZEN.csv`
  is still absent — creating it would fabricate a teacher approval that does
  not exist

## Descriptive counts so far

From `data/self_pilot/self_pilot_summary.json` — technical rows only, **not
accuracy**:

| | |
|---|---|
| total recordings | 19 (all `T_technical`) |
| trajectory available / not | 11 / 8 |
| PASS / RETRY | 7 / 12 *(descriptive workflow counts only)* |
| T1 gate violations | **0** |
| unsafe PASS | **0** |
| technical failures | `unreadable_audio` 3, `token_duration_out_of_contract` 2, `invalid_expected_tone` 2, `insufficient_voiced_frames` 1 |
| latency (median / p95) | 3.2 ms / 6.6 ms *(server-side inference only)* |

The PASS/RETRY split above comes from synthetic buzz tones and deliberate
failure cases. It says nothing about pronunciation and must not be quoted as a
rate.

## What is outstanding

| run | recordings | status |
|---|---|---|
| A — natural production | 16 | **not started** |
| B — repeat | 16 | **not started** |
| C — deliberate challenge | 6 | **not started** |
| experience checklist | 11 questions | **not answered** |

I did not simulate them. Synthesised audio is not a researcher production, and
writing it into the self-pilot log as though it were would fabricate exactly the
thing the self-pilot exists to obtain. `SP032` records this explicitly.

## UI issues found by code review

Found by reading the study components, before any recording. All are wording,
layout or button behaviour — none touches the model, so all are permitted fixes.

1. **No recording-duration feedback.** `ToneAttemptPanel` offers only
   Record/Stop: no timer, no level meter. Stopping early is easy, and the
   frozen 60 ms floor then returns a technical message that does not say why.
   This is the most likely source of avoidable RETRYs in Run A.
2. **No microphone level indicator.** A muted or dead microphone looks
   identical to a quiet room until the attempt has already been spent.
3. **Weak recording-state signal in the participant panel.** `SelfPilotRunner`
   shows "● Recording — speak now"; `ToneAttemptPanel` changes only the button
   label. The participant panel should match.
4. **話 and 電 presented alone.** Already flagged as needing a teacher decision
   on isolated versus in-word presentation; Run A should note whether they feel
   awkward, for the teacher packet.
5. **No per-item progress indicator** in the participant panel.

None of these was fixed in this phase: items 1–3 change what the researcher
experiences during Runs A–C, so changing them now and then running the pilot
would rehearse a UI that no longer exists. They are listed for a decision
before the runs.

## Boundaries honoured

* frozen scientific model, `t_pass`, trajectory, T1 gate, tone policy, audio
  contract, study recorder and API route: **unchanged**
* `fitted_model_sha256` identical to TV2/TV3
* no fresh-validation dataset modified
* OMPAL Test not opened
* no accuracy, PASS precision, sensitivity, specificity, agreement or kappa
  computed — the exporter raises `ValidityMetricRefused` if a future edit tries

## Next step

Run the checklist. It is a single sitting: 16 + 16 + 6 recordings plus 11
questions. Then re-run:

```bash
python -m pronunciation.wav2vec_tone.export_self_pilot
```

and confirm `t1_gate_violations == 0` and `unsafe_pass_count == 0` across the
researcher's own recordings. At that point the verdict can be revisited.

---

*Artefacts: `data/self_pilot/self_pilot_trials.csv`,
`self_pilot_summary.json`, `self_pilot_harness_report.json`,
`self_pilot_harness_matrix.csv`, `audio/PILOT_ONLY_*.wav`.*
