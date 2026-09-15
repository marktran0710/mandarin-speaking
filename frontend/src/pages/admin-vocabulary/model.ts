import type { StoredCustomStory } from "../../services/api/stories-submissions";
import { buildVocabRows, type VocabRow } from "../../utils/myStoriesUtils";
import { tierText } from "../../utils/teacher-stories/helpers";
import { vocabularyBookSource } from "./book-sources";

export type VocabularyTier = "easy";
export interface VocabularyEntry extends VocabRow {
  id: string;
  storyId: string;
  storyTitle: string;
  lessonNumber: number | null;
  lessonSubOrder: number | null;
  frameIndex: number;
  wordIndex: number;
  tier: VocabularyTier;
  context: string;
  published: boolean;
  expected: { vocabulary: string; pinyin: string; translation: string; pos: string };
}

// The quiz now runs a single vocabulary set through three rounds; the old
// extra story-text levels are no longer surfaced to students, and the per-word
// AI question data (distractors/cloze/synonym) only ever existed on the base
// word list anyway. So the inventory is built from that one canonical level —
// never triplicated. (`tier` stays "easy" on each entry because the
// metadata-save API is still keyed by it.)
const CANONICAL_TIER = "easy" as const;

export function buildVocabularyInventory(stories: StoredCustomStory[]): VocabularyEntry[] {
  return [...stories].sort((a, b) => (a.lessonNumber ?? Infinity) - (b.lessonNumber ?? Infinity)
    || (a.lessonSubOrder ?? 0) - (b.lessonSubOrder ?? 0) || a.title.localeCompare(b.title))
    .flatMap(story => story.frames.flatMap((frame, frameIndex) => {
      const expected = {
        vocabulary: tierText(frame, "vocabulary", CANONICAL_TIER) || "",
        pinyin: tierText(frame, "vocabularyPinyin", CANONICAL_TIER) || "",
        translation: tierText(frame, "vocabularyTranslation", CANONICAL_TIER) || "",
        pos: tierText(frame, "vocabularyPos", CANONICAL_TIER) || "",
      };
      return buildVocabRows(expected.vocabulary, expected.pinyin, expected.pos, expected.translation)
        .map((row, wordIndex) => ({
          ...row, id: JSON.stringify([story.id, frameIndex, wordIndex]), storyId: story.id,
          storyTitle: story.title, lessonNumber: story.lessonNumber ?? null,
          lessonSubOrder: story.lessonSubOrder ?? null, frameIndex, wordIndex, tier: CANONICAL_TIER, expected,
          context: tierText(frame, "suggestedAnswer", CANONICAL_TIER) || tierText(frame, "listenScript", CANONICAL_TIER) || tierText(frame, "prompt", CANONICAL_TIER) || "",
          published: Boolean(story.published),
        })).filter(row => Boolean(row.word));
    }));
}

const searchKey = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
export function matchesVocabularySearch(entry: VocabularyEntry, query: string): boolean {
  return searchKey([entry.word, entry.pinyin, entry.translation, entry.storyTitle].join(" ")).includes(searchKey(query.trim()));
}

export function vocabularyEntriesToCsv(entries: VocabularyEntry[]): string {
  const cell = (value: string | number | null) => {
    const text = String(value ?? "");
    const safe = /^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text) ? `'${text}` : text;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const rows = entries.map(e => {
    const source = vocabularyBookSource(e);
    return [e.lessonNumber, e.lessonSubOrder, e.storyTitle, e.frameIndex + 1,
      e.word, e.pinyin, e.pos, e.translation, e.context, source?.book ?? "Not verified", source?.page ?? null, source?.kind ?? ""];
  });
  return "\uFEFF" + [["Lesson", "Part", "Speaking story", "Scene", "Word", "Pinyin", "Part of speech", "Meaning", "Speaking context", "Book source", "Printed page", "Source section"], ...rows]
    .map(row => row.map(cell).join(",")).join("\r\n");
}
