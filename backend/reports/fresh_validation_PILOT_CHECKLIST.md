# Operational pilot — mandatory before recruitment

**2–3 lab members or non-study volunteers.** They are recorded with
`participant_id = PILOT01`, `PILOT02`, `PILOT03` and `pilot_only = YES`.

**Pilot data never enters the validation analysis** — not as participants, not
as a sanity check on precision, not as a supplementary sample. Pilot recordings
may be reused as rater *training* material, which is their only downstream use.

Pilot participants must not be people who will later take part as learners.

## What the pilot is for

Logistics and interface only. It answers "does the session run", not "does the
system work".

| # | goal | how it is confirmed | status |
|---|---|---|---|
| 1 | recording works | 16 non-empty audio files per pilot participant, all play back | ☐ |
| 2 | instructions understood | pilot participant can explain, unprompted, that RETRY does not mean wrong | ☐ |
| 3 | 16 trials manageable | session completes within ~20 min without fatigue complaints | ☐ |
| 4 | PASS/RETRY wording understandable | pilot participant reports both messages as clear; no one reads RETRY as "incorrect" | ☐ |
| 5 | data paths correct | files land in the study directory, named as specified, nothing in `data/preflight/` | ☐ |
| 6 | latency logging works | `processing_latency_ms` populated and plausible for every attempt | ☐ |
| 7 | usability form works | responses saved and readable | ☐ |
| 8 | rater export can be generated | blinded export builds from pilot rows and contains no system decision, score, or participant id | ☐ |
| 9 | item order applied | delivered sequence matches the assigned `order_id` exactly | ☐ |
| 10 | first/retry logging correct | `first_attempt` and `attempt_number` correct on every row | ☐ |
| 11 | technical failure path | one deliberately aborted or silent recording produces RETRY with a failure reason, never PASS | ☐ |

## What may be fixed after the pilot

Only things that cannot change what the system computes:

- typo correction
- layout improvement
- instruction clarification
- non-model logging bug
- file naming bug
- rater UI usability fix

## What may not be fixed after the pilot

- threshold change
- feature change
- model change
- tone gate change
- F0-processing change
- item replacement without teacher sign-off
- automatic decision-rule change

**The pilot must not be used to change the frozen model.** If the pilot shows
poor PASS rates, that is an observation to record, not a reason to adjust
anything — it is precisely the finding the study exists to measure.

## The stop rule

**If a UI or logging change would alter acoustic processing or model input —
STOP.** That includes sample rate, channel count, codec, gain or normalisation,
trimming, buffering that changes what audio reaches the analyser, and any change
to how the segment boundaries are chosen.

Such a change is a **system-version change**. It requires:

1. halting pilot and recruitment,
2. a new frozen system artefact with a new version string and hash,
3. re-running the D0 preflight against the new artefact,
4. re-running the pilot.

The frozen evidence does not transfer to a system that hears different audio.

## Sign-off

Pilot complete when items 1–11 are ticked and any fixes made fall entirely
within the permissible list.

**Pilot lead:** ____________  **Date:** ____________
