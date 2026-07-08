# Fill vocabulary table from the suggested-answer sentence

Date: 2026-07-08

## Problem

Teachers fill in each scene's vocabulary table (`VocabularyTable` in
`src/pages/MyStoriesPage.tsx`) by hand — one row per word, typing the Chinese
word, pinyin, part of speech, and English translation themselves. Most scenes
already have a "Suggested answer" sentence (`customDraft.suggestedAnswers[index]`)
that contains most or all of the vocabulary the teacher wants students to see.
The teacher wants a button that fills the vocabulary table automatically from
that sentence, instead of retyping (and re-translating) words that are already
right there in the sentence.

## Current data flow (context)

- Each frame's vocabulary lives as four parallel comma-separated draft strings:
  `customDraft.vocabulary[index]`, `vocabularyPinyin[index]`, `vocabularyPos[index]`,
  `vocabularyTranslation[index]` (`src/pages/MyStoriesPage.tsx`).
- `VocabularyTable` (same file, ~line 1911) zips those four strings into
  `VocabRow[]` for editing, keeping its **own** `rows` state (not derived live
  from props) — a deliberate fix (commit `7dea72a`) so a blank row being typed
  into doesn't vanish on every keystroke. Consequently, writing new values into
  `customDraft` from *outside* the table does not by itself update what's
  rendered.
- The existing escape hatch for exactly this: `vocabDraftGeneration`
  (`MyStoriesPage.tsx:703`), used as part of `VocabularyTable`'s React `key`
  (`` `${vocabDraftGeneration}-${index}` ``, line 1333). Bumping it remounts the
  table so it re-derives `rows` from the (now externally-updated) props. Already
  used this way when a story loads for edit and when the edit is cancelled.
- The backend (`backend/main.py`) has no existing translation/dictionary
  endpoint. It does have an established pattern for one-shot AI content
  generation: `POST /api/generate-story-images` calls Gemini
  (`GEMINI_API_KEY`, model `gemini-2.0-flash`, `generateContent`), rate-limited
  via `_check_rate_limit`, with the response JSON extracted through
  `strip_json_fence` + `json.loads`. Unlike that endpoint, there is no
  meaningful deterministic fallback for real translation, so this feature
  requires `GEMINI_API_KEY` to be configured.
- Frontend AI-backed calls follow a consistent shape (see
  `src/pages/TeacherImageBuilderPage.tsx`): a module-level
  `BACKEND_URL = import.meta.env.VITE_BACKEND_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "")`,
  a `fetch` with JSON body, `!response.ok` → read `{ detail }` and throw, and a
  loading/error state around the call. `MyStoriesPage.tsx` has no existing
  backend `fetch` calls of its own (image/audio "upload" there is just a local
  `FileReader` data URL) — this is the first one added to that file.

## Design

### Backend: `POST /api/vocab-from-sentence`

New Pydantic models in `backend/main.py`, next to the other request/response
models:

```python
class VocabFromSentenceRequest(BaseModel):
    sentence: str

class VocabWordSuggestion(BaseModel):
    word: str
    pinyin: str
    pos: str
    translation: str

class VocabFromSentenceResponse(BaseModel):
    words: List[VocabWordSuggestion]
```

Route behavior:

- Rate-limited the same way as `/api/generate-story-images`:
  `_check_rate_limit(f"vocab-from-sentence:{client_ip}", max_requests=10, window_seconds=60)`.
- Validates `sentence.strip()` is non-empty (400 if not — the frontend button
  is disabled when the textarea is empty, so this only guards direct API
  misuse).
- If `GEMINI_API_KEY` is not configured, raise `HTTPException(503, ...)` with a
  message telling the teacher AI vocabulary extraction isn't available on this
  backend. No local/template fallback (unlike image-plan generation) — a wrong
  translation is worse than no autofill.
- Prompts Gemini to segment the sentence into its key vocabulary and return,
  per word: Taiwan-Mandarin pinyin (tone-marked), part of speech (must be one
  of the app's fixed codes: `N, V, Adj, Adv, MW, Particle, Phrase, Other`), and
  a short English translation. Request strict JSON matching
  `VocabFromSentenceResponse`'s shape (array of `{word, pinyin, pos,
  translation}`), Traditional Chinese characters, one entry per distinct word
  (no duplicates even if the word repeats in the sentence).
- Parses the response the same way `generate_story_images_with_gemini` does
  (`strip_json_fence` then `json.loads`).
- Defensive filter: drop any returned entry whose `word` is not actually a
  substring of the input sentence, and drop exact-duplicate words (keep first).
  This mirrors the same "is this word really used in context" check
  `collectQuizEntries` already does client-side for the vocab quiz — it stops a
  hallucinated or malformed entry from silently entering the table.
- On any Gemini/network error, or invalid JSON, raise `HTTPException(502, ...)`
  with a generic "Could not extract vocabulary from that sentence" message
  (mirrors the `except Exception as exc: raise HTTPException(status_code=500,
  ...)` style used elsewhere in `main.py`, using 502 here since it's an
  upstream-provider failure specifically).

### Frontend: fill button on the frame editor

In `MyStoriesPage.tsx`:

- A module-level `BACKEND_URL` constant, following the exact convention in
  `TeacherImageBuilderPage.tsx` (this file has none yet).
- New per-frame loading state: `const [vocabFillLoadingIndex, setVocabFillLoadingIndex] = useState<number | null>(null);` and `const [vocabFillError, setVocabFillError] = useState("");`.
- A button rendered next to the "Suggested answer" textarea (only when
  `customDraft.narrativeMode !== "listen_retell"`, same condition the textarea
  itself already uses — listen-retell frames don't have a suggested-answer
  sentence to draw from):

  ```tsx
  <button
    type="button"
    className="btn-vocab-autofill"
    disabled={!customDraft.suggestedAnswers[index]?.trim() || vocabFillLoadingIndex === index}
    onClick={() => handleFillVocabFromSentence(index)}
  >
    {vocabFillLoadingIndex === index ? "Filling…" : "✨ Fill from suggested answer"}
  </button>
  {vocabFillError && vocabFillLoadingIndex === null && (
    <span className="teacher-form-error">{vocabFillError}</span>
  )}
  ```

- `handleFillVocabFromSentence(index)`:
  1. Clears `vocabFillError`, sets `vocabFillLoadingIndex(index)`.
  2. `fetch(`${BACKEND_URL}/api/vocab-from-sentence`, { method: "POST", ... , body: JSON.stringify({ sentence: customDraft.suggestedAnswers[index] }) })`.
  3. On `!response.ok`, read `{ detail }` and set it as `vocabFillError`.
  4. On success, merge the returned `words` into that frame's four draft
     columns via a new pure helper (see below), then call `updateDraftFrame`
     for each of the four fields with the re-serialized comma strings, then
     `setVocabDraftGeneration((g) => g + 1)` so `VocabularyTable` remounts and
     picks up the new values (same mechanism `handleEditCustomStory` and
     `handleCancelCustomStoryEdit` already use).
  5. `finally`: `setVocabFillLoadingIndex(null)`.

- New pure helper function, alongside `buildVocabRows`/`splitVocabColumn`:

  ```typescript
  function mergeVocabSuggestions(
    existingRows: VocabRow[],
    suggestions: Array<{ word: string; pinyin: string; pos: string; translation: string }>,
  ): VocabRow[] {
    const rows = existingRows.map((r) => ({ ...r }));
    for (const s of suggestions) {
      const match = rows.find((r) => r.word === s.word);
      if (match) {
        if (!match.pinyin.trim()) match.pinyin = s.pinyin;
        if (!match.pos.trim()) match.pos = s.pos;
        if (!match.translation.trim()) match.translation = s.translation;
      } else {
        rows.push({ word: s.word, pinyin: s.pinyin, pos: s.pos, translation: s.translation });
      }
    }
    return rows;
  }
  ```

  Merge semantics (non-destructive): a row already in the table keeps every
  cell the teacher already typed; only blank cells get filled in. A suggested
  word with no matching row is appended as a new row. Rows the teacher typed
  that aren't mentioned in the sentence are left as-is (not removed) — the
  button only ever adds/fills, never deletes.

- CSS: one new small class, `.btn-vocab-autofill`, following the existing
  `.vocab-table-add-btn` dashed-outline style already in `MyStoriesPage.css`.

### Testing

- Backend (`backend/tests/`, new file `test_vocab_from_sentence.py`):
  mocked Gemini response confirms the happy path returns parsed
  `VocabFromSentenceResponse`; a returned word not present in the sentence is
  dropped; a duplicate word is deduped; missing `GEMINI_API_KEY` yields 503;
  a non-200/malformed Gemini reply yields 502.
- Frontend (`src/pages/MyStoriesPage.test.tsx` or a new
  `vocabAutofill.test.ts` colocated with the merge helper): unit tests for
  `mergeVocabSuggestions` covering the three cases (new word appended,
  existing row's blank cells filled, existing row's already-filled cells left
  untouched) — this is the load-bearing logic and is a pure function, so it's
  tested directly rather than through the full component tree.
- Manual: with a real `GEMINI_API_KEY` configured, type a suggested-answer
  sentence, click the button, confirm the table fills; confirm the button is
  disabled with an empty suggested-answer field; confirm a clear error shows
  if the backend is stopped.

## Out of scope

- Editing/regenerating a single row's suggestion individually (the button
  always processes the whole sentence for that frame).
- Any change to the vocab-matching/scoring logic fed to AI feedback — this
  endpoint only ever writes to the table's four draft columns, same as manual
  entry does today.
- Supporting narrative modes other than requiring a non-empty suggested-answer
  sentence (listen-retell frames simply don't show the button, matching how
  they already hide the textarea).
