# Vocabulary Table (Pinyin / Part-of-Speech / Translation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the teacher's two separate "Vocabulary" / "Vocabulary Pinyin" text inputs with a single table (Chinese word · pinyin · part of speech · English translation), and surface the two new columns to students as a hover tooltip on the vocab chip.

**Architecture:** Storage stays as four parallel comma-separated strings per frame (`vocabulary`, `vocabularyPinyin`, `vocabularyPos`, `vocabularyTranslation`) — additive, no DB migration, since `custom_stories.frames` is one JSON blob column. A new `VocabularyTable` component zips those four strings into rows for editing and re-serializes back to the same four strings on every change. The existing Grammar Pattern Canvas is hidden behind a module-level `GRAMMAR_CANVAS_ENABLED = false` flag rather than deleted.

**Tech Stack:** React + TypeScript (frontend), FastAPI + Pydantic (backend), Vitest + Testing Library, pytest.

## Global Constraints

- No SQL schema/migration changes — `custom_stories.frames` is a JSON text column; only the Pydantic request model needs the new field names declared, or FastAPI silently drops them.
- Part-of-speech is a fixed dropdown: `N, V, Adj, Adv, MW, Particle, Phrase, Other`. Store the short code itself (e.g. `"N"`).
- Existing stories with only `vocabulary`/`vocabularyPinyin` must load into the new table with empty POS/translation cells — no forced re-entry.
- Grammar Pattern Canvas (`VocabGroupEditor`) must remain in the codebase, gated off, not deleted (the user asked for a *temporary* removal).
- Vocabulary-matching/scoring is untouched — it only ever reads the plain `vocabulary` string; POS/translation never reach the AI feedback prompt.
- Reuse existing design tokens (`--jade`, `--clay-error`, `--clay-hairline`, `--clay-radius-md`, etc.) and the `.custom-story-form input/select` base styling already applied inside the form — don't hardcode colors.

---

### Task 1: Backend accepts the two new optional vocab fields

**Files:**
- Modify: `backend/main.py:273-284` (the `CustomStoryFrameRequest` model)
- Test: `backend/tests/test_custom_stories_vocab_fields.py` (create)

**Interfaces:**
- Produces: `CustomStoryFrameRequest.vocabularyPos: Optional[str]`, `CustomStoryFrameRequest.vocabularyTranslation: Optional[str]` — later tasks' saved stories round-trip these through `POST /api/custom-stories`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_custom_stories_vocab_fields.py`:

```python
"""Confirms vocabularyPos/vocabularyTranslation round-trip through the
custom-stories API instead of being silently dropped by the Pydantic model."""


def test_vocabulary_pos_and_translation_round_trip(client):
    story = {
        "id": "test-vocab-fields-story",
        "title": "Vocab Fields Test",
        "learningGoal": "Check pos/translation persist",
        "level": "Beginner speaking",
        "frames": [
            {
                "imageUrl": "",
                "prompt": "Describe the picture.",
                "vocabulary": "餐廳, 吃",
                "vocabularyPinyin": "cāntīng, chī",
                "vocabularyPos": "N, V",
                "vocabularyTranslation": "restaurant, to eat",
            }
        ],
        "narrativeMode": "describe",
    }

    post_response = client.post("/api/custom-stories", json=story)
    assert post_response.status_code == 200
    saved_frame = post_response.json()["frames"][0]
    assert saved_frame["vocabularyPos"] == "N, V"
    assert saved_frame["vocabularyTranslation"] == "restaurant, to eat"

    get_response = client.get("/api/custom-stories")
    assert get_response.status_code == 200
    fetched = next(s for s in get_response.json() if s["id"] == "test-vocab-fields-story")
    assert fetched["frames"][0]["vocabularyPos"] == "N, V"
    assert fetched["frames"][0]["vocabularyTranslation"] == "restaurant, to eat"

    client.delete("/api/custom-stories/test-vocab-fields-story")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_custom_stories_vocab_fields.py -v`
Expected: FAIL — `assert saved_frame["vocabularyPos"] == "N, V"` raises `KeyError` (or the key is missing/`None`), because the Pydantic model doesn't declare the field yet.

- [ ] **Step 3: Add the two fields to the request model**

In `backend/main.py`, find `class CustomStoryFrameRequest(BaseModel):` (around line 273) and add the two new optional fields, keeping the existing fields as-is:

```python
class CustomStoryFrameRequest(BaseModel):
    imageUrl: str
    prompt: str
    vocabulary: str = ""
    vocabularyGroups: Optional[List[dict]] = None
    grammarPattern: Optional[str] = None
    grammarExample: Optional[str] = None
    vocabularyPinyin: Optional[str] = None
    vocabularyPos: Optional[str] = None
    vocabularyTranslation: Optional[str] = None
    suggestedAnswer: Optional[str] = None
    listenAudioUrl: Optional[str] = None
    listenScript: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_custom_stories_vocab_fields.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `cd backend && python -m pytest tests/ -q`
Expected: same pass/fail counts as before this change (one pre-existing, unrelated flaky failure in `test_asr_unit.py::TestTranscribeAudioContentRouting::test_auto_routes_to_fallback` is expected and not caused by this task).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_custom_stories_vocab_fields.py
git commit -m "feat: accept vocabularyPos/vocabularyTranslation on custom story frames"
```

---

### Task 2: Frontend types carry POS/translation through to the student-facing Topic

**Files:**
- Modify: `src/utils/teacherStories.ts:20-31` (`CustomStoryFrame` interface), `src/utils/teacherStories.ts:75-141` (`storyToTopic`)
- Modify: `src/services/database.ts:46-57` (duplicate `CustomStoryFrame` interface)
- Modify: `src/components/TopicSelector.tsx:13-33` (`Topic` interface)
- Test: `src/utils/teacherStories.test.ts` (create)

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `CustomStoryFrame.vocabularyPos?: string`, `CustomStoryFrame.vocabularyTranslation?: string`; `Topic.vocabularyPos?: Record<number, string[]>`, `Topic.vocabularyTranslation?: Record<number, string[]>`. Task 6 (student chip tooltip) reads these two `Topic` fields.

- [ ] **Step 1: Write the failing test**

Create `src/utils/teacherStories.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { storyToTopic, type CustomTeacherStory } from "./teacherStories";

describe("storyToTopic", () => {
  it("maps vocabularyPos and vocabularyTranslation onto the topic, keyed by frame index", () => {
    const story: CustomTeacherStory = {
      id: "story-1",
      title: "Restaurant Story",
      learningGoal: "Order food",
      level: "Beginner",
      frames: [
        {
          imageUrl: "",
          prompt: "Describe the picture.",
          vocabulary: "餐廳, 吃",
          vocabularyPinyin: "cāntīng, chī",
          vocabularyPos: "N, V",
          vocabularyTranslation: "restaurant, to eat",
        },
      ],
    };

    const topic = storyToTopic(story);

    expect(topic.vocabularyPos?.[0]).toEqual(["N", "V"]);
    expect(topic.vocabularyTranslation?.[0]).toEqual(["restaurant", "to eat"]);
  });

  it("omits vocabularyPos/vocabularyTranslation when the frame has none", () => {
    const story: CustomTeacherStory = {
      id: "story-2",
      title: "No POS Story",
      learningGoal: "Goal",
      level: "Beginner",
      frames: [
        { imageUrl: "", prompt: "Describe the picture.", vocabulary: "餐廳" },
      ],
    };

    const topic = storyToTopic(story);

    expect(topic.vocabularyPos).toBeUndefined();
    expect(topic.vocabularyTranslation).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/utils/teacherStories.test.ts`
Expected: FAIL — TypeScript error / `undefined` mismatch, since `vocabularyPos`/`vocabularyTranslation` don't exist on `CustomStoryFrame` or in `storyToTopic`'s output yet.

- [ ] **Step 3: Add the two fields to `CustomStoryFrame` in `teacherStories.ts`**

In `src/utils/teacherStories.ts`, update the interface (around line 20):

```typescript
export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: VocabGroup[];
  grammarPattern?: string;
  grammarExample?: string;
  vocabularyPinyin?: string;
  vocabularyPos?: string;
  vocabularyTranslation?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenScript?: string;
}
```

- [ ] **Step 4: Populate the new `Topic` fields in `storyToTopic()`**

In `src/utils/teacherStories.ts`, inside `storyToTopic` (around line 75), add two new accumulator records alongside the existing `vocabularyPinyin` one, and populate them inside the `story.frames.forEach` loop:

```typescript
  const vocabularyPinyin: Record<number, string[]> = {};
  const vocabularyPos: Record<number, string[]> = {};
  const vocabularyTranslation: Record<number, string[]> = {};
  const suggestedAnswers: Record<number, string> = {};
```

(add `vocabularyPos` and `vocabularyTranslation` next to the existing `vocabularyPinyin` declaration)

Inside the `story.frames.forEach((frame, index) => { ... })` loop, next to the existing `vocabularyPinyin` block:

```typescript
    if (frame.vocabularyPos && frame.vocabularyPos.trim()) {
      vocabularyPos[index] = frame.vocabularyPos
        .split(",")
        .map((p) => p.trim());
    }
    if (frame.vocabularyTranslation && frame.vocabularyTranslation.trim()) {
      vocabularyTranslation[index] = frame.vocabularyTranslation
        .split(",")
        .map((t) => t.trim());
    }
```

And in the returned object (where `vocabularyPinyin` is conditionally spread in), add:

```typescript
    ...(Object.keys(vocabularyPos).length > 0 ? { vocabularyPos } : {}),
    ...(Object.keys(vocabularyTranslation).length > 0 ? { vocabularyTranslation } : {}),
```

- [ ] **Step 5: Add the same two fields to the duplicate interface in `services/database.ts`**

In `src/services/database.ts`, update `CustomStoryFrame` (around line 46):

```typescript
export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: Array<{ name: string; words: string[] }>;
  grammarPattern?: string;
  grammarExample?: string;
  vocabularyPinyin?: string;
  vocabularyPos?: string;
  vocabularyTranslation?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenScript?: string;
}
```

- [ ] **Step 6: Add the two fields to `Topic` in `TopicSelector.tsx`**

In `src/components/TopicSelector.tsx`, update the `Topic` interface (around line 13):

```typescript
export interface Topic {
  id: string;
  name: string;
  description: string;
  skillFocus: string;
  level: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
  grammarPatterns?: Record<number, string>;
  grammarExamples?: Record<number, string>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenScripts?: Record<number, string>;
  linear?: boolean;
  lessonNumber?: number | null;
  narrativeMode?: "story" | "describe" | "listen_retell";
  firstFrameIsExample?: boolean;
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `npx vitest run src/utils/teacherStories.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 8: Type-check and run the full frontend test suite**

Run: `npx tsc --noEmit -p tsconfig.json`
Expected: same two pre-existing errors as before this change (`StoryRecorder.tsx` unused `VocabCategorizer`, `MyStoriesPage.tsx` frame-field union mismatch at the `vocabularyPinyin` line) — both predate this plan and are fixed/absorbed by Task 3. No *new* errors from this task.

Run: `npx vitest run`
Expected: no new failures beyond whatever was already failing before this task.

- [ ] **Step 9: Commit**

```bash
git add src/utils/teacherStories.ts src/utils/teacherStories.test.ts src/services/database.ts src/components/TopicSelector.tsx
git commit -m "feat: add vocabularyPos/vocabularyTranslation to story and topic types"
```

---

### Task 3: Teacher builder draft state carries the two new columns

**Files:**
- Modify: `src/pages/MyStoriesPage.tsx:222-247` (`emptyCustomStoryDraft`)
- Modify: `src/pages/MyStoriesPage.tsx:740-779` (`updateFrameCount`, `updateDraftFrame`)
- Modify: `src/pages/MyStoriesPage.tsx:1770-1823` (`createCustomStory`, `storyToDraft`)
- Modify: `src/pages/MyStoriesPage.tsx:1825-1852` (`clearFrameError` field union)

**Interfaces:**
- Consumes: `CustomStoryFrame.vocabularyPos`/`vocabularyTranslation` from Task 2.
- Produces: `customDraft.vocabularyPos: string[]`, `customDraft.vocabularyTranslation: string[]` (per-frame comma strings, same shape as `customDraft.vocabularyPinyin`) — Task 4's `VocabularyTable` reads/writes these via `updateDraftFrame`.

This task has no separate automated test of its own — it's plumbing consumed by Task 4 and Task 5's tests. Do it as plain edits, then verify with the type-checker at the end.

- [ ] **Step 1: Add the two new arrays to `emptyCustomStoryDraft`**

In `src/pages/MyStoriesPage.tsx`, update `emptyCustomStoryDraft` (around line 222):

```typescript
const emptyCustomStoryDraft = {
  title: "Taiwan Community Story",
  learningGoal: "Students describe who, where, what happened, and how people solved the problem.",
  level: "Beginner speaking",
  lessonNumber: "",
  imageUrls: ["", "", "", "", "", ""],
  prompts: [
    "Introduce the place and the people.",
    "Describe the first event.",
    "Explain the problem or surprise.",
    "Tell the result and feeling.",
    "Revise the story with one clearer detail.",
    "Finish with a lesson or next step.",
  ],
  vocabulary: ["", "", "", "", "", ""],
  vocabularyPinyin: ["", "", "", "", "", ""],
  vocabularyPos: ["", "", "", "", "", ""],
  vocabularyTranslation: ["", "", "", "", "", ""],
  vocabularyGroups: [null, null, null, null, null, null] as (VocabGroup[] | null)[],
  grammarPattern: "",
  grammarExample: "",
  suggestedAnswers: ["", "", "", "", "", ""],
  listenAudioUrls: ["", "", "", "", "", ""],
  listenScripts: ["", "", "", "", "", ""],
  linear: false,
  firstFrameIsExample: false,
  narrativeMode: "story" as NarrativeMode,
};
```

- [ ] **Step 2: Resize the new arrays when frame count changes**

In `updateFrameCount` (around line 740):

```typescript
  const updateFrameCount = (count: number) => {
    const clamped = Math.min(12, Math.max(1, count));
    setCustomDraft((draft) => ({
      ...draft,
      imageUrls: resizeToCount(draft.imageUrls, clamped, ""),
      prompts: resizeToCount(draft.prompts, clamped, ""),
      vocabulary: resizeToCount(draft.vocabulary, clamped, ""),
      vocabularyPinyin: resizeToCount(draft.vocabularyPinyin, clamped, ""),
      vocabularyPos: resizeToCount(draft.vocabularyPos, clamped, ""),
      vocabularyTranslation: resizeToCount(draft.vocabularyTranslation, clamped, ""),
      vocabularyGroups: resizeToCount(draft.vocabularyGroups, clamped, null),

      suggestedAnswers: resizeToCount(draft.suggestedAnswers, clamped, ""),
      listenAudioUrls: resizeToCount(draft.listenAudioUrls, clamped, ""),
      listenScripts: resizeToCount(draft.listenScripts, clamped, ""),
    }));
    setValidationErrors((errors) => ({ ...errors, frames: undefined, form: undefined }));
  };
```

- [ ] **Step 3: Widen `updateDraftFrame`'s field union to include the two new fields**

Around line 764:

```typescript
  const updateDraftFrame = (
    field:
      | "imageUrls"
      | "prompts"
      | "vocabulary"
      | "vocabularyPinyin"
      | "vocabularyPos"
      | "vocabularyTranslation"
      | "suggestedAnswers"
      | "listenAudioUrls"
      | "listenScripts",
    index: number,
    value: string,
  ) => {
    setCustomDraft((draft) => ({
      ...draft,
      [field]: draft[field].map((item, itemIndex) =>
        itemIndex === index ? value : item,
      ),
    }));
    setValidationErrors((errors) =>
      clearFrameError(errors, index, field),
    );
    clearNotice();
  };
```

- [ ] **Step 4: Widen `clearFrameError`'s field parameter type to match**

Around line 1825 — `clearFrameError` only branches on `imageUrls`/`prompts`, but its type must accept whatever `updateDraftFrame` passes through:

```typescript
function clearFrameError(
  errors: CustomStoryValidationErrors,
  index: number,
  field:
    | "imageUrls"
    | "prompts"
    | "vocabulary"
    | "vocabularyPinyin"
    | "vocabularyPos"
    | "vocabularyTranslation"
    | "suggestedAnswers"
    | "listenAudioUrls"
    | "listenScripts",
): CustomStoryValidationErrors {
  const frameError = errors.frames?.[index];

  if (!frameError) {
    return { ...errors, form: undefined };
  }

  const nextFrames = { ...errors.frames };
  nextFrames[index] = {
    ...frameError,
    imageUrl: field === "imageUrls" ? undefined : frameError.imageUrl,
    prompt: field === "prompts" ? undefined : frameError.prompt,
  };

  if (!nextFrames[index].imageUrl && !nextFrames[index].prompt) {
    delete nextFrames[index];
  }

  return {
    ...errors,
    form: undefined,
    frames: Object.keys(nextFrames).length > 0 ? nextFrames : undefined,
  };
}
```

- [ ] **Step 5: Serialize the two new columns when building a `CustomTeacherStory` from the draft**

In `createCustomStory` (around line 1770), add the two new conditional spreads next to the existing `vocabularyPinyin` one:

```typescript
  return {
    id: existingId || `custom-story-${Date.now()}`,
    title: draft.title.trim() || "Untitled teacher story",
    learningGoal: draft.learningGoal.trim(),
    level: draft.level.trim() || "Custom activity",
    frames: draft.imageUrls.map((imageUrl, index) => ({
      imageUrl: imageUrl.trim(),
      prompt: draft.prompts[index].trim(),
      vocabulary: draft.vocabulary[index].trim(),
      ...(draft.vocabularyGroups[index] ? { vocabularyGroups: draft.vocabularyGroups[index]! } : {}),
      ...(draft.grammarPattern?.trim() ? { grammarPattern: draft.grammarPattern.trim() } : {}),
      ...(draft.grammarExample?.trim() ? { grammarExample: draft.grammarExample.trim() } : {}),
      ...(draft.vocabularyPinyin[index]?.trim() ? { vocabularyPinyin: draft.vocabularyPinyin[index].trim() } : {}),
      ...(draft.vocabularyPos[index]?.trim() ? { vocabularyPos: draft.vocabularyPos[index].trim() } : {}),
      ...(draft.vocabularyTranslation[index]?.trim() ? { vocabularyTranslation: draft.vocabularyTranslation[index].trim() } : {}),
      ...(draft.suggestedAnswers[index]?.trim() ? { suggestedAnswer: draft.suggestedAnswers[index].trim() } : {}),
      ...(draft.listenAudioUrls[index]?.trim() ? { listenAudioUrl: draft.listenAudioUrls[index].trim() } : {}),
      ...(draft.listenScripts[index]?.trim() ? { listenScript: draft.listenScripts[index].trim() } : {}),
    })),
    ...(draft.linear ? { linear: true } : {}),
    ...(draft.firstFrameIsExample ? { firstFrameIsExample: true } : {}),
    ...(draft.lessonNumber.trim() ? { lessonNumber: Number(draft.lessonNumber) } : {}),
    narrativeMode: draft.narrativeMode,
  };
}
```

- [ ] **Step 6: Parse the two new columns back into the draft when editing a saved story**

In `storyToDraft` (around line 1794), add the two new lines next to the existing `vocabularyPinyin` mapping:

```typescript
  return {
    title: story.title,
    learningGoal: story.learningGoal,
    level: story.level,
    lessonNumber: story.lessonNumber != null ? String(story.lessonNumber) : "",
    imageUrls: frames.map((frame) => frame?.imageUrl || ""),
    prompts: frames.map((frame, index) =>
      frame?.prompt || emptyCustomStoryDraft.prompts[index],
    ),
    vocabulary: frames.map((frame) => frame?.vocabulary || ""),
    vocabularyGroups: frames.map((frame) => frame?.vocabularyGroups || null),
    grammarPattern: story.frames.find((f) => f?.grammarPattern)?.grammarPattern || "",
    grammarExample: story.frames.find((f) => f?.grammarExample)?.grammarExample || "",
    vocabularyPinyin: frames.map((frame) => frame?.vocabularyPinyin || ""),
    vocabularyPos: frames.map((frame) => frame?.vocabularyPos || ""),
    vocabularyTranslation: frames.map((frame) => frame?.vocabularyTranslation || ""),
    suggestedAnswers: frames.map((frame) => frame?.suggestedAnswer || ""),
    listenAudioUrls: frames.map((frame) => frame?.listenAudioUrl || ""),
    listenScripts: frames.map((frame) => frame?.listenScript || ""),
    linear: story.linear ?? false,
    firstFrameIsExample: story.firstFrameIsExample ?? false,
    narrativeMode: story.narrativeMode ?? "story",
  };
}
```

- [ ] **Step 7: Type-check**

Run: `npx tsc --noEmit -p tsconfig.json`
Expected: the pre-existing `MyStoriesPage.tsx` frame-field union error (previously at the `updateDraftFrame("vocabularyPinyin", ...)` call site) is now GONE, since the union includes all the fields that call it. Only the one remaining pre-existing, unrelated error stays (`StoryRecorder.tsx` unused `VocabCategorizer`).

- [ ] **Step 8: Commit**

```bash
git add src/pages/MyStoriesPage.tsx
git commit -m "feat: thread vocabularyPos/vocabularyTranslation through the story builder draft state"
```

---

### Task 4: VocabularyTable component replaces the two text inputs; Grammar Canvas hidden behind a flag

**Files:**
- Modify: `src/pages/MyStoriesPage.tsx` (add `VocabularyTable` component near `VocabGroupEditor`, around line 1854; replace the two `<label>` inputs around line 1310-1329; add `GRAMMAR_CANVAS_ENABLED` flag and gate the render around line 1378)
- Modify: `src/pages/MyStoriesPage.css` (new table styles)

**Interfaces:**
- Consumes: `customDraft.vocabulary[index]`, `vocabularyPinyin[index]`, `vocabularyPos[index]`, `vocabularyTranslation[index]` (strings) and `updateDraftFrame` (Task 3) as the change callback.
- Produces: `VocabularyTable` component, used only in `MyStoriesPage.tsx` — no other file depends on it.

- [ ] **Step 1: Add the `VOCAB_POS_OPTIONS` constant and `VocabularyTable` component**

In `src/pages/MyStoriesPage.tsx`, add this near the existing `VocabGroupEditor` function (just above it, around line 1854):

```typescript
const VOCAB_POS_OPTIONS = ["N", "V", "Adj", "Adv", "MW", "Particle", "Phrase", "Other"];

interface VocabRow {
  word: string;
  pinyin: string;
  pos: string;
  translation: string;
}

function splitVocabColumn(value: string): string[] {
  if (!value.trim()) return [];
  return value.split(",").map((v) => v.trim());
}

function buildVocabRows(
  vocabulary: string,
  vocabularyPinyin: string,
  vocabularyPos: string,
  vocabularyTranslation: string,
): VocabRow[] {
  const words = splitVocabColumn(vocabulary);
  const pinyins = splitVocabColumn(vocabularyPinyin);
  const pos = splitVocabColumn(vocabularyPos);
  const translations = splitVocabColumn(vocabularyTranslation);
  return words.map((word, i) => ({
    word,
    pinyin: pinyins[i] || "",
    pos: pos[i] || "",
    translation: translations[i] || "",
  }));
}

function VocabularyTable({
  vocabulary,
  vocabularyPinyin,
  vocabularyPos,
  vocabularyTranslation,
  onChangeColumn,
}: {
  vocabulary: string;
  vocabularyPinyin: string;
  vocabularyPos: string;
  vocabularyTranslation: string;
  onChangeColumn: (
    field: "vocabulary" | "vocabularyPinyin" | "vocabularyPos" | "vocabularyTranslation",
    value: string,
  ) => void;
}) {
  const rows = buildVocabRows(vocabulary, vocabularyPinyin, vocabularyPos, vocabularyTranslation);

  const commitRows = (nextRows: VocabRow[]) => {
    onChangeColumn("vocabulary", nextRows.map((r) => r.word).join(", "));
    onChangeColumn("vocabularyPinyin", nextRows.map((r) => r.pinyin).join(", "));
    onChangeColumn("vocabularyPos", nextRows.map((r) => r.pos).join(", "));
    onChangeColumn("vocabularyTranslation", nextRows.map((r) => r.translation).join(", "));
  };

  const updateCell = (rowIndex: number, field: keyof VocabRow, value: string) => {
    commitRows(rows.map((row, i) => (i === rowIndex ? { ...row, [field]: value } : row)));
  };

  const addRow = () => {
    commitRows([...rows, { word: "", pinyin: "", pos: "", translation: "" }]);
  };

  const removeRow = (rowIndex: number) => {
    commitRows(rows.filter((_, i) => i !== rowIndex));
  };

  return (
    <div className="vocab-table" role="table" aria-label="Vocabulary">
      <div className="vocab-table-header" role="row">
        <span role="columnheader">Chinese word</span>
        <span role="columnheader">Pinyin</span>
        <span role="columnheader">Part of speech</span>
        <span role="columnheader">English translation</span>
        <span role="columnheader" aria-hidden="true" />
      </div>
      {rows.map((row, index) => (
        <div className="vocab-table-row" role="row" key={index}>
          <input
            aria-label="Chinese word"
            value={row.word}
            onChange={(event) => updateCell(index, "word", event.target.value)}
            placeholder="餐廳"
          />
          <input
            aria-label="Pinyin"
            value={row.pinyin}
            onChange={(event) => updateCell(index, "pinyin", event.target.value)}
            placeholder="cāntīng"
          />
          <select
            aria-label="Part of speech"
            value={row.pos}
            onChange={(event) => updateCell(index, "pos", event.target.value)}
          >
            <option value="">--</option>
            {VOCAB_POS_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <input
            aria-label="English translation"
            value={row.translation}
            onChange={(event) => updateCell(index, "translation", event.target.value)}
            placeholder="restaurant"
          />
          <button
            type="button"
            className="vocab-table-remove"
            aria-label={`Remove word ${index + 1}`}
            onClick={() => removeRow(index)}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="vocab-table-add-btn" onClick={addRow}>
        + Add word
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Replace the two "Vocabulary" / "Vocabulary Pinyin" inputs with `VocabularyTable`**

In `src/pages/MyStoriesPage.tsx`, replace this block (around line 1310-1329):

```typescript
                    <label>
                      Vocabulary
                      <input
                        value={customDraft.vocabulary[index] ?? ""}
                        onChange={(event) =>
                          updateDraftFrame("vocabulary", index, event.target.value)
                        }
                        placeholder="台北, 下雨, 幫忙"
                      />
                    </label>
                    <label>
                      Vocabulary Pinyin (optional)
                      <input
                        value={customDraft.vocabularyPinyin[index] ?? ""}
                        onChange={(event) =>
                          updateDraftFrame("vocabularyPinyin", index, event.target.value)
                        }
                        placeholder="tái běi, xià yǔ, bāng máng"
                      />
                    </label>
```

with:

```typescript
                    <VocabularyTable
                      vocabulary={customDraft.vocabulary[index] ?? ""}
                      vocabularyPinyin={customDraft.vocabularyPinyin[index] ?? ""}
                      vocabularyPos={customDraft.vocabularyPos[index] ?? ""}
                      vocabularyTranslation={customDraft.vocabularyTranslation[index] ?? ""}
                      onChangeColumn={(field, value) => updateDraftFrame(field, index, value)}
                    />
```

- [ ] **Step 3: Hide the Grammar Pattern Canvas behind a flag**

Add this constant near the top of the file, alongside the other module-level constants (e.g. right above `const emptyCustomStoryDraft = {` around line 222):

```typescript
// Temporarily disabled 2026-07-07 at the user's request. The component,
// its data (vocabularyGroups), and this flag stay in place so it's a
// one-line flip to bring back.
const GRAMMAR_CANVAS_ENABLED = false;
```

Then wrap the existing render call (around line 1378):

```typescript
                    {GRAMMAR_CANVAS_ENABLED && (
                      <VocabGroupEditor
                        vocabulary={customDraft.vocabulary[index]}
                        groups={customDraft.vocabularyGroups[index]}
                        onChange={(groups) => updateDraftGroups(index, groups)}
                      />
                    )}
```

- [ ] **Step 4: Add table styles to `MyStoriesPage.css`**

Append to `src/pages/MyStoriesPage.css`:

```css
.vocab-table {
  display: grid;
  gap: 6px;
}

.vocab-table-header,
.vocab-table-row {
  display: grid;
  grid-template-columns: 1.1fr 1.1fr 0.9fr 1.3fr auto;
  gap: 8px;
  align-items: center;
}

.vocab-table-header span {
  font-size: 11px;
  font-weight: 800;
  color: var(--clay-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.vocab-table-row input,
.vocab-table-row select {
  padding: 8px 9px;
  font-size: 13px;
}

.vocab-table-remove {
  border: 1px solid var(--clay-hairline);
  border-radius: var(--clay-radius-sm);
  background: var(--clay-surface-card);
  color: var(--clay-error);
  cursor: pointer;
  font-size: 14px;
  font-weight: 900;
  width: 30px;
  height: 30px;
}

.vocab-table-add-btn {
  justify-self: start;
  margin-top: 2px;
  border: 1px dashed var(--jade);
  border-radius: var(--clay-radius-md);
  background: var(--clay-surface-card);
  color: var(--jade-deep);
  cursor: pointer;
  font-size: 12px;
  font-weight: 900;
  padding: 7px 12px;
}

.vocab-table-add-btn:hover {
  background: var(--jade-soft);
}
```

- [ ] **Step 5: Type-check**

Run: `npx tsc --noEmit -p tsconfig.json`
Expected: no new errors.

- [ ] **Step 6: Manually verify in the running app**

Run: `npm run dev` (frontend) and `cd backend && uvicorn main:app --reload --port 8000` (backend), open the Teacher Dashboard → Materials tab. Confirm:
- The "Vocabulary" and "Vocabulary Pinyin (optional)" labels are gone, replaced by a table with 4 columns + a `+ Add word` button.
- Adding a row, filling in all 4 cells, and removing a row all work without console errors.
- The "+ Add Grammar categories" button no longer appears anywhere in the frame editor.

- [ ] **Step 7: Commit**

```bash
git add src/pages/MyStoriesPage.tsx src/pages/MyStoriesPage.css
git commit -m "feat: replace vocabulary/pinyin inputs with a table; hide Grammar Canvas behind a flag"
```

---

### Task 5: Update and extend the MyStoriesPage test suite for the new table

**Files:**
- Modify: `src/pages/MyStoriesPage.test.tsx:114` (existing test using the old single "Vocabulary" input)
- Modify: `src/pages/MyStoriesPage.test.tsx` (add a new test for the table's 4 columns)

**Interfaces:**
- Consumes: `VocabularyTable`'s rendered ARIA labels from Task 4 (`"Chinese word"`, `"Pinyin"`, `"Part of speech"`, `"English translation"`, `"+ Add word"` button).

- [ ] **Step 1: Update the existing test that types into the old "Vocabulary" input**

In `src/pages/MyStoriesPage.test.tsx`, replace this line (currently line 114):

```typescript
    await user.type(screen.getAllByLabelText("Vocabulary")[0], "下雨, 幫忙");
```

with:

```typescript
    await user.click(screen.getAllByRole("button", { name: "+ Add word" })[0]);
    await user.type(screen.getAllByLabelText("Chinese word")[0], "下雨");
```

- [ ] **Step 2: Run the existing test to confirm it still passes with the new table**

Run: `npx vitest run src/pages/MyStoriesPage.test.tsx -t "lets teachers save a custom image-based story activity"`
Expected: PASS

- [ ] **Step 3: Write a new failing test for the full 4-column round trip**

Add this test to `src/pages/MyStoriesPage.test.tsx`, after the existing "lets teachers save a custom image-based story activity" test:

```typescript
  it("saves all four vocabulary table columns for a word", async () => {
    const user = userEvent.setup();
    render(
      <MyStoriesPage mode="teacher" records={[]} onDeleteRecord={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Restaurant Story");

    await user.click(screen.getAllByRole("button", { name: "+ Add word" })[0]);
    await user.type(screen.getAllByLabelText("Chinese word")[0], "餐廳");
    await user.type(screen.getAllByLabelText("Pinyin")[0], "cāntīng");
    await user.selectOptions(screen.getAllByLabelText("Part of speech")[0], "N");
    await user.type(screen.getAllByLabelText("English translation")[0], "restaurant");

    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    const stored = localStorage.getItem("teacherCustomStories") || "";
    expect(stored).toContain('"vocabulary":"餐廳"');
    expect(stored).toContain('"vocabularyPinyin":"cāntīng"');
    expect(stored).toContain('"vocabularyPos":"N"');
    expect(stored).toContain('"vocabularyTranslation":"restaurant"');
  }, 10000);
```

- [ ] **Step 4: Run it to verify it fails first**

Run: `npx vitest run src/pages/MyStoriesPage.test.tsx -t "saves all four vocabulary table columns"`
Expected: FAIL if Task 4 wasn't done yet in this session; if Task 4 is already complete (as it should be by this point in the plan), this instead confirms the table wires end-to-end — if it unexpectedly fails, re-check Task 4's `onChangeColumn` wiring before proceeding.

- [ ] **Step 5: Run the full MyStoriesPage test file**

Run: `npx vitest run src/pages/MyStoriesPage.test.tsx`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Commit**

```bash
git add src/pages/MyStoriesPage.test.tsx
git commit -m "test: cover the vocabulary table's 4-column save round trip"
```

---

### Task 6: Student-facing vocab chip tooltip (part of speech + translation)

**Files:**
- Modify: `src/components/StoryRecorder.tsx:1065-1096` (`overview-vocab-chips`), `src/components/StoryRecorder.tsx:1591-1630` (`practice-vocab-chips`), `src/components/StoryRecorder.tsx:1934-1962` (`ap-vocab-chips`)
- Test: add to `src/components/StoryRecorder.test.tsx`

**Interfaces:**
- Consumes: `Topic.vocabularyPos`/`vocabularyTranslation` from Task 2.
- Produces: `export function vocabTooltip(pos?: string, translation?: string): string | undefined` — a pure helper, exported for direct unit testing.

- [ ] **Step 1: Write the failing test for the pure helper**

Add to `src/components/StoryRecorder.test.tsx` (new `describe` block, can go near the top-level `describe("StoryRecorder student prototype", ...)`):

```typescript
import { vocabTooltip } from "./StoryRecorder";

describe("vocabTooltip", () => {
  it("combines part of speech and translation", () => {
    expect(vocabTooltip("N", "restaurant")).toBe("(N) restaurant");
  });

  it("returns just the POS in parens when translation is missing", () => {
    expect(vocabTooltip("N", undefined)).toBe("(N)");
  });

  it("returns just the translation when POS is missing", () => {
    expect(vocabTooltip(undefined, "restaurant")).toBe("restaurant");
  });

  it("returns undefined when both are missing", () => {
    expect(vocabTooltip(undefined, undefined)).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/StoryRecorder.test.tsx -t "vocabTooltip"`
Expected: FAIL — `vocabTooltip` is not exported from `StoryRecorder.tsx` yet.

- [ ] **Step 3: Add the `vocabTooltip` helper to `StoryRecorder.tsx`**

Add this near the top of `src/components/StoryRecorder.tsx`, alongside other small helper functions in the file (not inside the component body):

```typescript
export function vocabTooltip(pos?: string, translation?: string): string | undefined {
  if (pos && translation) return `(${pos}) ${translation}`;
  if (pos) return `(${pos})`;
  if (translation) return translation;
  return undefined;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/StoryRecorder.test.tsx -t "vocabTooltip"`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire the tooltip into `overview-vocab-chips`**

In `src/components/StoryRecorder.tsx`, around line 1076-1090, change:

```typescript
                    <div className="overview-vocab-chips">
                      {sceneWords.map((word, i) => {
                        const py = topic.vocabularyPinyin?.[si]?.[i] || toPinyin(word);
                        return (
                          <span
                            key={`${word}-${i}`}
                            className="overview-vocab-chip"
                          >
                            <span className="vocab-chip-hanzi">{word}</span>
                            {py && (
                              <span className="vocab-chip-pinyin">{py}</span>
                            )}
                          </span>
                        );
                      })}
                    </div>
```

to:

```typescript
                    <div className="overview-vocab-chips">
                      {sceneWords.map((word, i) => {
                        const py = topic.vocabularyPinyin?.[si]?.[i] || toPinyin(word);
                        const tooltip = vocabTooltip(
                          topic.vocabularyPos?.[si]?.[i],
                          topic.vocabularyTranslation?.[si]?.[i],
                        );
                        return (
                          <span
                            key={`${word}-${i}`}
                            className="overview-vocab-chip"
                          >
                            <span className="vocab-chip-hanzi" title={tooltip}>{word}</span>
                            {py && (
                              <span className="vocab-chip-pinyin">{py}</span>
                            )}
                          </span>
                        );
                      })}
                    </div>
```

- [ ] **Step 6: Wire the tooltip into `practice-vocab-chips`**

Around line 1615-1616, change:

```typescript
                          <span className="vocab-chip-row">
                            <span className="vocab-chip-hanzi">{w}</span>
```

to:

```typescript
                          <span className="vocab-chip-row">
                            <span
                              className="vocab-chip-hanzi"
                              title={vocabTooltip(
                                topic.vocabularyPos?.[selectedImageIndex]?.[wi],
                                topic.vocabularyTranslation?.[selectedImageIndex]?.[wi],
                              )}
                            >
                              {w}
                            </span>
```

- [ ] **Step 7: Wire the tooltip into `ap-vocab-chips`**

Around line 1951-1952, change:

```typescript
                          <span className="vocab-chip-row">
                            <span className="vocab-chip-hanzi">{w}</span>
```

(the second occurrence, inside the `ap-vocab-chips` block) to:

```typescript
                          <span className="vocab-chip-row">
                            <span
                              className="vocab-chip-hanzi"
                              title={vocabTooltip(
                                topic.vocabularyPos?.[selectedImageIndex]?.[wi],
                                topic.vocabularyTranslation?.[selectedImageIndex]?.[wi],
                              )}
                            >
                              {w}
                            </span>
```

- [ ] **Step 8: Run the full StoryRecorder test suite**

Run: `npx vitest run src/components/StoryRecorder.test.tsx`
Expected: PASS (no regressions in the existing recording-flow tests).

- [ ] **Step 9: Type-check and build**

Run: `npx tsc --noEmit -p tsconfig.json`
Expected: same as Task 3 Step 7 — zero new errors (the one pre-existing `VocabCategorizer` unused-variable error is unrelated to this plan and may still be present).

Run: `npx vite build`
Expected: builds successfully.

- [ ] **Step 10: Commit**

```bash
git add src/components/StoryRecorder.tsx src/components/StoryRecorder.test.tsx
git commit -m "feat: show part-of-speech/translation as a tooltip on student vocab chips"
```

---

## Final verification (after all tasks)

- [ ] Run `cd backend && python -m pytest tests/ -q` — same pass/fail counts as the project's baseline (one pre-existing flaky failure expected).
- [ ] Run `npx vitest run` — no failures beyond the project's pre-existing baseline.
- [ ] Run `npx tsc --noEmit -p tsconfig.json` — no new errors versus the pre-existing 2 (or 1, after Task 3 fixes one of them).
- [ ] Run `npx vite build` — succeeds.
- [ ] Manually open Teacher Dashboard → Materials, build a word in the new table with all 4 columns filled in, save, publish, then open the story as a student and hover the word's chip to confirm the tooltip shows `(POS) translation`.
