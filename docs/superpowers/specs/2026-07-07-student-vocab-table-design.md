# Student-facing vocabulary table (overview / study list)

Date: 2026-07-07

## Problem

Since the recent teacher-side vocabulary work, each word can carry a Chinese
word, pinyin, part of speech, and English translation. Students currently see
only the word and pinyin as a "chip"; part of speech and translation are
hidden behind a hover `title` tooltip on the Chinese word — easy to miss, and
tooltips don't work well on touch devices. The teacher asked for a table
layout for students too, but distinct from the teacher's editable builder
table (no inputs, dropdowns, or add/remove controls — read-only display).

## Scope

Only the **"Key Vocabulary" overview block** — the `overview-vocab-chips`
render site in `src/components/StoryRecorder.tsx` (~line 1074-1105), shown to
a student before they start recording a scene, with no interactive
used/missing state.

**Explicitly out of scope**: the two *live* vocab-chip render sites shown
during active recording practice (`practice-vocab-chips`,
`ap-vocab-chips`), which turn green/red as the student's speech is checked
against the word list. Converting those to a table would need a design for
how a table row shows "used"/"missing" state, which isn't part of this
request — they keep their current chip appearance unchanged.

## Data (no changes needed)

`Topic.vocabulary`, `vocabularyPinyin`, `vocabularyPos`, `vocabularyTranslation`
(all `Record<number, string[]>`, keyed by scene index) already carry
everything this table needs — added in the prior vocabulary-table plan. No
backend or type changes are required for this feature.

## Design

Replace the current per-scene flex-wrapped chip row with a per-scene
read-only table: one row per word, four columns — Chinese word, Pinyin, Part
of speech, Meaning. All four are always visible (no hover/tooltip needed,
unlike the chip it replaces). The existing per-scene grouping and "Scene N"
label (`overview-vocab-scene`, `overview-vocab-scene-label`) stay exactly as
they are today — only the row-of-chips inside each scene group becomes a
table.

Visual styling is deliberately distinct from the teacher builder's table
(`VocabularyTable` in `src/pages/MyStoriesPage.tsx`, which uses jade/violet
accents and interactive controls): this student-facing table reuses the
existing gold/amber palette the overview vocab block already uses
(`--gold`, `--gold-soft`, `--gold-deep`, currently applied to
`.overview-vocab-chip`), just laid out as table rows/cells instead of
wrapped chips. No inputs, no dropdown, no buttons — plain text cells.

**Missing data**: if a word has no part of speech or no translation filled
in (common for existing stories, or words a teacher hasn't annotated yet),
that cell renders empty — no placeholder text, no layout break. Pinyin keeps
its current fallback behavior (falls back to an auto-computed pinyin via
`toPinyin(word)` when the teacher didn't supply one — unchanged from today).

## Testing

- Existing `StoryRecorder.test.tsx` coverage of the overview render must
  keep passing (adjusted for the new table markup where it touches this
  block).
- New coverage: a scene with a word that has both POS and translation shows
  both in their own cells; a word missing one or both shows empty cells
  without breaking the row; the live practice chip views
  (`practice-vocab-chips`, `ap-vocab-chips`) are unaffected by this change.

## Out of scope

- The two live/interactive vocab chip views during recording practice.
- Any change to the teacher builder's `VocabularyTable`.
- Any backend or type change (all data already flows through `Topic` from
  the prior plan).
