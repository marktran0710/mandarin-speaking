# Fresh validation — data dictionary

Three files. `*_TEMPLATE.csv` carry headers only; the study fills them.

## fresh_validation_items.csv (complete, 16 rows)

| field | meaning |
|---|---|
| item_id | I01–I16 |
| traditional_character | target, Traditional Chinese |
| expected_pinyin | Taiwan MoE reading, with tone diacritic |
| expected_tone | 1–4 |
| english_gloss / vietnamese_gloss | for participant instructions |
| prompt_type | single_syllable_read_aloud |
| list_block | presentation block |
| pronunciation_source | moe_dict (moedict.tw) |
| pronunciation_status | verified_single_reading — no polyphone, no neutral tone |

## fresh_validation_participants_TEMPLATE.csv

`participant_id`, `age_range`, `gender`, `L1`, `other_languages`,
`mandarin_proficiency_self`, `mandarin_proficiency_placement`,
`mandarin_learning_duration_months`, `taiwan_experience`,
`hearing_speech_issue_reported`, `consent_audio`, `consent_research_use`,
`session_date`, `device_used`, `environment_note`, `withdrew`,
`withdrawal_reason`, `notes`.

Descriptive only. **None of these may be used to modify the frozen system.**
Do not store directly identifying information in the analysis dataset.

## fresh_validation_trials_TEMPLATE.csv

**Identity** — `participant_id`, `item_id`, `attempt_number`, `first_attempt`
(YES/NO; only YES enters primary analysis), `expected_tone`, `expected_pinyin`,
`audio_path`, `recorded_at`.

**Technical** — `audio_captured`, `trajectory_available`,
`technical_failure_reason`, `processing_latency_ms`.

**System (blinded from raters)** — `r2_raw_score` (internal ranking value; never
shown to learner or rater), `system_decision` (PASS / RETRY).

**Human** — `rater1_id`, `rater1_accept` (YES/NO), `rater1_confidence` (1–5),
`rater1_perceived_tone`; same for rater 2. `human_consensus` is derived
(HUMAN_ACCEPT / HUMAN_REJECT / DISAGREEMENT / INCOMPLETE) — do not hand-fill it.
`adjudicator_id`, `adjudicated_accept` only if a documented third rater resolved
a disagreement.

**Study control** — `rater_order_id` (seeded presentation order),
`is_duplicate_qc_trial`, `duplicate_of_trial_id`, `notes`.

## Conventions

- Booleans: `YES` / `NO`. Blank means missing, and is handled by the
  pre-registered missing-data rules — never imputed.
- A system technical failure must have `system_decision = RETRY`.
- `first_attempt = NO` rows are retained for usability and technical analysis
  and excluded from the primary comparison.
