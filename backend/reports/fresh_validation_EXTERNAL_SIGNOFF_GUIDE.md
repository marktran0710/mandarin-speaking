# External sign-off guide (Phase D2)

Technical preparation is finished. Everything that remains is a human decision.
This page says who decides what, where the answer is recorded, and what happens
next.

**Nothing here approves anything.** The status record
`data/fresh_validation_external_signoff.json` starts with every value `PENDING`,
and a value changes only when a named person supplies a decision. The gate
checker reads that file and never writes it.

## The one command

```
python -m pronunciation.wav2vec_tone.check_fresh_validation_study_gate
python -m pronunciation.wav2vec_tone.check_fresh_validation_study_gate --teacher-review
```

It prints one line per gate and a single `STUDY_START_READY = YES / NO`. It
modifies no file and resolves no gate. **A failed requirement is never waived.**

Current output:

```
  SYSTEM HASH          PASS     8101bcaf8c92e1e3 OMPAL_R2_PASS_v1
  ITEM APPROVAL        PENDING  0/16 approved
  話 / 電 CONTEXT       PENDING  話 PENDING / 電 PENDING
  T3 RULE              PENDING  rating cannot begin while PENDING
  ETHICS / CONSENT     PENDING  9 external items; no approval is claimed
  RATERS               PENDING  >= 2 independent raters
  PILOT                PENDING  PILOT_ONLY, never in the analysis
  PARTICIPANT INSTR.   PASS     drafted; final wording follows the ethics text
  ITEM MANIFEST HASH   PENDING  not created — correct while teacher review is pending
  ITEM ORDER FILE      PASS     12 orders, 0 adjacent same-tone
  COLLECTION TRACKER   PASS     template ready, no participant names
  DATA PATHS           PENDING  files present; end-to-end write confirmed by the pilot
  ANALYSIS SCRIPT      PASS     no model fit; 0.90 target hard-coded
  OMPAL TEST SEAL      PASS     5/5 seal checks

STUDY_START_READY = NO
```

---

## Gate 1 — Teacher item review

**Who:** a Mandarin teacher. **Materials:**
`reports/fresh_validation_teacher_packet.md`. **Return:**
`data/fresh_validation_item_teacher_review_TEMPLATE.csv`, one row per item, with
the four tick fields, `teacher_decision`, initials and date.

Then run the gate checker with `--teacher-review`. It validates that all 16 item
IDs are present, no item is duplicated, every field is filled, every
`teacher_decision` is `APPROVE` or `REPLACE`, and that no expected tone changed
without a written reason.

**If any item is marked REPLACE, the checker STOPS and names it.** It does not
choose a substitute — that is a teaching judgement. A replacement needs a new MoE
single-reading verification and another round of teacher review before it can be
used.

Record in the status file: `teacher_item_review_status`, reviewer id, date, and
any items marked REPLACE.

## Gate 2 — 話 and 電 context decisions

**Who:** the same teacher. Two independent decisions, recorded separately:

```
ISOLATED_CHARACTER   keep the single character as the prompt
CONTEXT_APPROVED     use a controlled word, target syllable identified
```

If context is approved, record all five fields for that item:

| field | meaning |
|---|---|
| `display_prompt` | what the learner sees, e.g. 電話 |
| `target_character` | the character being validated, e.g. 電 |
| `target_syllable` | the syllable analysed |
| `target_syllable_position` | 1-indexed position in the prompt |
| `expected_pinyin` | reading of the target syllable |
| `expected_tone` | tone of the target syllable |

Two hard rules:

1. **The acoustic target tone may not change.** 話 and 電 are both T4 items. A
   context word must preserve the target syllable's tone, or it is a different
   item and the frozen evidence does not describe it.
2. **The change must be versioned into the item manifest before recruitment.**
   Never edit the target silently, and never mid-study.

## Gate 3 — T3 acceptability rule

**Who:** the teacher, or a designated rating expert. Candidate wording, offered
for a decision and not adopted by default:

> A naturally produced low/half-third realization may be considered acceptable
> when appropriate to the elicitation context and need not exhibit a canonical
> full dipping contour.

Record `t3_rule_status` as `APPROVED`, `AMENDED`, `REJECTED` or `PENDING`. **If
amended or rejected, store the approved wording verbatim** in
`approved_wording_verbatim` — a paraphrase is not the rule.

**Formal rating cannot begin while `t3_rule_status = PENDING`.** The rater
instructions carry a blocking placeholder until the approved text replaces it.

## Gate 4 — Ethics and consent

**Who:** the institution and the responsible researcher. Ten fields, each
`CONFIRMED`, `NOT_REQUIRED`, or `PENDING`:

`ethics_determination`, `ethics_reference_number`, `consent_form_approved`,
`audio_recording_consent_confirmed`, `data_storage_confirmed`,
`retention_policy_confirmed`, `withdrawal_policy_confirmed`,
`recruitment_wording_confirmed`, `participant_compensation_confirmed`,
`researcher_contact_confirmed`.

**No ethics approval is claimed anywhere in this repository, and none can be
inferred from these files.** `NOT_REQUIRED` is a legitimate answer for some
items in some jurisdictions, but only the institution may give it. Detail and
the points an approving body will likely raise are in
`fresh_validation_ethics_consent_CHECKLIST.md`.

## Gate 5 — Raters

At least two independent Mandarin raters. Six sub-fields must be `CONFIRMED`:
`rater_1_confirmed`, `rater_2_confirmed`, `rater_training_complete`,
`rater_blinding_verified`, `t3_rule_acknowledged`, `rating_interface_tested`.

**Do not compute inter-rater reliability during training.** Formal reliability
is a property of the completed validation dataset and is reported first in the
final analysis. A kappa measured on training material would be a different
number about different audio, and treating it as a threshold would push raters
toward each other before they hear real data.

## Gate 6 — Pilot

2–3 `PILOT_ONLY` participants, recorded in the tracker with `pilot_only = YES`.
**Pilot data never enters the validation analysis.** Twelve checks are listed in
`fresh_validation_PILOT_CHECKLIST.md` and mirrored in the status file.

Pilot findings may fix logistics and interface only.

### The hard system-version rule

If a pilot correction changes any of:

```
sample rate · audio codec · channels · gain · normalization
F0 extraction · token boundaries · trajectory calculation
model features · classifier · threshold · tone gate · decision logic
```

then **STOP**. The system is no longer `OMPAL_R2_PASS_v1`. A new frozen version
must be issued and the D0 technical preflight re-run against it.

**Validation status does not transfer.** Evidence gathered on a system that
heard one kind of audio says nothing about a system that hears another.

## Gate 7 — Frozen item manifest

**Only after teacher sign-off exists**, create
`data/fresh_validation_items_FROZEN.csv` with columns:

```
item_id · display_prompt · target_character · target_syllable
target_syllable_position · expected_pinyin · expected_tone
teacher_approved · teacher_reviewer_id · review_date · context_decision
```

Compute its SHA-256 and record it in the status file. The gate checker then
verifies the file against the recorded hash on every run.

**This file does not exist yet, and creating it now would be fabricating an
approval.** `ITEM MANIFEST HASH` reading PENDING is the correct state.

---

## Documentation freeze

When an external decision arrives, update **only the affected placeholder** in:

```
reports/fresh_validation_teacher_packet.md
reports/fresh_validation_participant_instructions.md
reports/fresh_validation_rater_recruitment_and_training.md
reports/fresh_validation_ethics_consent_CHECKLIST.md
reports/fresh_validation_session_RUNBOOK.md
reports/fresh_validation_STUDY_START_GATE.md
```

**Do not rewrite the scientific protocol.** The analysis plan, the primary
metric, the 0.90 criterion, the consensus rule and the reporting order are
fixed.

Log every placeholder edit here:

| date | external decision | file | placeholder replaced |
|---|---|---|---|
| — | *(none yet)* | — | — |

## Recruitment

Target **30 completed eligible CFL learners**, acceptable range **25–40**.
Not formally powered — see `fresh_validation_sample_size_precision_plan.md`.

Recruit until 30 completed eligible participants, unless an external logistical
or ethical decision changes the target **before collection begins**. Interim
validation outcomes may never influence where recruitment stops.

## No interim outcome peeking

Once recruitment begins, do not compute PASS precision, false PASS counts,
system–human agreement, tone-specific precision, or confidence intervals.

Permitted monitoring — about whether collection is working, not whether the
model is doing well: missing recordings, trajectory failures, app crashes,
latency, file integrity.

`analyze_fresh_human_validation.py` runs **once**, after recruitment and rating
are complete, exactly as frozen, in its fixed order: human–human reliability →
consensus → PASS precision → speaker-cluster CI → coverage → tone-specific →
technical robustness → usability.

## After sign-off

When the teacher review, ethics/consent confirmation, rater confirmation and
pilot completion are all supplied and recorded, run the gate checker. If it
prints

```
STUDY_START_READY = YES
```

technical work ends and the next action is **collect real participant data**.

There is no model-tuning step before collection. The validation phase is
complete once recruitment, two-rater ratings and the pre-registered analysis are
done — **whatever the result**. A negative result is a valid endpoint and does
not start a new tuning cycle.
