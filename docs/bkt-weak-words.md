# BKT Weak Words / Priority Review

The learner-facing personalized review flow uses one pooled standard Bayesian
Knowledge Tracing model. The knowledge component is a vocabulary word, so the
state is maintained independently for each `student_id × word_id` pair.

## Runtime flow

1. A new word is `UNASSESSED` until it has three eligible observations.
2. Three distinct Easy tier slots (`tier1`, `tier2`, and `tier3`) unlock the
   personalized review gate. The server also reports per-word evidence
   coverage; a word with fewer than three observations stays `UNASSESSED` and
   is not recommended.
3. Each validated binary answer is appended to `vocab_quiz_responses` and the
   learner's `student_vocab_mastery` cache is rebuilt from ordered history.
4. Assessed non-mastered words are sorted by `p_learned`; the first five are
   returned as the learner's priority review words.
5. Review answers use the same BKT update and are then included in the next
   ranking. Review questions prefer a question kind not previously seen for
   that word when one is available.

The new endpoints are:

- `GET /api/students/{student_id}/weak-words`
- `GET /api/students/{student_id}/vocabulary-mastery`
- `GET /api/students/{student_id}/vocabulary-mastery/{word_id}/seen-items`

The existing vocabulary-attempt endpoint remains the write boundary. It
stores the original JSONB attempt and also writes the normalized response
ledger. Attempts are immutable by id: resubmitting an identical attempt is
idempotent, while changed response data returns a conflict.

## Model parameters

`backend/analytics/bkt.py` is the single runtime configuration for `L0`, `T`,
`G`, `S`, the `.95` mastery criterion, minimum evidence, diagnostic count, and
Bottom-K size. The current values are transparent engineering defaults, not
research-validated cutoffs. They must be frozen or replaced with
pilot-calibrated parameters before the main experiment.

Response time is collected in the ledger for audit and later analysis. It is
not an input to BKT, mastery, eligibility, or ranking.

## Historical data

Migration `0026` copies safely mappable legacy JSONB responses into the
normalized ledger as `bkt_eligible = false` with an explicit audit reason.
Rows with no student, word, or binary outcome are skipped and reported by the
migration. They are never silently treated as evidence. The rebuild command
can replay the normalized ledger after a parameter change:

```text
python scripts/rebuild_bkt_mastery.py [student_id]
```

## Experiment condition boundary

The current authentication and vocabulary-attempt models do not carry a
control/experimental assignment. Therefore this implementation does not infer
one from role, URL, or student id. The existing general review remains
available as the non-personalized path; the BKT Bottom-K behavior is exposed
only through the personalized review endpoint and card. A future assignment
field can select between these paths without changing response count,
question count, duration, feedback, or question-pool rules.
