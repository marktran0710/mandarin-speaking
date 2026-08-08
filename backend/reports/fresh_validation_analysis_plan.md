# Fresh validation — analysis plan (pre-registered)

Fixed before any data exists. Implemented in
`pronunciation/wav2vec_tone/analyze_fresh_human_validation.py`, which exits with
a clear message when data are absent rather than producing placeholder output.

## Order of reporting

The order is part of the plan, not presentation preference.

1. **Participant and trial flow** — enrolled, withdrawn, analysed; trials total,
   first attempts, exclusions by pre-registered rule.
2. **Human–human reliability** — raw agreement, Cohen's κ, positive and negative
   agreement, each rater's YES rate. This is the ceiling and is reported before
   any system number, so the system is never compared against a criterion whose
   own reliability is unknown.
3. **Consensus distribution** — HUMAN_ACCEPT / HUMAN_REJECT / DISAGREEMENT.
4. **Primary: PASS precision** on strict consensus, with 95% speaker-cluster
   bootstrap CI.
5. **Sensitivity:** full sample with documented adjudication, if available.
6. **Coverage** — PASS coverage and retry rate, reported as a separate outcome.
7. **Per tone** — T1–T4 with denominators; T1 coverage is 0 by design.
8. **Per participant** — coverage and precision, to detect confirmation
   concentrated in a few learners.
9. **Technical** — capture rate, trajectory failure rate, latency median/IQR/p95.
10. **Retry and usability** — descriptive only.
11. **QC duplicates** — intra-rater agreement, reported separately.

## Primary estimand

```
PASS precision = human-acceptable system PASS / all system PASS
```

One-sided by design: the system only makes positive claims, so the question is
how often a confirmation is justified.

## Uncertainty

Speaker-cluster bootstrap, 4000 resamples of **participants**. Tokens within a
learner are correlated; a token bootstrap would understate every interval.
Report point estimate, 95% CI, n learners, n productions.

## Pre-specified criterion

PASS precision **≥ 0.90**, CI lower bound reported prominently.

A shortfall is the finding. `t_pass`, enabled tones, and the model are frozen —
the script does not load the model and cannot modify it.

## Interpretation guards

- Accuracy is not the headline; prevalence of acceptable productions will be
  high and accuracy would mostly restate it.
- High precision with very low coverage is a legitimate result: safe but rarely
  useful.
- No learning-effectiveness claim from first→retry change; that is confounded
  with practice and attention.
- Produced-tone analysis only if rater agreement on perceived tone is adequate.
- Any post-hoc change to the system creates a new version needing new
  validation data.
