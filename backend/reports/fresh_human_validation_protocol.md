# Fresh human validation protocol — PASS / RETRY confirmation system

To be executed after Phase C8. **No data has been collected.** This document
specifies the study so that the design is fixed before any recording exists.

## What is being validated

The frozen one-sided system, not a Correct/Incorrect classifier:

```
POLICY_B_tone_gated · t_pass = 0.4227 · enabled tones T2, T3, T4
trajectory unavailable -> RETRY · outputs PASS | RETRY only
```

The human question must match the system decision exactly:

> **Is the target tone acceptable enough for this learner to continue?
> YES / NO**

Not "was it perfect", not "which tone did you hear". Asking a different
question than the system answers is the commonest way this kind of study
produces an uninterpretable number.

## Why OMPAL cannot answer this

OMPAL is French-L1 read speech, rated by three of four experts, with no
produced-tone record. This project has measured its limits precisely: 81/100
segment usability, no automatic QC rule, and Dev exceeding the Train estimate in
four consecutive phases. It was adequate to develop a formulation; it cannot
establish that the formulation works on our learners, on spontaneous speech,
through our microphone path, or against our teachers' standards.

The fresh set must be **independent of all OMPAL development data**.

## Participants and material

- **20–30 CFL learners**, recruited to span proficiency rather than convenience
- **15–20 target items each** → roughly 300–600 tokens
- Recorded **through the actual app workflow**, not in a studio: the same
  microphone path, prompts and retry affordance the product would use
- Items must cover T2, T3, T4 (the enabled tones) **and T1**, so the gate
  decision can itself be checked against fresh evidence

## Raters

- **At least two independent Mandarin raters**, preferably Taiwan-based CFL
  teachers, since the target variety is Taiwan Mandarin
- Blind to the system output and to each other
- Same binary question as the system, plus a free-text note

Optional and explicitly not required: perceived produced tone, and severity.
Collect them **if raters can supply them reliably** — that would be the first
data in this project capable of validating tone-confusion diagnosis, which
OMPAL never could. Do not make the study contingent on it.

## Analysis order — this matters

**Report human–human agreement first.** It is the ceiling: if two teachers
agree only moderately on whether an attempt is acceptable, no system can be
asked to do better, and the target moves. Report Cohen's κ with a
speaker-cluster bootstrap interval, and the raw agreement rate alongside it,
since κ is unstable at high prevalence.

Only then report system–human agreement.

## Pre-specified metrics

| metric | why |
|---|---|
| human–human agreement (κ, CI) | the ceiling; report before anything else |
| **PASS precision against human YES** | the primary safety number |
| **false-PASS rate** | the harmful error: confirmed but not acceptable |
| automatic coverage | what fraction of attempts get confirmed |
| retry rate | what a learner actually experiences |
| speaker coverage | is confirmation concentrated in easy learners |
| per-tone PASS precision | T2/T3/T4 separately, with denominators |
| T1 check | does fresh evidence support keeping T1 gated |

Intervals must use a **speaker-cluster bootstrap** throughout. Tokens within a
learner are not independent, and treating 500 tokens from 25 learners as 500
observations would produce intervals several times too narrow.

## Pre-specified success criteria

Fixed now, before data exists:

- PASS precision against human judgement **≥ 0.90**, with the lower bound of the
  speaker-cluster CI reported and not hidden
- Coverage high enough to be useful in a lesson — to be judged against observed
  retry tolerance, not a number invented here
- No single tone below 0.85 PASS precision among enabled tones
- Confirmation reaching a large majority of learners, not a subset

If PASS precision holds around 0.90 but coverage collapses on real speech, the
finding is that the system is safe and not yet useful — which is a legitimate
outcome and must be reported as such rather than repaired by moving the
threshold.

## Explicitly out of scope

- No threshold retuning on this set. It is validation, not development. If the
  policy fails, that is the result.
- No learning-effectiveness claim. Improvement from first attempt to retry is
  confounded with practice and with trying harder; a learning claim needs a
  control condition and a delayed post-test, which this design does not have.
- No produced-tone diagnosis claim unless rater-perceived tone was collected
  *and* the raters agreed on it well enough to serve as a criterion.

## Relationship to the sealed OMPAL Test

The OMPAL Test split (7 speakers, 322 tokens, 55 Incorrect) remains sealed and
untouched. It is a one-shot benchmark confirmation, and it is now the *lesser*
evidence: it would tell us how the formulation scores on more OMPAL read
speech, not whether it works for learners. Spend it, if at all, after the
practical formulation has survived this study.
