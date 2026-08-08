# Session runbook — one participant

One session per participant, about 15–20 minutes. Follow this in order.

## Before the participant arrives

1. Run `python -m pronunciation.wav2vec_tone.preflight_fresh_validation`.
   Confirm **19/19** checks pass and the frozen hash verifies. If the hash check
   fails, the script exits with `STOP VALIDATION SESSION` — do not record.
2. Confirm free disk space and that the recording directory is writable.
3. Open the collection tracker and note the next `participant_id` and its
   `order_id` (see step 5).

## During the session

**1. Verify participant ID.** Assign the next `participant_id` from the tracker
(`P001`, `P002`, …). Never write the participant's name into the tracker or any
analysis file. If a name-to-ID link is kept at all, it lives in the separate
document named in the ethics checklist.

**2. Verify consent.** Confirm the signed consent form exists, including audio
consent, before anything is recorded. Record `consent_complete = YES`. Without
consent, the session does not happen.

**3. Confirm microphone.** Same microphone and room for every participant if
possible. Note the device and environment in the tracker.

**4. Run a short non-study microphone test.** One or two throwaway phrases, to
check levels and that the participant is audible. **This is not a study trial:**
it is not saved into the trials file, not scored, and not rated. Its only
purpose is to catch a dead microphone before 16 trials are wasted.

**5. Assign the item order.** `order_id = O{(participant_number − 1) mod 12 + 1}`
— P001→O01, P013→O01, and so on. Take the sequence from
`data/fresh_validation_item_orders.csv` and record `order_id` in the tracker.
The order is assigned before the session and never chosen after seeing anything.

**6. Read the participant instructions** (`fresh_validation_participant_instructions.md`).
Make sure the participant has understood that RETRY does not mean they were
wrong. Answer questions before starting.

**7. Run the 16 target trials** in the assigned order.

For each item:

  a. Show character + pinyin + meaning.
  b. Participant records.
  c. **Save the first attempt** with `attempt_number = 1`, `first_attempt = YES`.
     This is the only recording that enters the primary analysis, so it is saved
     before anything else happens.
  d. The system produces PASS or RETRY and shows the corresponding message.
  e. On RETRY, offer one retry. Retries are saved with `first_attempt = NO` and
     an incremented `attempt_number`.
  f. Move on regardless of the outcome. **Never coach the participant toward a
     PASS**, and never repeat an item because you did not like the result.

**8. Log every technical event** per attempt: `audio_captured`,
`trajectory_available`, `technical_failure_reason`, `processing_latency_ms`,
`recorded_at`. A technical failure must be recorded as `system_decision = RETRY`.

**9. Usability questionnaire.** 5–8 Likert items plus one open comment, after
all 16 trials. Record `usability_complete`.

**10. Verify files saved.** Before the participant leaves: 16 first-attempt
audio files exist and are non-empty, the trials rows are written, and the audio
plays back. If a first attempt is missing, note it — **do not re-record it after
the fact**, since a repeat attempt is not a first attempt.

**11. Close the session.** Update the tracker:
`session_complete`, `first_attempts_complete_16`, `technical_failures`,
`usability_complete`, `notes`. Thank the participant.

## After the session

- Back up the recordings according to the approved storage plan.
- Record `system_version`, `system_hash`, session date/time, device, app
  version and processing environment in the session log.
- Do **not** compute any validation result. See the interim-peeking safeguard in
  `fresh_validation_STUDY_START_GATE.md`.

## What counts as the primary data

**First attempts only** — 16 per participant. Retries are secondary and
descriptive: they measure usability and retry behaviour, and they are reported
separately. They never enter PASS precision.

## If something goes wrong

| situation | action |
|---|---|
| microphone fails mid-session | fix it, continue from the next item, log the affected trials as technical failures |
| participant wants to stop | stop immediately; record `withdrew = YES` and the reason if freely given; apply the approved withdrawal procedure |
| an item is accidentally skipped | log it as missing; do not append it at the end out of order — note the deviation |
| the app crashes | record the trial as a technical failure; restart; do not re-run completed items |
| the participant asks "was that right?" | explain that the app only says whether it can confirm, and that you cannot judge it either |
| frozen hash fails preflight | **stop the session**; a changed artefact is a new system version |
