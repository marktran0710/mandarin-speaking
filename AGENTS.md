# Project instructions

## Task Orchestration

For each coding request, first classify it internally as EASY, NORMAL, or HARD without spending excessive reasoning on classification or providing lengthy classification commentary.

### EASY

Use EASY when requirements are explicit, the solution is obvious and localized, usually involves one or a few files, has low regression risk, and requires no architectural decision, authentication or security work, database migration, or destructive data operation. Examples include renaming a variable, fixing a typo, a minor CSS/UI adjustment, changing a label, updating simple configuration, adding straightforward validation, adding a simple test, or a mechanical transformation.

Delegate EASY work to `fast_worker`. Do not invoke `planner` or `reviewer` unless something unexpected occurs.

### NORMAL

Use NORMAL for normal feature implementation, moderate business logic, ordinary bug fixing, standard API/component/service changes, or a moderate refactor with a reasonably clear path. Delegate to `standard_worker`, requiring only its short execution plan and appropriate targeted tests. Do not use Sol by default.

### HARD

Classify a task as HARD when it materially involves architecture changes, ambiguous root cause, difficult debugging, cross-module or cross-service refactoring, authentication or authorization, security-sensitive functionality, database/schema migration, destructive data operations, concurrency or race conditions, public API compatibility, major performance issues, complex algorithms, many interacting components, substantial backward-compatibility risk, or unclear requirements with important consequences.

For HARD work:

1. Spawn `planner` and wait for its read-only analysis.
2. Convert the analysis into bounded implementation tasks.
3. Delegate EASY subtasks to `fast_worker` and NORMAL subtasks to `standard_worker`.
4. Run independent tasks concurrently only when safe.
5. Integrate results and run relevant checks.
6. Spawn `reviewer` for a read-only final review.
7. If the reviewer returns FAIL, fix important findings, rerun relevant tests, and review again when warranted.

The planner should reduce a HARD task into the lowest-cost reliable bounded tasks; do not keep using Sol for implementation after planning when Luna or Terra can safely perform the work.

## Escalation and de-escalation

Escalate EASY to NORMAL when more files than expected, nontrivial logic, unclear assumptions, or unexpected test behavior appears. Escalate NORMAL to HARD when architecture decisions, unclear root cause, repeated failed fixes, security/authentication, possible data loss or corruption, concurrency, schema migration, or major hidden coupling appears. Never force a cheaper worker to continue after discovering higher complexity.

If a worker attempts materially the same fix twice and the problem remains unresolved, stop repeating it and escalate one level with the attempts, evidence, test output, current hypothesis, and unresolved uncertainty.

## Parallel execution

Parallelize only independent exploration, modules, or test suites. Avoid parallel modifications to the same file, tightly coupled code paths, the same schema/migration, or shared mutable configuration. Execute sequentially when conflicts are likely.

## Cost and model policy

Optimize for correctness first, then cost. Use the lowest-capability model that can reliably complete each bounded task:

- Luna / low: fast, localized, mechanical work.
- Terra / medium: ordinary implementation and moderate changes.
- Sol / high: deep planning, difficult diagnosis, architecture, high-risk decisions, and important final review.

Do not use Sol for search/replace, simple file creation, formatting, boilerplate, obvious tests, or straightforward isolated implementation.

## Planning and testing

- EASY: no detailed plan; run a targeted check or test where applicable.
- NORMAL: a short plan of at most approximately 2-4 steps; run targeted unit/integration tests and useful lint or type checks.
- HARD: detailed planner decomposition, targeted and regression tests, integration tests where applicable, and review against the original requirements.

Do not run huge unrelated test suites unless warranted by the change.

## User communication

Keep orchestration details brief. Communicate what is being done, important findings, what changed, validation performed, and remaining risks. Do not expose private chain-of-thought. For HARD work, it is acceptable to say briefly that the task is being decomposed into smaller implementation units.

## Tone-evaluation code: warn before editing

Before changing anything in the tone-scoring/verdict path — `backend/tone_decision.py` (thresholds: `TONE_CONFIRM_THRESHOLD`, `TONE_ERROR_THRESHOLD`, `SHAPE_STRONG`, `SHAPE_WEAK`, `DIRECTION_SUPPORT`, `DIRECTION_BAD`, `PHRASE_RESCUE_SHAPE_STRONG`, `PHRASE_RESCUE_DIRECTION_SUPPORT`), `backend/chinese_tones.py` (shape/direction heuristics), `backend/praat_analyzer.py` (`_combine_word_verdict`, `_apply_phrase_rescue`, syllable/word promotion logic), or the sentence-level pass gate (`SENTENCE_SYLLABLE_PASS_RATIO`, `build_pronunciation_mastery` in `main.py`) — explain the concrete before/after impact to the user (real numbers, ideally a real sentence) and get explicit confirmation before implementing. Do not ship a threshold or verdict-logic change silently, even a "small" one.

These thresholds directly decide whether a real student's recording is graded ✓/△/✗ and are explicitly unvalidated against human raters (the code's own comments call them "ENGINEERING DEFAULTS, not calibrated cutoffs"). A change here shifts grading leniency/strictness across every student in both directions, and the test suite cannot catch "this is now too lenient/strict" on its own since tests just encode whatever the new thresholds produce.

## Commit before context runs low

Any coding agent working in this repo — Claude Code, Codex, or another
tool — should commit meaningful, verified, working progress to git before
its own context/token budget gets close to running out (roughly the last
5% of budget), rather than saving one large commit for the very end of a
session. Do this incrementally: commit a logical chunk of work as soon as
it is stable and tested, instead of accumulating everything and hoping
there is enough budget left at the end to commit it all at once.

Losing uncommitted work when a session ends abruptly, gets compacted, or a
subagent runs out of budget is expensive to redo — the agent (or the next
one that picks up the session) has to re-derive context and redo work that
was already correct. Only commit code that is actually in a working,
verified state (tests passing, no half-finished edits) — this rule is
about not *delaying* commits of good work, not about committing broken
work just to beat a deadline.
