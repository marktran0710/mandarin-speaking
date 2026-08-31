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

## Layout design and target audience principles

The target users are adult learners (18+) who are thoughtful, educated, and focused
on making steady progress. Design the layout to feel polished, calm, purposeful,
and trustworthy rather than childish, noisy, or gamified for its own sake.

1. **Keep the experience compact and content-first.** Prefer a clear hierarchy,
   aligned sections, predictable spacing, and concise cards. Remove decorative
   elements, labels, metrics, badges, or helper copy when they do not improve
   comprehension or the next decision.

2. **One function, one place.** Do not add duplicate navigation, repeated
   settings, mirrored controls, or multiple actions that lead to the same result.
   Reuse an existing component and flow when it already solves the problem. Every
   new control must have a distinct user need and a clear reason to exist.

3. **Prefer simple, obvious interaction.** Give each context one primary action,
   make the available next step easy to scan, and avoid unnecessary modals,
   multi-step flows, hidden gestures, or configuration. Use familiar language and
   preserve the user's mental model across screens.

4. **Design for mature learners.** Use restrained visual emphasis, readable
   typography, meaningful status colors, and professional copy. Avoid toy-like
   illustrations, excessive rounded containers, ornamental gradients, confetti,
   arbitrary progress mechanics, or decorative gamification unless it directly
   supports learning motivation or feedback.

5. **Treat layout quality as a product requirement.** Before shipping a screen,
   check that headings, controls, content, and actions form a compact rhythm with
   no unexplained dead space, duplicated information, or competing visual focal
   points. Responsive layouts must preserve the same clarity and must not add
   controls merely because there is room on larger screens.

6. **Question scope before implementation.** When a request suggests a new
   feature, first verify whether the need can be met by simplifying, relabeling,
   or repositioning an existing feature. Do not invent dashboard metrics,
   shortcuts, filters, or secondary actions without evidence that they are
   necessary for the learning task.

7. **Use a shared grid for every composed layout.** Treat each page as a
   small, deliberate grid: use one content container, shared horizontal
   gutters, and consistent column lines so headings, controls, cards, and
   footers have aligned left and right edges. Repeating cards should use the
   same column widths and gaps, with equal row heights when their content
   permits. Prefer `grid-template-columns: repeat(..., minmax(0, 1fr))`, token
   spacing, and `align-items: stretch` over per-component offsets, arbitrary
   widths, or nested margins that create drift. On smaller screens, collapse
   the grid while preserving the same page gutter and alignment rhythm.

8. **Keep composed components visibly separated.** Every sibling component or
   section needs a deliberate gap; components must not touch edge-to-edge
   unless they are an intentional segmented control, table, or continuous
   surface. Use the spacing tokens (`--space-xs` for related controls,
   `--space-sm` for adjacent components, and `--space-md` or larger between
   sections) through a parent `gap` or a clearly owned section margin. After
   changing layout, inspect the rendered boundary between each major sibling
   and fix any zero-gap pair before shipping. Preserve the same rhythm when a
   grid collapses on smaller screens.

9. **Keep spacing consistent at the same hierarchy level.** Reuse one token
   for the same relationship across components and responsive variants:
   `--space-2xs` for intentional micro-label spacing, `--space-xs` inside a
   control or compact row, `--space-sm` between related components, and
   `--space-md` or larger between sections. Prefer a parent `gap` over mixed
   child margins, and do not alternate nearby raw values such as 8px, 10px,
   12px, and 14px for the same relationship. A zero gap is allowed only for
   an intentionally continuous surface (for example a table row or a
   segmented control); document that exception in the selector. Audit every
   breakpoint after changing the base rhythm so mobile and desktop do not
   drift apart.

10. **Prefer horizontal composition when the content can remain readable.**
    On desktop and tablet, place related content in a deliberate row: icon
    beside its label, media beside its supporting copy, and action beside the
    context it affects. Use equal grid tracks, `minmax(0, 1fr)`, and token
    gaps instead of stacking short pieces vertically. Collapse to a column
    only when the available measure would make text wrap, controls shrink, or
    the primary action harder to scan; keep the same gutter and spacing rhythm
    after that collapse.

11. **Fit the desktop viewport; let mobile flow naturally.** For student-facing
    desktop layouts (`min-width: 901px`), the application shell should occupy
    the available dynamic viewport with `height: 100dvh` and avoid a
    document-level scrollbar in the normal state. Build this with stretched
    grid/flex tracks and `min-height: 0`: fixed rails and headers stay
    `flex-shrink: 0`, while the main content panel owns any necessary
    `overflow: auto` so long feedback, zoomed text, and real data remain
    reachable. Do not use guessed `calc(100dvh - Npx)` offsets. On mobile
    (`max-width: 900px`), use natural page flow with `min-height: 100dvh`,
    allow vertical page scrolling, and prevent horizontal overflow.

## Git branch naming

Do not use `codex/` as a branch-name prefix in this repository. Branch names
must be descriptive without that prefix, for example
`backend-refactor-500-lines`.

## Tone-evaluation code: warn before editing

Before changing anything in the tone-scoring/verdict path — `backend/tone_decision.py` (thresholds: `TONE_CONFIRM_THRESHOLD`, `TONE_ERROR_THRESHOLD`, `SHAPE_STRONG`, `SHAPE_WEAK`, `DIRECTION_SUPPORT`, `DIRECTION_BAD`, `PHRASE_RESCUE_SHAPE_STRONG`, `PHRASE_RESCUE_DIRECTION_SUPPORT`), `backend/chinese_tones.py` (shape/direction heuristics), `backend/praat_analyzer.py` (`_combine_word_verdict`, `_apply_phrase_rescue`, syllable/word promotion logic), or the sentence-level pass gate (`SENTENCE_SYLLABLE_PASS_RATIO`, `build_pronunciation_mastery` in `main.py`) — explain the concrete before/after impact to the user (real numbers, ideally a real sentence) and get explicit confirmation before implementing. Do not ship a threshold or verdict-logic change silently, even a "small" one.

These thresholds directly decide whether a real student's recording is graded ✓/△/✗ and are explicitly unvalidated against human raters (the code's own comments call them "ENGINEERING DEFAULTS, not calibrated cutoffs"). A change here shifts grading leniency/strictness across every student in both directions, and the test suite cannot catch "this is now too lenient/strict" on its own since tests just encode whatever the new thresholds produce.

## Frontend UI/CSS discipline

The student-facing UI has repeatedly shipped "looks fine in the diff, breaks
on screen" bugs — a results screen whose action buttons got clipped by a
viewport-height clamp, a footer glued to a self-eval Skip button by a
zeroed-out margin, a two-column layout that dumped 100+px of dead space in
front of a shorter column. Every one of these came from the same handful of
root causes, so the fix is a small, mandatory set of constraints, not more
one-off patches. Follow these when writing or reviewing ANY CSS in
`frontend/src`:

1. **Tokens only, never invented values.** Colors, radii, and spacing come
   from the tokens defined in `src/styles/index/01-tokens-surfaces.css`
   (`--clay-*`, `--seal*`, `--jade*`, `--gold*`, `--tone1*`, `--space-*`,
   `--clay-radius-sm/md/lg/xl/pill`). A hardcoded hex color or a
   border-radius that isn't one of the five scale values (8/14/20/28/999px)
   is a bug to fix, not a style choice — it's how the app has quietly grown
   three different visual systems before. The one standing exception is a
   true one-off (clearing an absolutely positioned sibling, a decorative
   micro-radius ≤5px) — leave a comment saying so when you use it.

2. **Use a safe desktop viewport shell.** Do not use guessed
   `calc(100dvh - Npx)` offsets, viewport clamps, or an `overflow: hidden`
   wrapper that has no reachable inner scroller. The student shell may use
   `height: 100dvh` on desktop when its grid/flex children have
   `min-height: 0`, fixed chrome is non-shrinking, and the content panel owns
   `overflow: auto`. This keeps the normal desktop state within the viewport
   without clipping long feedback. Mobile remains auto-height and uses normal
   page scrolling. A shared action footer must stay reachable with
   `flex-shrink: 0`, never by hiding overflow around it.

3. **One CSS source of truth per selector per state.** Before adding a rule
   that touches `.some-shared-class`, grep for every existing rule that
   already touches it. If a shared component needs a variant-specific
   override (e.g. a `:has()`-scoped alternate layout), that override's
   selector must be either (a) provably higher specificity than what it's
   replacing — verify by counting classes, don't guess — or (b) live in the
   same file immediately after what it overrides, with a comment saying so.
   Two files at *equal* specificity fighting over the same property,
   resolved only by import order, is exactly how a "fixed" bug came back
   under a different variant three separate times in one session.

4. **CSS Grid rows share height across all cells — `align-items` does not
   change that.** A grid row (or a flex row without `flex-direction:
   column`) is always as tall as its tallest cell, full stop.
   `align-items: start/center` only changes where a *shorter* cell's own
   content sits inside that shared height — it does not let the shorter
   cell's box end early. If two columns can have very different natural
   content lengths (an image next to a variable-length text block), either
   cap the taller one's height so the mismatch stays small, or don't put
   them in a shared row at all. Don't reach for `align-items` as the fix
   for "there's a gap after the short column" — it isn't one.

5. **Use image-based icons, not canvas or hand-drawn SVG.** New or edited UI
   uses the shared image-icon component and colorful raster assets (prefer
   transparent PNG, WebP, or AVIF) from the central icon library. Keep one
   coherent illustrated icon family with the same artboard, optical size,
   padding, and visual weight; do not mix random stock icons, emoji, canvas
   drawings, or per-page image files. Existing `StudentIcon` and
   `shared/ui/Icon` SVG aliases should be migrated behind the shared
   image-icon API when those surfaces are touched. Directional and status
   icons follow the same image system rather than becoming text glyphs.
   Every meaningful image icon still needs an accessible name/alternative;
   decorative icons must be hidden from assistive technology, and icon
   controls must preserve the existing touch-target minimum.

6. **Verify layout changes against a real render, not just the diff.**
   `getBoundingClientRect()` in an actual browser (a throwaway Vite entry
   mounting the component with realistic mock props is enough — see any
   `debug-*.tsx` pattern used during development, delete it before
   committing) catches what reading CSS cannot: which rule actually won
   the cascade, and what the real pixel gap is. Three CSS-only guesses at
   the same layout bug in one session, each "should work" but didn't
   (verified afterward, in the browser, to be wrong), is the sign this
   step was skipped — do it before claiming a layout fix is done, not
   after a fourth report that it isn't.

7. **Let one outer frame own the surface, but keep a content inset.** When
   a parent frame owns the border, radius, background, or shadow, its direct
   activity/content child must not draw a competing border, radius, shadow,
   or opaque surface. Removing that inner border does not mean using
   `padding: 0`: preserve a visible inset with spacing tokens (normally
   `--space-sm` vertically and `--space-md` horizontally), or with an
   equivalent parent gap, so content never touches the frame edge. Keep the
   token gap between sibling columns and sections. A zero gap is allowed
   only when adjacent pieces intentionally form one continuous surface (for
   example, tabs and their panel); add a selector comment documenting that
   exception. For fixed-height desktop stages, pair the inset with
   `min-height: 0` and a reachable local scroller so the inset does not
   create dead space or clip the activity.

## Automation tests for UI/UX: rules, not just "add a test"

Writing a test that renders green proves nothing by itself — this session
shipped one that always passed regardless of the bug it claimed to check
(`queryByRole("button", { name: /Start recording/ })` — "Start recording"
was never real text in this app, invented for an unrelated design mockup).
A UI test earns its place in the suite only if it follows all of these:

1. **Prove the test can fail before trusting it.** After writing a
   regression test, temporarily re-introduce the bug (revert the fix, or
   comment out the guard) and run that one test — it must fail. Then
   restore the fix and confirm it passes again. A test nobody has watched
   fail is a test that might be silently checking nothing. This is not
   optional rigor for "important" tests — it's the only way to know the
   assertion is wired to the right thing at all, and it takes under a
   minute.

2. **Assert on real copy, not remembered or invented copy.** Before writing
   `getByText`/`getByRole(..., { name })`, find the actual string in the
   source — grep the component's JSX or the relevant `src/i18n/*.json` key
   — don't recall it from a design mockup, an earlier screenshot, or what
   "sounds right." This is especially dangerous for a *negative* assertion
   (`queryBy...`.`not.toBeInTheDocument()`): if the text was never real,
   the assertion trivially passes on every run, pretend-testing something
   that was never at risk.

3. **`getByText` breaks on `BiLabel`-wrapped copy — use `getByRole` with a
   `name` instead.** `BiLabel`/`BiText` render the Chinese, pinyin, and
   English strings as separate sibling text nodes; a query whose pattern
   matches more than one of those nodes throws "multiple elements found,"
   not a clean pass or fail. Query the containing element by its ARIA role
   and accessible name (`getByRole("heading", { name: /.../ })`,
   `getByRole("button", { name: "..." })`) — the accessible name computation
   concatenates the sibling text nodes into one string, so one query
   reliably matches instead of fighting the DOM split.

4. **Mock the exact module path the component under test imports, and
   verify the mocked function names against the real exports.** A typo'd
   key in a `vi.mock(..., async (importOriginal) => ({ ...actual, wrongName:
   ... }))` doesn't error — `...actual` silently keeps exporting the real
   implementation next to your unused mock, and the component keeps calling
   the real (probably network-dependent) function. Grep the target file for
   `export function <name>` to confirm the name before relying on the mock.

5. **A green Vitest/RTL suite proves logic, not pixels.** jsdom has no real
   layout engine — it cannot see a clipped button, a centered vs. dumped
   gap, or a broken responsive breakpoint. Behavioral assertions (this
   screen shows before that fetch resolves, this click leads to that state,
   this element is/isn't present) belong in the automated suite. A claim
   that a *visual* layout bug is fixed needs verification against a real
   browser render (see "Verify layout changes against a real render" above)
   — reporting a passing test suite as proof of a layout fix is a
   category error, not a stronger form of evidence.

6. **Keep assertions non-redundant.** Don't add a second `waitFor` (or a
   duplicate query) that re-checks exactly what an already-awaited
   `findBy*` just confirmed — it adds no coverage, just noise that makes
   the test harder to read and slower to run. If more time is genuinely
   needed for a background effect to settle, say so in a comment and make
   the wait meaningfully different from what already happened (e.g. wait
   for a *second*, independent condition), not a copy of the first check.

7. **Check `src/test/setup.ts` before adding boilerplate.** It already runs
   `localStorage.clear()` before every test — don't re-add that per-file
   or per-test "to be safe." Know what the global setup already guarantees
   before duplicating it.

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
