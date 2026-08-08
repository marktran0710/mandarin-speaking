# Recruitment readiness checklist (Phase D0)

Recruitment may not begin until every gate is ticked. Gates marked **EXTERNAL**
cannot be satisfied by this repository and require a person.

## Technical / methodological — verified by preflight

- [x] frozen system hash verified (`OMPAL_R2_PASS_v1`, sha256 `8101bcaf8c92e1e3…`)
- [x] recording → trajectory → model → decision chain dry-run passes for all four tones
- [x] PASS/RETRY wording verified: no forbidden term, no raw score, no digits
- [x] trajectory-failure behaviour verified → RETRY, never PASS
- [x] T1 gate verified: RETRY even when the score alone would have PASSed (PF01, 0.4185 < 0.4227)
- [x] only PASS / RETRY ever emitted; no produced-tone claim possible
- [x] rater blinding verified (no system decision, score, participant id, other rater, OMPAL result)
- [x] rater randomisation verified (0/399 adjacent same-learner, 0/399 adjacent same-tone, seed recorded)
- [x] duplicate-QC logic verified (7.5%, invisible to raters, excluded from the primary denominator)
- [x] analysis script frozen; verified to contain no model import and no fit call
- [x] analysis script fails cleanly on absent data — no placeholder results possible
- [x] preflight artefacts isolated under `data/preflight/`, every row marked `IS_PREFLIGHT=YES`
- [x] data storage paths and file schemas defined; participant IDs anonymised by schema
- [x] session metadata fields defined (system version, hash, timestamp, device, app version, environment)
- [x] sample-size / precision plan complete, with its limits stated explicitly
- [x] OMPAL Test still sealed (no predictions, scores or metrics on disk)

## External gates — NOT satisfied

- [ ] **EXTERNAL — all 16 items teacher-approved.** Every row of
      `data/fresh_validation_item_teacher_review_TEMPLATE.csv` must carry
      `teacher_decision = APPROVE`. No item is approved on automated grounds.
- [ ] **EXTERNAL — ruling on 話 and 電**: keep as isolated characters, or move
      to a fixed disyllabic prompt (e.g. 電話) with the target syllable
      preserved and the analysis window on it. Any substitution requires a new
      MoE verification and a reissued item manifest.
- [ ] **EXTERNAL — T3 half-third ruling** written into the rater instructions
      before rating begins, so raters do not each decide it privately.
- [ ] **EXTERNAL — ethics / IRB approval documented.** No approval is claimed
      and no documentation exists in this repository.
- [ ] **EXTERNAL — consent forms finalised** (audio retention, research use,
      right to withdraw).
- [ ] **EXTERNAL — participant instructions finalised** in the participants'
      working language.
- [ ] **EXTERNAL — raters recruited and briefed** (≥2, native or near-native
      Taiwan Mandarin, CFL pronunciation-teaching experience preferred; rater
      background recorded).
- [ ] **EXTERNAL — recruitment target confirmed** at 25, or raised to 30–40 if
      the wider interval (0.141 at N=25) is unacceptable to the stakeholder.

## Standing rules during the study

1. If the frozen system hash changes at any point, **stop the session**. A
   changed artefact is a new system version; it needs its own validation set
   and does not inherit this one.
2. Fresh validation labels may not be used to refit the model, move `t_pass`,
   or re-enable T1. A shortfall is the finding, not a tuning signal.
3. Preflight rows never enter the study dataset.
4. OMPAL Test stays sealed.
