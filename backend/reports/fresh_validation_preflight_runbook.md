# Fresh validation — preflight runbook (Phase D0)

Run `python -m pronunciation.wav2vec_tone.preflight_fresh_validation` before any
recruitment, and again at the start of each recording day.

**No participant data was collected and no validation outcome was simulated.**
The dry run below uses OMPAL native-reference audio (outside the learner
benchmark) plus a constructed silent clip. All artefacts land in
`data/preflight/`, every row carries `IS_PREFLIGHT=YES`, and none of it may
enter `fresh_validation_trials.csv` or any human-validity estimate.

## What it verifies — 19 checks, all passing

### Frozen system

Recomputes the sha256 of `fresh_validation_system_FROZEN.json` and compares it
to the recorded value (`8101bcaf8c92e1e3…`). On mismatch the script **exits with
`STOP VALIDATION SESSION`** rather than continuing — a changed artefact means
the thing under test is not the thing that was frozen.

### Technical chain — one trial per tone, plus a forced failure

| trial | tone | trajectory | score | decision | reason | latency |
|---|---|---|---|---|---|---|
| PF01 | T1 | yes | 0.4185 | RETRY | tone_not_enabled | 1315 ms |
| PF02 | T2 | yes | 0.4118 | PASS | score_below_threshold | 13.5 ms |
| PF03 | T3 | yes | 0.5143 | RETRY | score_above_threshold | 12.7 ms |
| PF04 | T4 | yes | 0.4082 | PASS | score_below_threshold | 11.6 ms |
| PF05 | — | **no** | — | RETRY | trajectory_unavailable | 1.3 ms |

Two rows are worth noting:

- **PF01 scored 0.4185, below `t_pass = 0.4227`.** It would have PASSed on
  score alone and was withheld purely by the T1 gate. The gate is doing real
  work, not duplicating the threshold.
- **PF03 is a native production that did not PASS.** A concrete instance of the
  low coverage the study will measure — RETRY does not mean the production was
  wrong.

### Policy invariants

- T1 → RETRY regardless of acoustics.
- Trajectory unavailable → RETRY, never PASS.
- Only `PASS` / `RETRY` are ever emitted.

### Learner-facing wording

```
PASS  → "Your tone sounds acceptable. You can continue."
RETRY → "I'm not confident enough to confirm this attempt. Please try once more."
```

Checked against `wrong`, `incorrect`, `instead of`, `%`, `score`, `percent` —
none present. Separately asserted: **no digit appears in any learner message**,
so the raw score cannot leak numerically.

### Rater blinding

The generated export carries no `system_decision`, no `r2_raw_score`, no
`participant_id`, no other-rater field, and no OMPAL result.

### Randomisation

The first implementation shuffled with random restarts and left **93 of 399**
adjacent pairs sharing a tone (~23%) — random shuffling cannot beat the ~25%
same-tone floor with four tones, so the check was correctly failing on a real
weakness. **The scheduler was fixed rather than the check relaxed.** The order
is now constructed: at each step take a trial differing from the previous in
both learner and tone, preferring the largest remaining bucket so the tail
cannot dead-end, relaxing tone before speaker only if nothing qualifies.

Result: **0/399 adjacent same-learner pairs, 0/399 adjacent same-tone pairs.**
Seed `20260808` recorded. The assertion was then tightened from ≤15% to ≤2%.

### Duplicate QC

30 of 400 = **7.5%**, inside the 5–10% band, carrying ordinary sequential
rating ids so they are indistinguishable to a rater.

### Analysis pipeline

Verified by inspection of `analyze_fresh_human_validation.py`: restricted to
first attempts; pre-registered consensus rule present; duplicates excluded from
the primary denominator; cluster bootstrap over participants; the 0.90 target
hard-coded rather than parameterised; and — asserted — **no model import and no
`.fit(` call anywhere in the file**, so validation labels cannot reach the
model. The script also exits cleanly with an explanatory message when no data
file exists, so it cannot emit placeholder results.

## Latency — liveness only

Median 12.7 ms, min 1.3 ms, max 1315 ms across five preflight trials. The
maximum is first-call warm-up (model construction), not steady state.

**This is not a real-world latency estimate.** It excludes microphone capture,
upload, decoding and UI rendering, and runs on pre-extracted audio on a
developer machine. Real end-to-end latency must be measured during the study
via `processing_latency_ms`, and reported as median / IQR / p95.

## Environment recorded

Python 3.12.0, numpy 2.4.3, seed 20260808. OMPAL Test predictions, scores and
metrics all confirmed **absent** — the test set remains sealed.

## Per-session procedure

1. Run the preflight. If the hash check fails, **stop and investigate** — do
   not record.
2. Confirm 19/19 checks pass and `n_failed == 0`.
3. Record in the session log: `system_version`, `system_hash`, date/time,
   device and microphone, app version, processing environment.
4. Confirm `data/preflight/` output is not being written into, or merged with,
   the study data directory.
