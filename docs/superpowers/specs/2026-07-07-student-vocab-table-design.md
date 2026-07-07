# Student-facing vocabulary table

Date: 2026-07-07 (revised same day: scope expanded to all 3 student vocab displays)

## Problem

Since the recent teacher-side vocabulary work, each word can carry a Chinese
word, pinyin, part of speech, and English translation. Students currently see
only the word and pinyin as a "chip"; part of speech and translation are
hidden behind a hover `title` tooltip on the Chinese word — easy to miss, and
tooltips don't work well on touch devices. The teacher asked for a table
layout for students too, but distinct from the teacher's editable builder
table (no inputs, dropdowns, or add/remove controls — read-only display).

## Scope

All three student-facing vocab chip render sites in
`src/components/StoryRecorder.tsx` become read-only tables:

1. **`overview-vocab-chips`** (~line 1074-1105) — the "Key Vocabulary" list
   shown before a student starts recording a scene. No interactive state.
2. **`practice-vocab-chips`** (~line 1593-1650) — shown during active
   recording practice, heading "Scene vocabulary." Once `praatMetrics` exists
   (recording analyzed), each word is marked used (✓) or missing (✗) against
   the student's speech.
3. **`ap-vocab-chips`** (~line 1955-1990) — shown in the post-recording
   results/analysis panel, same "Scene vocabulary" heading and used/missing
   marking, sourced only from the AI vocabulary-coverage result (no raw-
   transcription fallback, unlike #2 — that existing behavioral difference
   between the two is preserved, not something this change touches).

All three get the same 4-column table treatment (Chinese word, Pinyin, Part
of speech, Meaning); #2 and #3 additionally get a status column (see below).

## Data (no changes needed)

`Topic.vocabulary`, `vocabularyPinyin`, `vocabularyPos`, `vocabularyTranslation`
(all `Record<number, string[]>`, keyed by scene index) already carry
everything these tables need — added in the prior vocabulary-table plan. No
backend or type changes are required for this feature. The `used`/`missing`
determination logic in `practice-vocab-chips`/`ap-vocab-chips` (comparing
against `praatMetrics.ai_feedback.vocabulary_coverage`, with a raw-
transcription-substring fallback only in `practice-vocab-chips`) is unchanged
— only how the result is *displayed* changes, from a chip to a table row.

## Design

Replace each chip row (`overview-vocab-chips`, `practice-vocab-chips`,
`ap-vocab-chips`) with a per-scene read-only table: one row per word,
columns Chinese word · Pinyin · Part of speech · Meaning, all always visible
(no hover/tooltip needed, unlike the chip it replaces). Existing surrounding
structure (per-scene grouping and "Scene N" label in the overview; the
"Scene vocabulary" heading and the `check_which_words_you_used` hint text in
the other two) stays exactly as today — only the chip row itself becomes a
table.

**Status column** (`practice-vocab-chips` and `ap-vocab-chips` only): a
narrow leading or trailing column showing ✓ (used) or ✗ (missing) in the same
green/red language the chips use today, plus a subtle background tint on the
whole row — green-tinted using the existing `--jade`/`--jade-soft` tokens for
a used word, red-tinted using `--clay-error`/`--seal-soft` for a missing one,
matching `.vocab-chip.vocab-used`/`.vocab-chip.vocab-missed`'s existing color
choice (`src/components/StoryRecorder.css:3873-3888`) exactly, just applied
to a table row instead of a chip. A word with `used === null` (not yet
analyzed) gets no tint and no tick, same as a chip shows no status today.

Visual styling is deliberately distinct from the teacher builder's table
(`VocabularyTable` in `src/pages/MyStoriesPage.tsx`, which uses jade/violet
accents and interactive controls): these student-facing tables reuse the
existing gold/amber palette (`--gold`, `--gold-soft`, `--gold-deep`) the
overview vocab block already uses for its chips, just laid out as table
rows/cells instead of wrapped chips. No inputs, no dropdown, no buttons —
plain text cells (plus the status tick for #2/#3).

**Missing data**: if a word has no part of speech or no translation filled
in (common for existing stories, or words a teacher hasn't annotated yet),
that cell renders empty — no placeholder text, no layout break. Pinyin keeps
its current fallback behavior (falls back to an auto-computed pinyin via
`toPinyin(word)` when the teacher didn't supply one — unchanged from today).

## Testing

- Existing `StoryRecorder.test.tsx` coverage of all three render sites must
  keep passing (adjusted for the new table markup).
- New coverage per site: a word with both POS and translation shows both in
  their own cells; a word missing one or both shows empty cells without
  breaking the row.
- New coverage for #2/#3: a used word's row is tinted green with a ✓; a
  missing word's row is tinted red with a ✗; a not-yet-analyzed word (no
  `praatMetrics` yet) has neither tint nor tick.
- Confirm the `practice-vocab-chips` vs `ap-vocab-chips` used/missing
  source-of-truth difference (transcription-substring fallback exists only
  in the former) is preserved after the table conversion.

## Out of scope

- Any change to the teacher builder's `VocabularyTable`.
- Any backend or type change (all data already flows through `Topic` from
  the prior plan).
- Any change to the used/missing *determination* logic itself — only its
  display changes.
