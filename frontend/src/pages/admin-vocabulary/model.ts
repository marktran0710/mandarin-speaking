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
  storyWide: boolean;
  tier: VocabularyTier;
  context: string;
  published: boolean;
  expected: { vocabulary: string; pinyin: string; translation: string; pos: string };
}

// The quiz runs one vocabulary set through three rounds. The per-word AI
// question data (distractors/cloze/synonym) belongs to that base word list, so
// the inventory is built from one canonical level and never triplicated.
// (`tier` stays "easy" because the metadata-save API is still keyed by it.)
const CANONICAL_TIER = "easy" as const;

export function buildVocabularyInventory(stories: StoredCustomStory[]): VocabularyEntry[] {
  return [...stories].sort((a, b) => (a.lessonNumber ?? Infinity) - (b.lessonNumber ?? Infinity)
    || (a.lessonSubOrder ?? 0) - (b.lessonSubOrder ?? 0) || a.title.localeCompare(b.title))
    .flatMap(story => {
      const storyWide = story.storyVocabulary?.easy;
      if (storyWide) {
        const expected = {
          vocabulary: storyWide.vocabulary || "",
          pinyin: storyWide.vocabularyPinyin || "",
          translation: storyWide.vocabularyTranslation || "",
          pos: storyWide.vocabularyPos || "",
        };
        const context = story.frames.find(frame => frame.suggestedAnswer || frame.listenScript || frame.prompt);
        return buildVocabRows(expected.vocabulary, expected.pinyin, expected.pos, expected.translation)
          .map((row, wordIndex) => ({
            ...row, id: JSON.stringify([story.id, "story-wide", wordIndex]), storyId: story.id,
            storyTitle: story.title, lessonNumber: story.lessonNumber ?? null,
            lessonSubOrder: story.lessonSubOrder ?? null, frameIndex: 0, wordIndex, tier: CANONICAL_TIER,
            storyWide: true, expected,
            context: context ? tierText(context, "suggestedAnswer", CANONICAL_TIER) || tierText(context, "listenScript", CANONICAL_TIER) || tierText(context, "prompt", CANONICAL_TIER) || "" : "",
            published: Boolean(story.published),
          })).filter(row => Boolean(row.word));
      }
      return story.frames.flatMap((frame, frameIndex) => {
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
          storyWide: false,
          context: tierText(frame, "suggestedAnswer", CANONICAL_TIER) || tierText(frame, "listenScript", CANONICAL_TIER) || tierText(frame, "prompt", CANONICAL_TIER) || "",
          published: Boolean(story.published),
        })).filter(row => Boolean(row.word));
      });
    });
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
    return [e.lessonNumber, e.lessonSubOrder, e.storyTitle, e.storyWide ? "Story-wide" : e.frameIndex + 1,
      e.word, e.pinyin, e.pos, e.translation, e.context, source?.book ?? "Not verified", source?.page ?? null, source?.kind ?? ""];
  });
  return "\uFEFF" + [["Lesson", "Part", "Speaking story", "Scene", "Word", "Pinyin", "Part of speech", "Meaning", "Speaking context", "Book source", "Printed page", "Source section"], ...rows]
    .map(row => row.map(cell).join(",")).join("\r\n");
}
