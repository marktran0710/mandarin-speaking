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

  it("uses vocabAssessment as the quiz source even when its words differ from frame vocabulary", () => {
    const storyWithAssessment = {
      ...story,
      frames: [{
        imageUrl: "", prompt: "p", vocabulary: "書, 桌子, 房間", vocabularyPinyin: "shū, zhuō zi, fáng jiān",
        vocabularyTranslation: "book, table, room", vocabularyPos: "N, N, N",
      }],
      vocabAssessment: [
        { questionId: "q1", wordId: "w1", targetWord: "書", pinyin: "shū", pos: "N", simpleEnglishMeaning: "book", level: "easy", difficultyWeight: 1, questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "", options: [], correctAnswer: "book", acceptedAnswers: ["book"], explanation: "" },
        { questionId: "q2", wordId: "w2", targetWord: "桌子", pinyin: "zhuō zi", pos: "N", simpleEnglishMeaning: "table", level: "easy", difficultyWeight: 1, questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "", options: [], correctAnswer: "table", acceptedAnswers: ["table"], explanation: "" },
        { questionId: "q3", wordId: "w3", targetWord: "哪裡 / 哪兒", pinyin: "nǎlǐ / nǎr", pos: "Pron", simpleEnglishMeaning: "where", level: "easy", difficultyWeight: 1, questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "", options: [], correctAnswer: "where", acceptedAnswers: ["where"], explanation: "" },
      ],
    } as StoredCustomStory;
    const entries = buildVocabularyInventory([storyWithAssessment]);
    expect(entries.map(e => e.word)).toEqual(["書", "桌子", "哪裡 / 哪兒"]);
    expect(entries.every(entry => entry.source === "quiz-assessment")).toBe(true);
    // The assessment identity lets edits update all three quiz rounds for a word.
    const table = entries.find(e => e.word === "桌子")!;
    expect(table.assessmentWordId).toBe("w2");
    expect(table.expected).toEqual({ vocabulary: "桌子", pinyin: "zhuō zi", translation: "table", pos: "N" });
  });

  it("uses each lesson part's quiz bank independently", () => {
    const assessmentQuestion = (questionId: string, wordId: string, targetWord: string, pinyin: string, meaning: string) => ({
      questionId, wordId, targetWord, pinyin, pos: "N", simpleEnglishMeaning: meaning,
      level: "easy" as const, difficultyWeight: 1, questionType: "basic_meaning_mcq" as const,
      answerFormat: "single_choice" as const, prompt: "", options: [], correctAnswer: meaning,
      acceptedAnswers: [meaning], explanation: "",
    });
    const assessedStories = [
      { ...story, id: "lesson-1-part-2", lessonNumber: 1, lessonSubOrder: 2, vocabAssessment: [
        assessmentQuestion("l1-easy", "l1-word", "朋友", "péngyou", "friend"),
        assessmentQuestion("l1-medium", "l1-word", "朋友", "péngyou", "friend"),
        assessmentQuestion("l1-hard", "l1-word", "朋友", "péngyou", "friend"),
      ] },
      { ...story, id: "lesson-6-part-1", lessonNumber: 6, lessonSubOrder: 1, vocabAssessment: [
        assessmentQuestion("l6-easy", "l6-word", "游泳", "yóuyǒng", "swim"),
        assessmentQuestion("l6-medium", "l6-word", "游泳", "yóuyǒng", "swim"),
        assessmentQuestion("l6-hard", "l6-word", "游泳", "yóuyǒng", "swim"),
      ] },
    ] as StoredCustomStory[];

    const entries = buildVocabularyInventory([...assessedStories, story]);
    expect(entries.filter(entry => entry.source === "quiz-assessment")).toMatchObject([
      { storyId: "lesson-1-part-2", lessonNumber: 1, lessonSubOrder: 2, word: "朋友", assessmentWordId: "l1-word" },
      { storyId: "lesson-6-part-1", lessonNumber: 6, lessonSubOrder: 1, word: "游泳", assessmentWordId: "l6-word" },
    ]);
    // One row per wordId mirrors the live quiz even though it stores three rounds.
    expect(entries.filter(entry => entry.source === "quiz-assessment")).toHaveLength(2);
    // A legacy story without an assessment still keeps its own authored source.
    expect(entries.filter(entry => entry.storyId === story.id).every(entry => entry.source === "scene-vocabulary")).toBe(true);
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
