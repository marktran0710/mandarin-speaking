import { describe, expect, it } from "vitest";
import { buildVocabularyInventory, matchesVocabularySearch, vocabularyEntriesToCsv } from "./model";
import { vocabularyBookSource } from "./book-sources";
import type { StoredCustomStory } from "../../services/api/stories-submissions";

const story: StoredCustomStory = { id: "s1", title: "Room", lessonNumber: 5, frames: [{
  imageUrl: "", prompt: "Room prompt", vocabulary: "書, , 桌子", vocabularyPinyin: "shū, , zhuō zi",
  vocabularyTranslation: "book, , table", vocabularyPos: "N, , N",
  vocabularyMedium: "房間", vocabularyTranslationMedium: "room", suggestedAnswer: "我的桌子",
}] };

describe("Speaking vocabulary inventory", () => {
  it("uses the story-wide vocabulary that drives the three practice rounds", () => {
    const words = Array.from({ length: 15 }, (_, index) => `word-${index + 1}`);
    const storyWithCanonicalPool = {
      ...story,
      storyVocabulary: {
        easy: {
          vocabulary: words.join(", "),
          vocabularyPinyin: words.map((_, index) => `pinyin-${index + 1}`).join(", "),
          vocabularyTranslation: words.map((_, index) => `meaning-${index + 1}`).join(", "),
          vocabularyPos: words.map(() => "N").join(", "),
        },
      },
    };
    const entries = buildVocabularyInventory([storyWithCanonicalPool]);
    expect(entries).toHaveLength(15);
    expect(entries.every((entry) => entry.storyWide)).toBe(true);
    expect(entries.map((entry) => entry.word)).toEqual(words);
  });

  it("preserves blank positions and only surfaces the single canonical level", () => {
    const entries = buildVocabularyInventory([story]);
    const table = entries.find(e => e.word === "桌子")!;
    expect(table.wordIndex).toBe(2);
    expect(table.pinyin).toBe("zhuō zi");
    expect(table.expected.translation).toBe("book, , table");
    expect(table.context).toBe("我的桌子");
    // The retired Medium/Hard story-text tiers never appear — every entry is
    // the base vocabulary, so the Medium word "房間" is not surfaced.
    expect(entries.every(e => e.tier === "easy")).toBe(true);
    expect(entries.some(e => e.word === "房間")).toBe(false);
  });
  it("keeps repeated scenes distinct and supports unassigned lessons", () => {
    const entries = buildVocabularyInventory([{ ...story, lessonNumber: null, frames: [story.frames[0], story.frames[0]] }]);
    expect(new Set(entries.map(e => e.id)).size).toBe(entries.length);
    expect(entries.every(e => e.lessonNumber === null)).toBe(true);
  });
  it("searches Chinese, toneless pinyin and meanings", () => {
    const entry = buildVocabularyInventory([story]).find(e => e.word === "桌子")!;
    for (const query of ["桌子", "zhuo zi", "TABLE", "room"]) expect(matchesVocabularySearch(entry, query)).toBe(true);
    expect(matchesVocabularySearch(entry, "swimming")).toBe(false);
  });
  it("does not carry book proof to a different word or lesson", () => {
    expect(vocabularyBookSource({ lessonNumber: 5, word: "桌子" })?.page).toBe(122);
    expect(vocabularyBookSource({ lessonNumber: 6, word: "桌子" })).toBeNull();
    expect(vocabularyBookSource({ lessonNumber: 5, word: "unknown" })).toBeNull();
  });
  it("exports every supplied entry with BOM, escaping and formula protection", () => {
    const entries = buildVocabularyInventory([story]);
    const csv = vocabularyEntriesToCsv([{ ...entries[0], storyTitle: '=HYPERLINK("x")', translation: 'book, "text"', context: 'first\nsecond' }]);
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain('"\'=HYPERLINK(""x"")"');
    expect(csv).toContain('"book, ""text"""');
    expect(csv).toContain('"first\nsecond"');
  });
  it("exports book provenance only for the checked lesson and word", () => {
    const entry = buildVocabularyInventory([story]).find(e => e.word === "桌子")!;
    expect(vocabularyEntriesToCsv([entry])).toContain('"Modern Chinese 1","122","Vocabulary list"');
    expect(vocabularyEntriesToCsv([{ ...entry, lessonNumber: 6 }])).toContain('"Not verified","",""');
  });
});
