# Fresh human validation study — executable protocol (Phase D)

**No data has been collected.** This document is complete enough for another
researcher to run the study without inventing methodological decisions.

## 1. System under validation

`OMPAL_R2_PASS_v1` — sha256 `8101bcaf8c92e1e3…`, recorded in
`data/fresh_validation_system_FROZEN.json`.

| | |
|---|---|
| representation | 20-point median-centred semitone F0 trajectory, time-normalised across the voiced span |
| classifier | tone-conditioned L2 logistic regression, C=0.1, class_weight=balanced |
| threshold | **t_pass = 0.4227** |
| PASS-enabled tones | **T2, T3, T4** |
| T1 | always RETRY |
| trajectory unavailable | always RETRY |
| outputs | **PASS** / **RETRY** only |

Never output: INCORRECT, WRONG, WRONG TONE, or any produced-tone claim such as
"T2 instead of T3". RETRY means *insufficient evidence to confirm*, never *the
production was wrong*. The raw score is internal and is never shown.

Development evidence being tested: Train PASS precision 0.919, 95% cluster CI
[0.861, 0.966], coverage 18.3%. Dev is **not** independent (the representation
was inspected on Dev in C6) and is therefore not the basis of any claim.

## 2. Research question

> When the frozen system outputs PASS for a fresh CFL learner production, do
> independent Mandarin raters agree the target tone is acceptable enough for
> the learner to continue?

## 3. Participants

**Target 25 learners** (acceptable range 20–30).

Inclusion: non-native Mandarin speaker; able to read/produce the target
material; provides audio and research-use consent; **not part of OMPAL
development**. L1 is deliberately not restricted — a narrow L1 group would
answer a narrower question than the product needs.

Recorded (descriptive only; never used to modify the system): `participant_id`,
age range, gender, L1, other languages, self-reported and placement proficiency,
learning duration in months, Taiwan experience, self-reported hearing/speech
issue where ethically appropriate, device, environment note.

## 4. Items and tone design

**16 scored items per learner**, 4 per tone → **≈400 first-attempt productions**
at 25 learners. This is a practical prospective validation sample, **not** a
formal power calculation.

Every target was verified single-reading in the Taiwan MoE dictionary: no
polyphone, no neutral tone, tone unambiguous. Full manifest in
`data/fresh_validation_items.csv`.

| tone | items |
|---|---|
| T1 | 貓 māo · 高 gāo · 天 tiān · 花 huā |
| T2 | 人 rén · 門 mén · 茶 chá · 魚 yú |
| T3 | 狗 gǒu · 水 shuǐ · 馬 mǎ · 筆 bǐ |
| T4 | 飯 fàn · 話 huà · 菜 cài · 電 diàn |

**T1 is included deliberately even though it can never PASS.** T1 is a known
limitation and must be documented prospectively rather than hidden, and the
human ratings of T1 items estimate how much useful coverage the gate is costing.
T1 PASS is **not** enabled during this study.

Items were chosen for CFL familiarity and lexical diversity. Outcome labels were
not used in selection.

## 5. Learner workflow

```
target shown (character + pinyin + gloss)
        ↓
learner records
        ↓
frozen system processes the recording
        ↓
PASS  →  "Your tone sounds acceptable. You can continue."
RETRY →  "I'm not confident enough to confirm this attempt. Please try once more."
```

System decisions are logged automatically and **blinded from raters**.

**First attempts only** feed the primary validation. Retries are influenced by
practice, effort and the feedback just received, so they are not equivalent to
independent first attempts. Retry recordings are retained for usability,
technical and exploratory analysis only.

## 6. Human raters

**At least two**, independent. Preferred: native or near-native Taiwan Mandarin,
with CFL pronunciation-teaching experience. Rater background is recorded.

Raters are blind to the system decision, to each other's ratings, and to all
OMPAL results.

### Primary question — matches PASS semantics exactly

> Is the target tone acceptable enough for the learner to continue without being
> asked to repeat it? **YES / NO**

Not "rate the pronunciation" — the system's claim is specifically about target-
tone acceptability, and asking a different question would make the comparison
uninterpretable.

### Secondary (optional)

Confidence 1–5; perceived produced tone (T1/T2/T3/T4/uncertain); severity
(minor / clear error). Produced-tone analysis proceeds **only** if rater
agreement on it is adequate — it has never been validated in this project
because OMPAL carries no produced-tone labels.

## 7. Presentation and QC

Deterministic seeded randomisation (`rater_order_id` stored) so the order is
reproducible. Avoid consecutive trials from the same learner or the same tone
where practical.

**5–10% hidden duplicate trials** estimate intra-rater consistency. Duplicates
do not alter the participant recording sample and are reported separately.

## 8. Human consensus rule (pre-registered)

| rater 1 | rater 2 | label |
|---|---|---|
| YES | YES | HUMAN_ACCEPT |
| NO | NO | HUMAN_REJECT |
| YES | NO | **DISAGREEMENT** |

Disagreements are **not** silently forced into a class. Two analyses are
reported:

- **Primary — strict consensus:** YES/YES and NO/NO only.
- **Sensitivity — full sample:** disagreements resolved by a documented third
  adjudicator, if one is available. Adjudicated labels are never created
  retrospectively without recording the procedure.

## 9. Human reliability is reported first

Before any system comparison: raw agreement, Cohen's κ (two raters) or an
appropriate multi-rater statistic, positive and negative agreement, and each
rater's YES rate.

κ is depressed at high YES prevalence, so it is interpreted **together with**
raw agreement and the marginals. A low κ does not by itself invalidate the human
criterion — but human–human agreement is the ceiling, and system–human agreement
cannot meaningfully exceed it.

## 10. Primary metric — PASS precision

```
PASS precision = human-acceptable system PASS / all system PASS
```

Because the system makes a one-sided positive claim, this is the safety number:
when it tells a learner to continue, how often do experts agree?

Also reported: PASS coverage, retry rate, false-PASS count and rate, speaker
coverage, per-tone PASS precision, sensitivity/specificity where meaningful, and
the PASS/RETRY × ACCEPT/REJECT confusion matrix. **Accuracy is not the
headline.**

## 11. Uncertainty — speaker-cluster bootstrap

All primary intervals resample **participants**, not tokens, 4000 times.
~400 productions from ~25 learners are not 400 independent observations; a token
bootstrap would give intervals several times too narrow. Every estimate reports
point value, 95% CI, number of learners, and number of productions.

## 12. Pre-specified success interpretation

**PASS precision ≥ 0.90**, with the lower bound of the cluster CI reported
prominently.

If the result is 0.87, the study found 0.87. **`t_pass` is not moved, tones are
not re-enabled, and the model is not refit.** Doing so would convert validation
data into development data and destroy the only independent evidence in the
project.

Coverage is a **separate** outcome. High precision with very low coverage is a
legitimate finding — "safe but rarely useful" — and must be reported as such
rather than repaired.

## 13. Technical robustness

Per first attempt: audio captured, trajectory extracted, processing completed,
latency in ms, failure reason. Reported: technical success rate, trajectory
failure rate, median and IQR latency, and 95th percentile.

## 14. Learner usability

Short questionnaire (5–8 items, 1–5 Likert) after the session: clarity of the
PASS message, clarity of the RETRY message, frustration from repeated RETRY,
perceived usefulness, ease of recording, willingness to use again, plus one
optional open comment. Not a psychometric study.

Retry behaviour reported descriptively: retries per item, % items retried, time
per item, non-completion.

**No learning-effectiveness claim.** Improvement across immediate retries may
reflect practice, repetition, increased attention, or feedback response, and
cannot establish learning. That requires a comparison condition and pre/post
with a delayed test — outside Phase D.

## 15. Missing-data rules (fixed before collection)

| situation | rule |
|---|---|
| one rater missing | excluded from strict consensus; appears in sensitivity analysis if adjudicated |
| both raters missing | excluded from human comparison; counted in trial flow |
| corrupt audio | excluded from human comparison; counted as technical failure |
| system technical failure | decision must be RETRY; kept in coverage denominators, excluded from PASS precision |
| participant withdrawal | all their trials excluded; participant counted in flow |

Technical RETRY (trajectory unavailable) is distinguished from model RETRY
(score above threshold) wherever the data permit.

## 16. Modification lock

Fresh validation labels may **not** be used to refit R2, change C, change
`t_pass`, change enabled tones, or change trajectory processing or feature
normalisation. Any such change creates a **new system version** requiring a new
independent validation set. The analysis script never loads the model.

## 17. Study checklist

**Before data collection**
1. Ethics/consent approval in place; consent text covers audio retention and research use.
2. `fresh_validation_system_FROZEN.json` hash verified unchanged.
3. Item manifest reviewed by a Mandarin teacher for CFL appropriateness.
4. Recording pipeline tested end-to-end; latency logging confirmed.
5. Randomisation seed fixed and recorded.
6. Analysis script runs and fails cleanly on absent data (verified).

**During recording**
7. One session per learner; 16 scored items in randomised block order.
8. Log every attempt with `attempt_number` and `first_attempt`.
9. Log audio capture, trajectory availability, latency, failure reason.
10. Do not reveal the system decision to anyone who will rate.

**Before human rating**
11. Build the blinded rater sheet; verify it contains no system decision, score, participant history or other rater's judgement.
12. Insert 5–10% hidden duplicates.
13. Apply the seeded presentation order; store `rater_order_id`.

**During human rating**
14. Raters work independently and do not confer.
15. Collect YES/NO first, then confidence, then optional perceived tone.

**Before analysis**
16. Merge rater sheets into the trials file; do not overwrite system fields.
17. Apply the pre-registered missing-data rules; do not invent new ones.
18. Confirm no model artefact was modified during the study.

**Final analysis**
19. Report human–human reliability **first**.
20. Report strict-consensus PASS precision with cluster CI, then coverage, tone and speaker breakdowns, technical and usability outcomes.
21. State the verdict against the 0.90 target without adjusting the threshold.
22. OMPAL Test remains sealed.
