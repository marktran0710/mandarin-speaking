# Rater recruitment, training and instructions

## Part 1 — Invitation

We are looking for **at least two** independent Mandarin raters.

**Preferred background:** native or near-native Taiwan Mandarin, with experience
teaching Mandarin pronunciation to non-native learners. Your background will be
recorded (language background, teaching experience, years) so it can be reported
alongside the results.

**What it involves:** listening to short recordings of learners saying single
Mandarin characters and answering one question about each. Roughly 430
recordings including hidden repeats, in as many sittings as you like.

**What we ask of you:**

- Work independently. Please do not discuss the recordings with the other rater
  until all rating is finished.
- Rate in reasonable sittings. If you are tired, stop and continue later —
  a break is better than pushing through.

**What you will not see:** what the app decided, any numerical score, the other
rater's answers, or which learner produced which recording. This is deliberate,
and it is the main reason your ratings are worth collecting.

## Part 2 — The rating question

For each recording you will see the **target character**, its **expected
pinyin**, and the **expected tone**, and hear one learner attempt.

> **Is the target tone acceptable enough for the learner to continue without
> being asked to repeat it?**
>
> **YES** — acceptable, the learner can move on
> **NO** — the learner should try again

Please judge the **tone** specifically. Consonant or vowel imperfections should
not by themselves make you answer NO, unless they make the tone impossible to
judge.

This is not "was it perfect". It is the everyday teaching question: would you
let this attempt go and move on, or ask for another try?

Then:

- **Confidence (1–5)** — 1 = very unsure, 5 = very sure.
- **Perceived tone (optional)** — T1 / T2 / T3 / T4 / uncertain. Please choose
  "uncertain" freely; an honest uncertainty is more useful than a guess.
- **Comment (optional)**.
- **Unusable audio** — if the recording is silent, clipped, cut off, or
  otherwise impossible to judge, mark it unusable rather than guessing.

### Tone 3 rule

> ⚠️ **PENDING TEACHER APPROVAL — the approved wording is pasted here before
> rating begins. Rating may not start while this placeholder is still in
> place.**
>
> Proposed for approval: *A naturally produced low / half-third realisation may
> be rated ACCEPTABLE when it is appropriate for the elicitation context and
> does not require a canonical full dipping contour.*

### Some recordings repeat

A small number of recordings appear more than once. This is an intentional
consistency check and applies to every rater. Judge each one as you hear it —
please do not try to remember what you said before.

## Part 3 — Training procedure

Training happens **before** formal rating and uses **only preflight / training
recordings**, all marked `PILOT_ONLY` or `IS_PREFLIGHT` and permanently excluded
from the validation analysis.

**Validation participants' trials are never used for training.** In particular,
training may not be extended or repeated after seeing disagreement on real
trials — that would tune the raters to the data they are meant to judge
independently.

**Training must not aim raters at the system's decisions.** The system output
stays hidden throughout training as well as formal rating. There is no "correct
answer key" derived from the app.

### Session outline (about 30 minutes)

1. Read Part 2 above together and check the question is understood the same way
   by both raters.
2. Listen to ~10 training recordings covering:
   - a clearly acceptable production
   - a production that clearly needs a retry
   - the **T3 rule** — at least two Tone-3 examples including a half-third
     realisation
   - minor voice-quality variation (breathy, creaky, quiet) that should *not*
     by itself force NO
   - a technical audio failure, to practise marking unusable rather than
     guessing
   - at least one genuinely uncertain case
3. Rate them independently, then compare and discuss.
4. Walk through the rating interface: playback, replay, YES/NO, confidence,
   perceived tone, unusable, save, resume.

### When training is complete

There is **no kappa threshold to clear**. Requiring one would push raters toward
each other before they have heard any real data, and agreement forced in
training is not evidence of a reliable criterion.

Training is complete when:

- [ ] both raters can state the primary question in their own words and mean the
      same thing by it
- [ ] the rating interface works end to end for each rater, including resuming
      an interrupted session
- [ ] the approved T3 rule has been read and its application to the training
      examples is agreed operationally
- [ ] the training trials have each been rated independently
- [ ] both raters understand that discussion happens **only** in training

Observed training agreement is recorded for the report, but it is **not** a gate.

## Part 4 — Once formal rating begins

**Raters work independently.** No discussion of specific recordings, no
comparing answers, no revisiting earlier ratings after conversation.

If something is unclear during formal rating — an interface fault, a corrupted
file, an ambiguity the training did not cover — raise it with the researcher
rather than with the other rater. Any clarification given is recorded and passed
to both raters identically.

Disagreement between raters is expected and is a result, not a problem to be
resolved by conferring. Disagreements are handled by the pre-registered
consensus rule.
