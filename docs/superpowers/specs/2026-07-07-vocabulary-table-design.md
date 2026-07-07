# Vocabulary table with pinyin, part-of-speech, and translation

Date: 2026-07-07

## Problem

Teachers currently enter story vocabulary as two separate free-text inputs per
frame in the Materials builder (`src/pages/MyStoriesPage.tsx`):

- **Vocabulary** — comma-separated Chinese words (e.g. `台北, 下雨, 幫忙`)
- **Vocabulary Pinyin (optional)** — a parallel comma-separated pinyin list
  (e.g. `tái běi, xià yǔ, bāng máng`), matched to the word list by position

There's no way to record part of speech or an English translation per word.
The teacher wants a single table-style input instead: one row per word, with
columns for the Chinese word, pinyin, part of speech, and English
translation — e.g. a row reading `餐廳, cāntīng, (N), restaurant`.

## Current data flow (context)

- `CustomStoryFrame` (`src/utils/teacherStories.ts`) stores `vocabulary: string`
  and `vocabularyPinyin?: string` as comma-separated strings.
- `storyToTopic()` splits both into parallel arrays and builds a `Topic` with
  `vocabulary: Record<number, string[]>` and
  `vocabularyPinyin?: Record<number, string[]>` (keyed by frame index).
- Student-facing vocab chips (`src/components/StoryRecorder.tsx`, 3 render
  sites: `overview-vocab-chips`, `practice-vocab-chips`, `ap-vocab-chips`) show
  the Chinese word (large) and pinyin (small), matched by array position,
  falling back to an auto-computed pinyin (`toPinyin(w)`) if the teacher didn't
  supply one.
- The backend never sees pinyin at all. `custom_stories.frames` is stored as
  one JSON text column (`backend/database.py`), so there is no SQL schema to
  migrate. The backend's `CustomStoryFrameRequest` Pydantic model
  (`backend/main.py`) declares each frame field explicitly — any field not
  declared there is silently dropped on save.
- Vocabulary-matching/scoring (`scene_vocabulary` passed to the AI feedback
  prompt) only ever uses the plain Chinese word string. Pinyin, part of
  speech, and translation are purely display metadata and never reach that
  code path.
- A separate feature, the **Grammar Pattern Canvas** (`VocabGroupEditor` in
  `MyStoriesPage.tsx`), lets a teacher assign each vocabulary word to a
  Subject/Verb/Object group, stored in `vocabularyGroups`. It reads the same
  comma-separated `vocabulary` string.

## Design

### Data model (additive, no migration)

Add two new optional parallel comma-separated fields to `CustomStoryFrame`,
matching the existing `vocabularyPinyin` convention exactly:

- `vocabularyPos?: string` — e.g. `"N, V, N"`
- `vocabularyTranslation?: string` — e.g. `"restaurant, to eat, tea"`

Both are index-aligned with `vocabulary` the same way `vocabularyPinyin`
already is. Existing stories that only have `vocabulary`/`vocabularyPinyin`
continue to work unchanged — the new columns are simply empty until a teacher
fills them in.

Backend: add `vocabularyPos: Optional[str] = None` and
`vocabularyTranslation: Optional[str] = None` to `CustomStoryFrameRequest` in
`backend/main.py` so they round-trip through save/load. No database schema
change (the frames column is a JSON blob). No change to vocabulary-matching
logic — POS/translation are never sent to the AI feedback prompt.

### Teacher UI: vocabulary table

Replace the two separate "Vocabulary" / "Vocabulary Pinyin" inputs in the
frame editor (`MyStoriesPage.tsx`) with a single table:

| Chinese word | Pinyin | Part of speech | English translation | |
|---|---|---|---|---|
| 餐廳 | cāntīng | [N ▾] | restaurant | × |
| 吃 | chī | [V ▾] | to eat | × |

- One row per word, with a `+ Add word` control to append a row and a `×`
  per row to remove it.
- Part of speech is a fixed dropdown: **N, V, Adj, Adv, MW, Particle, Phrase,
  Other**. Stored as the short code itself (e.g. `"N"`).
- Internally, the table is built by zipping the four parallel draft strings
  (`vocabulary`, `vocabularyPinyin`, `vocabularyPos`, `vocabularyTranslation`)
  together by index for editing, and re-serializes back to those same four
  comma-joined strings on every change — so the on-disk/API shape doesn't
  change, only how the teacher edits it.
- The **Grammar Pattern Canvas** (`VocabGroupEditor`) is temporarily removed
  from the rendered frame editor — its toggle button and editor no longer
  appear. The component itself, its CSS, and any already-stored
  `vocabularyGroups` data are left untouched so it can be re-enabled later by
  restoring the single render call in `MyStoriesPage.tsx`.

### Student-facing display

Vocab chips keep their current two-line look (Chinese word + pinyin) in all
three render sites in `StoryRecorder.tsx`. Part of speech and translation
appear as a native browser tooltip (`title` attribute) on the Chinese-word
span specifically — e.g. hovering 餐廳 shows `(N) restaurant` — added to the
inner `vocab-chip-hanzi` span rather than the outer chip, since the outer chip
already carries its own `title` for used/missing feedback. If a word has no
POS or translation filled in, no tooltip is added (no empty `title=""`).

`Topic` (`src/components/TopicSelector.tsx`) gains
`vocabularyPos?: Record<number, string[]>` and
`vocabularyTranslation?: Record<number, string[]>`, populated in
`storyToTopic()` the same way `vocabularyPinyin` already is.

**Known limitation, accepted as scope**: native `title` tooltips don't have a
consistent long-press equivalent across all mobile browsers — some show it on
long-press, some don't. No custom touch-popover component is being built for
this; if that turns out to matter in practice, it's a follow-up.

### Testing

- Existing `MyStoriesPage.test.tsx` and `StoryRecorder.test.tsx` suites must
  keep passing (adjusted for the removed Grammar Canvas UI and the new table
  markup where they touch it).
- New coverage: saving a story via the table produces the same
  comma-serialized `vocabulary`/`vocabularyPinyin`/`vocabularyPos`/
  `vocabularyTranslation` strings as the old two-input flow would have for
  word+pinyin; loading an old story (no POS/translation) populates the table
  with empty cells for those columns; the chip tooltip only appears when both
  POS and translation are present for that word.
- Backend: confirm `CustomStoryFrameRequest` round-trips the two new optional
  fields through `POST /api/custom-stories` without them being dropped.

## Out of scope

- Re-enabling the Grammar Pattern Canvas (left in place, just unrendered).
- Any change to vocabulary-matching/scoring logic.
- A custom touch/long-press tooltip component.
