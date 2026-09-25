# Agent Coding Rules

## 1. Core Development Philosophy

Use this development direction:

> **Architecture: Top-down**  
> **Implementation: Bottom-up**  
> **Integration: Incremental**  
> **Verification: End-to-end**

Do not immediately start coding from the visible bug, UI request, or isolated backend issue.

Before modifying code:

1. Understand the existing architecture.
2. Audit whether the existing architecture is still appropriate.
3. Compare it against the target architecture defined in this document.
4. Identify the feature boundary.
5. Trace the full data flow.
6. Identify reusable primitives already available.
7. Decide which layer owns each responsibility.
8. Implement the smallest reliable pieces first.
9. Assemble them into the larger feature.
10. Verify the complete user flow.

General pattern:

```text
Requirement
    ↓
Current Architecture Audit
    ↓
Target Architecture
    ↓
Architecture Gap
    ↓
Feature Architecture
    ↓
Data / API Contract
    ↓
Reusable Primitives
    ↓
Small Functions / Components
    ↓
Feature Modules
    ↓
Page / Endpoint Integration
    ↓
End-to-End Verification
    ↓
Final Diff Audit
```

---

# 2. Never Code Before Understanding the Existing System

Before editing a feature, inspect the full path:

```text
Page / Route
↓
Feature Container
↓
Components
↓
Hooks / State
↓
Service / API Client
↓
Backend Endpoint
↓
Application Service
↓
Domain Logic
↓
Persistence / Analytics
```

Do not modify the first file that appears relevant.

First determine:

- Where the data originates.
- Who owns the state.
- Where business logic belongs.
- Which components already exist.
- Which design tokens and styles already exist.
- Which shared primitives are being reused.
- Which APIs are involved.
- Whether the change affects other flows.
- Whether the current implementation reflects a deliberate architecture or accumulated legacy code.

For every non-trivial task, create a short implementation map before coding.

Example:

```text
Feature: Vocabulary Mastery Result

Frontend:
VocabularyResultPage
 ├── MasterySummary
 ├── WeakWordList
 └── ContinuePracticeCTA
        ↓
useVocabularyResults()
        ↓
vocabularyApi.getResults()

Backend:
GET /api/vocabulary/results
        ↓
VocabularyService
        ↓
BKTMasteryService
```

---

# 3. Mandatory Current Architecture Audit

Before implementing any medium or large feature, the agent MUST review the current architecture and compare it against the architecture rules defined in this document.

Do not assume the current structure already follows these rules.

The purpose of this audit is to determine:

```text
Current Architecture
        ↓
Target Architecture
        ↓
Architecture Gaps
        ↓
Safe Migration Path
        ↓
Implementation
```

The agent must first identify how the current system is actually organized.

Inspect at minimum:

## Frontend

- Page structure
- Feature boundaries
- Shared components
- Hooks
- State ownership
- API/service layer
- CSS architecture
- Design tokens
- Shared layout primitives
- Existing naming conventions
- Existing responsive behavior
- Existing loading/error/empty patterns

## Backend

- Routes/controllers
- Services
- Domain logic
- Repositories
- Schemas/contracts
- Configuration
- Algorithm modules
- Tests
- Logging
- Persistence boundaries

Then classify the current implementation.

For each relevant part, determine whether it is:

```text
KEEP
    Existing architecture is already correct.

EXTEND
    Existing pattern is correct and can support the new requirement.

REFACTOR LOCALLY
    Architecture is inconsistent, but only the affected feature needs restructuring.

MIGRATE GRADUALLY
    Existing architecture differs significantly from the target architecture,
    but changing everything at once would create unnecessary risk.

REPLACE
    Existing implementation is fundamentally incorrect, duplicated,
    or impossible to safely extend.
```

The agent MUST NOT automatically preserve existing architecture simply because it already exists.

> Existing code is evidence of the current system, not automatically the preferred architecture.

At the same time, the agent MUST NOT perform a full-system rewrite merely because the current architecture differs from the target architecture.

Use this decision rule:

```text
Existing pattern good
        ↓
Follow it

Existing pattern acceptable but incomplete
        ↓
Extend it

Existing pattern inconsistent
        ↓
Refactor affected area

Existing pattern fundamentally wrong
        ↓
Replace the smallest safe boundary

Large legacy architecture problem
        ↓
Migrate incrementally
```

---

# 4. Architecture Conformance Report

Before coding a medium or large task, produce a short architecture assessment.

Required format:

```text
CURRENT ARCHITECTURE

Frontend:
...

Backend:
...

CURRENT PROBLEMS

1. ...
2. ...
3. ...

TARGET ARCHITECTURE

...

GAPS

Current                         Target
------------------------------------------------
Business logic in component  → Domain/service
Local magic values           → Single config
Duplicated CSS               → Shared tokens
Large page component         → Feature modules

DECISION

KEEP:
...

EXTEND:
...

REFACTOR:
...

DO NOT TOUCH:
...

IMPLEMENTATION BOUNDARY:
...
```

The report does not need to be long.

Its purpose is to prevent the agent from blindly adding new code to an already inconsistent architecture.

---

# 5. New Code Must Follow the Target Architecture

After the architecture audit, all newly created code MUST follow the target architecture unless there is a documented compatibility reason not to.

Do not copy a bad legacy pattern merely for consistency.

For example, if the current code contains:

```text
Page Component
├── API calls
├── Business logic
├── BKT calculations
├── State logic
├── Navigation
└── CSS decisions
```

do NOT create another page using the same pattern.

Instead migrate the affected feature toward:

```text
Page
↓
Feature Container
↓
Hook / Controller
↓
Service
↓
Domain Logic
```

Use legacy code as compatibility context, not automatically as an architectural template.

---

# 6. Follow Existing Patterns Only When They Are Good Patterns

The rule:

> Search first, reuse second, extend third, create new last.

does NOT mean:

> Copy whatever pattern already exists.

Before reusing an existing pattern, verify that it follows the architecture rules.

Use:

```text
Existing pattern found
        ↓
Does it follow current architecture rules?
        ↓
      YES → reuse / extend
        ↓
       NO
        ↓
Can it be locally improved safely?
        ↓
      YES → refactor + reuse
        ↓
       NO
        ↓
Create the correct pattern at the smallest safe boundary
```

Consistency with bad architecture is not a goal.

Consistency with the target architecture is the goal.

---

# 7. Incremental Architecture Migration

Do not stop feature development solely because the legacy architecture is imperfect.

Instead use every relevant task as an opportunity to improve the affected area.

Example:

```text
Before

VocabularyPage.tsx
    ├── UI
    ├── API
    ├── BKT
    ├── Scheduling
    └── Progress Logic
```

When modifying vocabulary practice:

```text
After

VocabularyPage
    ↓
VocabularyPracticeFlow
    ↓
useVocabularyPractice
    ↓
practiceService
    ↓
BKT / Scheduling Domain
```

Do not simultaneously refactor Speaking, Placement, and unrelated modules unless required.

Principle:

> **Leave the touched architecture better than you found it, without expanding the task unnecessarily.**

---

# 8. Architecture Debt Must Be Reported

If the agent discovers architecture problems outside the task boundary, do not silently modify them.

Report them separately.

Example:

```text
ARCHITECTURE DEBT FOUND

Not required for this task:

1. Speaking and Vocabulary duplicate PracticeCard behavior.
2. Three different mastery thresholds exist.
3. Shared CSS layout has four feature-specific overrides.
4. API types are duplicated between frontend and backend.

Recommended future work:
...
```

Only fix them during the current task if they block correctness or create high regression risk.

---

# 9. Architecture Review Is Required Before Adding New Abstractions

Before adding any of the following:

```text
New service
New shared component
New global hook
New design token
New API abstraction
New state store
New domain module
New utility layer
New configuration system
```

the agent must verify:

```text
Does an equivalent already exist?

Is the existing equivalent architecturally correct?

Can it be extended safely?

Would creating another abstraction introduce duplication?

Should the existing abstraction be migrated instead?
```

Do not create parallel architectures.

Avoid ending up with:

```text
api/
services/
apiServices/
clients/
network/
```

all solving the same problem.

Choose one canonical architecture and migrate toward it.

---

# 10. Architecture Source of Truth

This document defines the preferred target architecture.

Priority when deciding architecture:

```text
1. Explicit requirements for the current task
2. AGENT_RULES.md
3. Approved project architecture / contracts
4. Existing good patterns
5. Legacy implementation
```

Legacy code must not override an explicitly defined newer architecture rule.

If existing code conflicts with this document:

```text
Do not blindly copy it.
Do not rewrite everything.

Identify the conflict.
Choose the smallest safe migration.
Document the decision.
Implement toward the target architecture.
```

---

# 11. Separate Architecture Decisions From Implementation

Do not invent architecture while writing JSX, CSS, route handlers, or service code.

First decide:

```text
What is the feature?
What are its boundaries?
What is shared?
What is feature-specific?
What is UI logic?
What is orchestration logic?
What is domain logic?
What belongs to the backend?
What is the API contract?
```

Avoid this:

```text
component.tsx
  + fetching
  + BKT calculation
  + formatting
  + business rules
  + navigation
  + CSS decisions
```

Prefer:

```text
Component
↓
Hook / Controller
↓
Service / Client
↓
Domain Logic
```

---

# 12. Implementation Should Be Bottom-Up

Once the architecture is understood, implement from the smallest stable unit upward.

Preferred order:

```text
Types / Contracts
↓
Pure Utilities
↓
Domain Functions
↓
Service Functions
↓
Hooks / Controllers
↓
Small UI Components
↓
Feature Container
↓
Page Integration
```

Example:

Instead of immediately creating:

```text
SpeakingResultsPage.tsx
```

with hundreds of lines, first create or verify:

```text
calculateSpeakingScore()
formatFeedback()
getToneStatus()

SpeakingScoreBadge
FeedbackRow
SpeakingResultsSummary
```

Then assemble:

```text
SpeakingResultsPage
```

---

# 13. One File = One Clear Responsibility

Every file should answer one main question.

Good:

```text
bkt.ts
bktMastery.ts
bktValidation.ts

SpeakingScoreCard.tsx
SpeakingFeedbackList.tsx
SpeakingResultsFlow.tsx
```

Bad:

```text
utils.ts
helpers.ts
common.ts
everything.ts
SpeakingPage.tsx
```

Avoid generic dumping-ground files.

---

# 14. File Size Guidelines

These are guidelines, not strict rules.

## Frontend

```text
Pure utility:
20–100 lines

Small UI component:
30–150 lines

Feature component:
80–250 lines

Hook / controller:
50–200 lines

Page / container:
100–300 lines
```

If a React component approaches roughly `300–400` lines, inspect whether responsibilities should be separated.

If a file exceeds roughly `500` lines, splitting should normally be considered.

Do not split files only to reduce line count.

Split when there are separate responsibilities.

---

# 15. Function Size Rules

Functions should perform one conceptual operation.

Prefer:

```ts
validateAnswer()
calculateMastery()
buildPracticeQueue()
formatNextReviewDate()
```

Avoid:

```ts
processEverything()
handleAllPracticeLogic()
doStuff()
```

Typical target:

```text
5–40 lines
```

Longer functions are acceptable when the algorithm itself is inherently cohesive.

Extract a function when:

- It has a meaningful independent name.
- It is reused.
- It contains independent business logic.
- It can be tested independently.
- It reduces cognitive complexity.

Do not create meaningless wrappers only to reduce line count.

---

# 16. Frontend Component Hierarchy

Use this hierarchy where appropriate:

```text
Page
└── Feature Container
    ├── Section
    │   ├── Component
    │   └── Component
    └── Section
        └── Component
```

Example:

```text
VocabularyPracticePage
└── VocabularyPracticeFlow
    ├── PracticeHeader
    ├── QuestionStage
    │   ├── QuestionPrompt
    │   ├── AnswerOptions
    │   └── FeedbackMessage
    └── PracticeFooter
        ├── ProgressIndicator
        └── ContinueButton
```

Pages should mainly coordinate features.

Pages should not contain the complete feature implementation.

---

# 17. Separate UI From Business Logic

React components should mainly answer:

> What should the user see?

They should not contain complicated domain calculations.

Bad:

```tsx
const mastery =
  pKnown * (1 - slip) /
  (pKnown * (1 - slip) + (1 - pKnown) * guess);
```

inside a UI component.

Better:

```ts
const result = calculateBKTMastery(input);
```

Then:

```tsx
<MasteryBadge value={result.mastery} />
```

The following logic should normally live outside presentation components:

- BKT
- SRS
- scoring
- quiz selection
- mastery rules
- scheduling rules
- experimental conditions
- question-generation rules

---

# 18. Single Source of Truth

Never maintain the same rule independently in multiple places.

Bad:

```text
Frontend:
PASS_SCORE = 14

Backend:
PASS_SCORE = 15

Quiz config:
PASS_SCORE = 14
```

Good:

```text
quizConfig
    ↓
shared contract / backend response
    ↓
frontend display
```

Important rules should have one authoritative owner.

Examples:

- Pass thresholds
- Quiz rounds
- Mastery thresholds
- BKT parameters
- Practice caps
- Scheduling intervals
- Question types
- Lesson metadata
- Experimental conditions
- Feature flags

---

# 19. Frontend Styling Rules

Do not create new visual rules before checking existing styles.

Search in this order:

```text
Design Tokens
↓
Shared Primitives
↓
Shared Layout Classes
↓
Feature-Specific Styles
↓
New Styles
```

Reuse existing:

- Spacing scale
- Font sizes
- Line heights
- Radius
- Shadows
- Borders
- Button styles
- Card styles
- Form controls
- Breakpoints
- Typography rules
- Layout primitives

Avoid random values such as:

```css
margin-top: 13px;
border-radius: 11px;
font-size: 17px;
```

unless explicitly required.

Prefer tokens:

```css
gap: var(--space-3);
padding: var(--space-4);
border-radius: var(--radius-md);
```

---

# 20. Do Not Fix Shared CSS With Blind Local Overrides

Before modifying CSS, trace the cascade.

Determine whether a class is:

```text
Global
Shared
Feature-specific
Component-specific
```

Do not solve a feature issue with:

```css
!important
```

unless there is a documented exceptional reason.

Avoid override chains such as:

```css
.practice-workspace { ... }

.speaking .practice-workspace { ... }

.student .speaking .practice-workspace { ... }

.practice-workspace.override { ... }
```

If two layouts are conceptually different, create a feature-specific layout rather than accumulating overrides.

---

# 21. UI Consistency Rule

Before creating a new UI pattern, inspect similar screens.

Compare:

- Header hierarchy
- Section spacing
- Cards
- Buttons
- Form controls
- Progress indicators
- Typography
- Mobile layout
- Empty states
- Loading states
- Error states
- CTA placement

If a reusable pattern already exists and is architecturally good, reuse it.

Do not create:

```text
PlacementButton
SpeakingButton
VocabularyButton
StudyButton
```

with different visual behavior unless there is a real design reason.

Prefer shared primitives with controlled variants.

---

# 22. Prefer Composition Over Duplication

If multiple components share structure, do not copy the entire component.

Extract the stable primitive.

Example:

```text
PracticeCard
├── SpeakingPracticeCard
├── VocabularyPracticeCard
└── ListeningPracticeCard
```

However, do not create overly generic components with excessive flags.

Bad:

```tsx
<Card
  speaking
  vocabulary
  compact
  result
  showAudio
  hideHeader
  customFooter
/>
```

If variants become structurally different, separate them.

---

# 23. Feature Folders Should Be Cohesive

Recommended frontend structure:

```text
src/
├── app/
├── components/
│   └── shared/
├── features/
│   ├── speaking/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── utils/
│   │   ├── types.ts
│   │   └── index.ts
│   │
│   ├── vocabulary/
│   ├── placement/
│   └── study/
│
├── services/
├── styles/
├── types/
└── utils/
```

Do not move every component into a global `components/` directory.

Feature-specific code should remain close to the feature.

---

# 24. Backend Layer Responsibilities

Use clear layers.

Recommended conceptual structure:

```text
Route / Controller
↓
Application Service
↓
Domain Logic
↓
Repository / External Service
```

Example:

```text
POST /practice/answer
↓
PracticeService.submitAnswer()
↓
BKTUpdater.update()
↓
PracticeRepository.saveAttempt()
```

## Controller / Route

Responsible for:

- Request parsing
- Authentication
- Schema validation
- HTTP status
- Response serialization

It should not contain BKT, scheduling, mastery, or experiment algorithms.

## Application Service

Responsible for:

- Workflow
- Orchestration
- Business use cases

Example:

```text
Submit Answer
→ Update BKT
→ Calculate Next Review
→ Save Attempt
→ Return Result
```

## Domain Layer

Responsible for:

- Algorithms
- Business rules
- Transformations
- Calculations

Examples:

```text
BKT
SM-2
Mastery rules
Quiz selection
Practice opportunity caps
Scoring
Fixed scheduling
Yoked scheduling
```

## Repository Layer

Responsible for:

- Database access
- Persistence
- File storage
- External storage adapters

Do not place domain decisions inside repositories.

---

# 25. Keep Domain Functions Pure When Possible

Prefer:

```python
def update_mastery(previous_state, observation, params):
    ...
    return new_state
```

over:

```python
def update_mastery(user_id):
    db = ...
    fetch(...)
    calculate(...)
    update(...)
    log(...)
```

Pure functions are easier to:

- Understand
- Test
- Compare experimentally
- Reproduce in research
- Debug

This is especially important for:

- BKT
- SM-2
- Fixed schedule
- Yoked schedule
- Question selection
- Mastery classification
- Practice caps

---

# 26. API Contract First

Before implementing frontend and backend independently, define the contract.

Example:

```ts
type PracticeAnswerResponse = {
  correct: boolean;
  masteryBefore: number;
  masteryAfter: number;
  nextReviewAt: string | null;
  remainingItems: number;
};
```

Backend and frontend should conform to the same conceptual model.

Never make the frontend infer hidden backend behavior from unrelated fields.

---

# 27. Do Not Leak Backend Domain Models Directly Into the UI

Backend may contain:

```text
pKnown
guess
slip
transition
schedulerState
experimentalCondition
```

The frontend may only need:

```text
mastery
status
nextReview
progress
```

Use presentation-oriented responses where appropriate.

Do not couple the UI directly to internal algorithm implementation.

---

# 28. Use Explicit State Machines for Complex Flows

Do not manage complex workflows with many unrelated booleans.

Bad:

```ts
isRecording
isFinished
isEvaluating
showFeedback
showResults
isRetry
```

Prefer:

```ts
type SpeakingStage =
  | "prompt"
  | "recording"
  | "processing"
  | "self-evaluation"
  | "feedback"
  | "completed";
```

Then:

```text
prompt
→ recording
→ processing
→ self-evaluation
→ feedback
→ completed
```

Complex learning flows should have explicit stages.

---

# 29. Avoid Boolean Explosion

Bad:

```tsx
<Component
  compact
  speaking
  result
  showScore
  hideActions
  showRetry
  student
/>
```

Prefer explicit models:

```tsx
<SpeakingResultCard
  result={result}
  mode="student"
/>
```

If behavior differs substantially, create separate components.

---

# 30. Name Things by Domain Meaning

Avoid:

```text
data
item
thing
value2
temp
handleStuff
processData
finalResult2
```

Prefer:

```text
practiceAttempt
masteryEstimate
reviewSchedule
questionDifficulty
learningItem
feedbackResult
```

Code should reflect the educational domain.

---

# 31. Comments Explain Why, Not What

Bad:

```ts
// Increment count
count++;
```

Useful:

```ts
// Practice opportunities are capped so the BKT group
// does not receive more exposure than the control group.
```

Important research decisions should be documented near the implementation.

---

# 32. No Opportunistic Refactoring

When implementing Feature A, do not simultaneously rewrite:

- Unrelated components
- Unrelated CSS
- Unrelated endpoints
- Naming across the whole project
- Other feature architecture

unless required.

Each coding task should have a bounded change surface.

Rule:

> Change the minimum architecture necessary to solve the underlying problem correctly.

Do not follow:

> Change the fewest possible lines regardless of architecture.

---

# 33. Preserve Existing Behavior Unless Change Is Intentional

Before modifying shared code, identify all consumers.

For example:

```text
.practice-workspace
```

may be used by:

```text
Speaking
Vocabulary
Study
Placement
```

Never assume a shared primitive belongs only to the current feature.

Search all usages before modifying it.

---

# 34. Preserve User Changes

Never overwrite or revert existing user work unless explicitly required.

Before editing:

- Check current diff.
- Check uncommitted files.
- Check recently modified files.
- Check whether the code belongs to the current task.

If unrelated user changes exist:

```text
Preserve them.
Work around them.
Do not reset them.
Do not overwrite them.
```

---

# 35. Tests Follow the Architecture

Test from the smallest unit upward.

```text
Pure Function Test
↓
Service Test
↓
Component Test
↓
Feature Integration Test
↓
Critical Browser Flow
```

For algorithms:

```text
input
→ expected output
```

For UI:

Test user-observable behavior rather than implementation details.

---

# 36. Every Bug Fix Should Add a Regression Check

When fixing a bug:

1. Understand why it happened.
2. Identify the correct owner.
3. Fix the root cause.
4. Add a test or validation preventing recurrence.

Do not only patch the visible symptom.

---

# 37. Definition of Done

A task is not complete merely because the code compiles.

## Frontend

```text
□ Architecture is consistent
□ Architecture audit completed
□ Existing good primitives reused where appropriate
□ No bad legacy pattern was copied unnecessarily
□ Desktop checked
□ Tablet checked
□ Mobile checked
□ Loading state checked
□ Empty state checked
□ Error state checked
□ Long content checked
□ Typecheck passes
□ Relevant tests pass
□ No unrelated regression found
```

## Backend

```text
□ Architecture audit completed
□ Request validation exists
□ Domain logic is separated
□ Error behavior is defined
□ Relevant unit tests pass
□ Existing API consumers remain compatible
□ Logging does not expose sensitive data
□ Algorithm behavior is deterministic where required
□ Experimental logic remains auditable
```

---

# 38. Standard Agent Workflow for Medium or Large Tasks

Use:

```text
PLAN
↓
INSPECT
↓
AUDIT ARCHITECTURE
↓
MAP TARGET
↓
IMPLEMENT
↓
TEST
↓
DIFF AUDIT
```

## Phase 1 — Inspect

Read:

```text
Relevant page
Relevant components
Related CSS
State / hooks
API client
Backend endpoint
Service / domain implementation
Existing tests
```

## Phase 2 — Audit Architecture

Determine:

```text
Current architecture
Good patterns
Bad patterns
Legacy constraints
Architecture debt
Target architecture
Migration boundary
```

## Phase 3 — Map

Produce:

```text
Current architecture
Problem root cause
Affected files
Proposed architecture
Migration decision
Risk areas
Tests required
```

## Phase 4 — Build Primitives

Implement:

```text
Types
Pure functions
Utilities
Small components
```

## Phase 5 — Assemble

Connect them into:

```text
Feature module
Page
API flow
```

## Phase 6 — Verify

Run:

```text
Unit tests
Integration tests
Typecheck
Lint
Browser QA when applicable
```

## Phase 7 — Audit Final Diff

Inspect the diff for:

```text
Duplication
Magic values
Dead code
Unnecessary CSS overrides
Architecture violations
Unrelated edits
Missing tests
Parallel abstractions
New technical debt
```

---

# 39. Always Prefer Root-Cause Fixes

When a problem appears, trace downward.

```text
Visible Symptom
↓
Component Issue?
↓
Shared Primitive Issue?
↓
State Architecture Issue?
↓
API Contract Issue?
↓
Service Issue?
↓
Domain Logic Issue?
↓
Persistence Issue?
```

Fix the lowest correct owner.

Example:

```text
Wrong mastery shown
```

Do not immediately patch:

```text
MasteryCard.tsx
```

Trace:

```text
MasteryCard
↓
Hook
↓
API Response
↓
Practice Service
↓
BKT Domain
```

Then correct the actual source.

---

# 40. Do Not Over-Engineer

Do not introduce:

- A new state library for one component
- A new abstraction used once
- A factory for simple objects
- Excessive dependency injection
- Generic frameworks inside the application
- Dozens of tiny files with no independent meaning

Use the simplest architecture that preserves:

```text
Clarity
Testability
Consistency
Extensibility
```

---

# 41. Research-System Specific Rule

Experimental conditions must be separated from learning algorithms.

For example:

```text
BKT ON / OFF
SM-2 / Fixed / Yoked
Practice cap
Experimental group
```

should be explicit configuration rather than scattered conditional statements.

Prefer:

```ts
const experimentConfig = {
  masteryModel: "bkt",
  scheduler: "sm2",
  practiceCap: 30,
};
```

Avoid:

```ts
if (user.group === 2) ...
if (bktEnabled) ...
if (experiment) ...
```

scattered across many components and services.

---

# 42. Experimental Logic Must Be Auditable

Any algorithm that affects research outcomes must have:

```text
Clear inputs
Clear outputs
Versioned parameters
Deterministic behavior where possible
Logs
Tests
```

Examples:

- BKT update
- SM-2 scheduling
- Fixed scheduling
- Yoked scheduling
- Practice opportunity caps
- Mastery thresholds
- Question selection

The UI must never silently change these rules.

---

# 43. Separate Research Logic From Presentation Logic

Do not allow UI code to determine experimental behavior.

Bad:

```tsx
if (group === "bkt") {
  nextQuestions = ...
}
```

inside a component.

Prefer:

```text
UI
↓
Practice Controller
↓
Experiment Configuration
↓
Domain / Scheduler
```

The frontend may display the result.

It should not secretly define the experimental condition.

---

# 44. Practice Opportunity Fairness

If experimental groups are intended to receive equal or capped learning opportunities, enforce this rule in one authoritative backend/domain layer.

Do not rely on UI behavior to ensure fairness.

Track explicitly where appropriate:

```text
attempt count
practice opportunity count
review count
item exposure count
scheduled review count
completed review count
```

Research fairness rules must be testable.

---

# 45. Reuse Before Creating

Before creating a new pattern, component, hook, utility, or style:

1. Search for an existing equivalent.
2. Evaluate whether it is architecturally good.
3. Reuse it if appropriate.
4. Extend it if the conceptual responsibility is the same.
5. Refactor it locally if needed.
6. Create a new implementation only when necessary.

Rule:

> **Never create a new pattern when the codebase already has an established equivalent good pattern. Search first, evaluate second, reuse third, extend fourth, create new only as the last option.**

---

# 46. Avoid Parallel Implementations

Before introducing a new module, check whether an older implementation already handles part of the same responsibility.

Avoid:

```text
bkt.ts
bktMastery.ts
newBktEngine.ts
masteryCalculator.ts
bktUtils.ts
```

unless each has a clearly distinct responsibility.

Likewise avoid:

```text
Button.tsx
AppButton.tsx
PrimaryButton.tsx
ActionButton.tsx
NewButton.tsx
```

without a clear design-system rationale.

When duplication exists, prefer consolidation at the smallest safe scope.

---

# 47. Preferred Development Priority

When making engineering decisions, prioritize:

```text
Correctness
↓
Consistency
↓
Readability
↓
Testability
↓
Reusability
↓
Performance
↓
Cleverness
```

Do not sacrifice architecture clarity for clever code.

---

# 48. Target Full-Stack Architecture

The project should gradually move toward a structure like:

```text
frontend/
├── app/
├── features/
│   ├── placement/
│   ├── vocabulary/
│   ├── speaking/
│   └── study/
├── components/
│   └── shared/
├── design-system/
├── services/
├── types/
└── utils/

backend/
├── api/
├── services/
├── domain/
│   ├── bkt/
│   ├── scheduling/
│   ├── assessment/
│   └── speaking/
├── repositories/
├── schemas/
├── config/
└── tests/
```

Do not perform a massive rewrite only to achieve this structure.

Instead:

> Whenever a feature is modified, improve that feature toward the target architecture without unnecessarily rewriting unrelated parts of the system.

This is:

> **Incremental architecture improvement, not full-system refactoring.**

---

# 49. Frontend Target Responsibility Model

Preferred direction:

```text
Page
↓
Feature Container
↓
Hook / Controller
↓
Frontend Service
↓
API Contract
```

Presentation:

```text
Shared Primitive
↓
Feature Component
↓
Feature Container
```

Avoid:

```text
Page
├── API fetch
├── business logic
├── algorithm
├── navigation
├── responsive decisions
├── state machine
└── 500 lines JSX
```

---

# 50. Backend Target Responsibility Model

Preferred direction:

```text
Route
↓
Application Service
↓
Domain
↓
Repository
```

Example:

```text
POST /practice/answer
        ↓
PracticeService
        ↓
MasteryUpdater
        +
Scheduler
        ↓
AttemptRepository
```

Do not allow:

```text
Route Handler
├── SQL
├── BKT calculation
├── scheduling
├── experiment assignment
├── response formatting
└── logging logic
```

to accumulate in one function.

---

# 51. Design System Consistency

When working on frontend UI, the agent must inspect the existing design system first.

Identify:

```text
Typography scale
Spacing scale
Radius
Colors
Borders
Shadows
Buttons
Inputs
Cards
Responsive breakpoints
Layout primitives
Feedback states
```

If these patterns are inconsistent, do not create another local styling system.

Use one of:

```text
KEEP
EXTEND
REFACTOR LOCALLY
MIGRATE GRADUALLY
```

Prefer central tokens for repeated visual values.

---

# 52. Avoid Magic Values

Repeated numeric or string rules should normally be represented by named configuration.

Bad:

```ts
if (score >= 14) { ... }

if (mastery > 0.8) { ... }

setTimeout(..., 1500)
```

Prefer:

```ts
QUIZ_PASS_THRESHOLD
MASTERY_THRESHOLD
FEEDBACK_DELAY_MS
```

However, do not create constants for meaningless one-off values with no domain significance.

---

# 53. Configuration Ownership

Configuration must have a clear owner.

Examples:

```text
Quiz behavior       → quiz config
Experiment behavior → experiment config
BKT parameters      → BKT config
Scheduler settings  → scheduler config
UI tokens           → design system
API URLs            → environment config
```

Do not scatter configuration throughout components.

---

# 54. Explicit Contracts Between Layers

Each layer should communicate through clearly defined contracts.

Example:

```text
UI
↓
PracticeViewModel

Controller
↓
PracticeServiceInput

Service
↓
DomainCommand

Domain
↓
DomainResult

Repository
↓
PersistenceModel
```

Do not pass raw database rows directly to UI code.

Do not pass React-specific objects into domain logic.

---

# 55. Stable Public APIs, Flexible Internals

Shared modules should expose a small stable public interface.

Example:

```ts
updateMastery()
getMasteryStatus()
```

Internal implementation may change without forcing unrelated callers to change.

Avoid exposing internal helper functions unless necessary.

---

# 56. Prefer Pure Transformations

When possible, structure business logic as:

```text
Input
↓
Pure transformation
↓
Output
```

Then perform side effects separately.

Example:

```text
Read attempt
↓
calculateBKTUpdate()
↓
calculateNextReview()
↓
save result
```

This improves:

- Testability
- Reproducibility
- Debugging
- Research validity

---

# 57. Side Effects Must Be Explicit

Side effects include:

```text
Database writes
Network calls
File writes
Navigation
Timers
Analytics
Logging
Local storage
```

Keep them identifiable.

Do not hide side effects inside functions that appear to be pure calculations.

---

# 58. Logging Rules

Log meaningful system events, not arbitrary implementation details.

Useful:

```text
practice attempt saved
BKT state updated
scheduler decision created
experiment condition assigned
API validation failed
```

Avoid leaking:

```text
passwords
tokens
personal identifiers
sensitive user data
```

Research logs should be structured and reproducible where possible.

---

# 59. Error Handling

Every external boundary must define error behavior.

Examples:

```text
API failure
Database failure
Missing learning item
Invalid experiment config
Invalid scheduler state
Malformed request
```

Do not silently swallow errors.

UI should distinguish when appropriate:

```text
Loading
Empty
Recoverable Error
Blocking Error
Success
```

---

# 60. Responsive Behavior Is Part of the Feature

Frontend work is incomplete until relevant responsive behavior is checked.

At minimum consider:

```text
Desktop
Tablet
Mobile
Narrow mobile
Short viewport
Long text
Large content
```

Do not design only for one viewport.

---

# 61. Accessibility Basics

New frontend work should preserve basic accessibility.

Check:

- Semantic buttons
- Labels
- Keyboard access
- Visible focus
- Disabled states
- Meaningful text
- Sufficient control size
- Correct heading hierarchy where applicable

Do not use clickable `div` elements when a button is appropriate.

---

# 62. Avoid Premature Shared Abstractions

Do not move code into `shared/` simply because two components currently look similar.

Promote to shared only when:

```text
The responsibility is genuinely shared
The API is stable enough
The abstraction reduces duplication
The abstraction does not introduce many flags
```

Two similar-looking components are not automatically one abstraction.

---

# 63. Feature-Specific First, Shared When Proven

For uncertain abstractions:

```text
Feature-specific implementation
↓
Second real use case appears
↓
Compare responsibilities
↓
Extract stable shared primitive
```

Do not design speculative abstractions for hypothetical future features.

---

# 64. No Hidden Cross-Feature Coupling

Feature A should not depend on internal implementation details of Feature B.

Bad:

```text
Vocabulary imports Speaking internal component
```

unless that component is intentionally promoted to shared.

Prefer:

```text
shared primitive
↑            ↑
Vocabulary   Speaking
```

---

# 65. Keep Dependency Direction Clear

Preferred dependency direction:

```text
App
↓
Features
↓
Shared UI / Services
↓
Domain Contracts
```

Domain logic should not depend on React.

Repositories should not determine UI structure.

UI should not own domain rules.

---

# 66. Migration Should Have a Boundary

When improving legacy architecture, define the migration boundary before coding.

Example:

```text
Migration boundary:
Vocabulary practice only

Included:
- VocabularyPracticePage
- practice hook
- practice service
- BKT integration

Excluded:
- Speaking flow
- Placement flow
- unrelated shared CSS
```

Do not let refactoring expand indefinitely.

---

# 67. Compatibility Wrappers Are Allowed Temporarily

If legacy and new architecture must coexist, use a small explicit compatibility layer.

Example:

```text
Legacy API
↓
Adapter
↓
New Domain Contract
```

Do not spread legacy conditionals throughout new code.

Temporary adapters should be documented.

---

# 68. Remove Dead Compatibility Code When Safe

After migration is complete:

```text
Confirm no consumers remain
↓
Remove adapter
↓
Remove dead code
↓
Run regression tests
```

Do not keep obsolete architecture indefinitely without reason.

---

# 69. Final Agent Checklist

Before creating new code, always ask internally:

```text
Does this already exist?

Is the existing implementation architecturally good?

Which layer should own this?

Can this be a pure function?

Is this shared or feature-specific?

Will another feature accidentally be affected?

Am I fixing the root cause or only the symptom?

Is there already a design pattern for this?

Is there already a backend pattern for this?

Am I creating a parallel architecture?

Can another developer understand this six months later?

Can this behavior be tested independently?

Does this change preserve existing research behavior?

Does this introduce another source of truth?

Should this area be kept, extended, refactored, migrated, or replaced?

What is the smallest safe migration boundary?
```

If these questions cannot be answered, inspect the codebase further before implementing.

---

# 70. Required Agent Output Before Medium/Large Implementation

Before coding, provide a concise plan containing:

```text
1. Current architecture
2. Relevant problems
3. Target architecture
4. Keep / Extend / Refactor / Migrate / Replace decisions
5. Files expected to change
6. Files explicitly not being changed
7. Implementation order
8. Tests / validation
9. Main regression risks
```

The plan should be short enough to act on, but detailed enough to expose architecture mistakes before code is written.

---

# 71. Golden Rule

For all medium or large coding tasks:

> **Understand the current system. Evaluate the current architecture. Design top-down. Implement bottom-up. Migrate incrementally. Verify end-to-end.**

Expected workflow:

```text
Understand the request
        ↓
Inspect the current system
        ↓
Audit current architecture
        ↓
Compare with target architecture
        ↓
Decide Keep / Extend / Refactor / Migrate / Replace
        ↓
Define implementation boundary
        ↓
Define contracts
        ↓
Build small reliable units
        ↓
Test those units
        ↓
Compose larger features
        ↓
Integrate with the application
        ↓
Verify the complete user flow
        ↓
Audit the final diff
        ↓
Report remaining architecture debt
```

Do not jump directly from user request to implementation.

---

# 72. Final Architecture Principle

The goal is NOT:

> Make all old code look identical.

The goal is NOT:

> Rewrite everything into a perfect architecture immediately.

The goal is:

> **Preserve good architecture, stop copying bad architecture, and gradually move every touched area toward one coherent target architecture.**

Use:

```text
Current Architecture
        ↓
Evaluate
        ↓
Preserve Good Patterns
        +
Repair Bad Patterns Locally
        +
Prevent New Inconsistency
        ↓
Target Architecture
```

Every meaningful task should leave the affected part of the codebase:

```text
More consistent
More understandable
More testable
More modular
Less duplicated
Closer to the target architecture
```

---

# 73. Student Mode Page Rules

From the 2026-09 Student Mode UI unification (`shared/ui/student/StudentPage.tsx`). Applies to every screen rendered inside `StudentShell`.

**LAYOUT-1** Every student screen uses `StudentPage` with one layout (`hub` / `task` / `stage`). Do not roll a page's own top-level container.

**LAYOUT-2** Same content left edge on every page — `.sa-page-container`'s `--sa-gutter-desktop`/`--sa-gutter` (24px desktop, 16px mobile). Enforced by `frontend/e2e/student-layout.spec.ts`.

**LAYOUT-3** No outer bordered/backgrounded card around a whole page (`hub` in particular — Study's old card is gone).

**HEAD-1** Exactly one `<h1>` per page, via `StudentPageHeader`, reached through `StudentPage`'s `header` slot.

**HEAD-2** One eyebrow/header markup pattern (`StudentPageHeader`); `eyebrowZh` and `eyebrowEn` are both required — bilingual labels per D2, Chinese primary + English secondary, joined by " · ", everywhere a label is user-facing chrome (nav, eyebrow, in-page labels). No English-only label.

**ACTION-1** One primary action per state, in the footer action bar (`StudentPage`'s `actions` prop), on the right; its label names its destination. A screen with several genuinely different choices (e.g. a mode picker) is not a single "next step" and may keep its own in-content buttons instead of forcing them into one footer primary — do not distort an existing multi-choice UI to satisfy this rule.

**ACTION-2** Primary = solid `--sa-primary` / `--sa-on-primary` (`StudentButton` `variant="primary"`). The light `--sa-primary-container` fill is for a selected/active state only, never the primary action.

**STATE-1** No screen renders empty: `StudentPage`'s `state` is `"loading" | "empty" | "error" | "ready"`; `"empty"` takes `emptyTitle`/`emptyText`/`emptyAction` (a next step), `"error"` takes `errorText`.

**DATA-1** No number on screen without a real data source. Hide a stat/widget entirely rather than show a fabricated or zeroed placeholder (e.g. the sidebar Stars card hides itself when `maxQuizStars === 0`).

**AFFORD-1** Anything that looks like a button is a button (real `<button>`/`StudentButton`, hoverable, clickable). A status indicator (e.g. a lesson's phase chips) has no border/button styling — no `border`, no `cursor:pointer`, no hover state — so it never reads as interactive when it isn't.

**CSS-1** Student UI is unaffected by legacy CSS: legacy stylesheets (`styles/index.css`, `shared-ui.css`) load inside `@layer legacy` on the student entrypoint only; student component CSS stays unlayered so it always outranks legacy rules regardless of import order. Do not wrap new student CSS in `@layer student` — unlayered already wins. Do not add this layering to the teacher/admin entrypoints unless they also gain a competing unlayered design system.

**THEME-1** Offer a theme toggle only when every `--sa-*` colour token has a dark value defined. `shared/styles/student-tokens.css` has none today, so Student Mode has no dark-mode toggle.

without unnecessarily increasing the scope of the task.
