# Project instructions

## Git workflow: commit every completed task

- Work in the current repository checkout and branch. Do not create Git worktrees.
- Once each task is implemented, verified as appropriate, and its final diff reviewed, commit that task immediately before starting the next task or sending the final response. Do not wait for an additional commit request or combine unrelated completed tasks into one commit.
- Inspect the branch, HEAD, working tree, and staged changes before editing and again before committing so concurrent changes are noticed.
- Stage and commit only the files or hunks belonging to the current task. Preserve unrelated changes made by the user or other agents, including changes already staged.
- If a merge, rebase, cherry-pick, or concurrent commit/edit causes a conflict with the task, warn the user immediately. Identify the affected files, commits when known, and the operation involved; explain what blocks completion. Preserve both sides and do not commit unresolved conflicts or silently overwrite others' work.
- If the task cannot be committed, report the concrete reason and the remaining changes. Do not claim the task is fully complete.
- Include the commit hash and a short summary in the final response.

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
