# Project instructions

## AI voice feedback code: warn before editing

Before changing anything in the tone-scoring/verdict path —
`backend/domain/speech/tone_decision.py` (thresholds: `TONE_CONFIRM_THRESHOLD`,
`TONE_ERROR_THRESHOLD`, `SHAPE_STRONG`, `SHAPE_WEAK`, `DIRECTION_SUPPORT`,
`DIRECTION_BAD`, `PHRASE_RESCUE_SHAPE_STRONG`, `PHRASE_RESCUE_DIRECTION_SUPPORT`),
`backend/domain/speech/tones/` (shape/direction heuristics),
`backend/domain/speech/acoustics/` (`_combine_word_verdict`, `_apply_phrase_rescue`,
syllable/word promotion logic), or the sentence-level pass gate
(`SENTENCE_SYLLABLE_PASS_RATIO`, `build_pronunciation_mastery` in
`backend/services/pronunciation_scoring.py`) — explain the concrete
before/after impact to the user (real numbers, ideally a real sentence) and
get explicit confirmation before implementing. Do not ship a threshold or
verdict-logic change silently, even a "small" one.

These thresholds directly decide whether a real student's recording is
graded ✓/△/✗ and are explicitly unvalidated against human raters (the
code's own comments call them "ENGINEERING DEFAULTS, not calibrated
cutoffs"). A change here shifts grading leniency/strictness across every
student in both directions, and the test suite cannot catch "this is now
too lenient/strict" on its own since tests just encode whatever the new
thresholds produce.
