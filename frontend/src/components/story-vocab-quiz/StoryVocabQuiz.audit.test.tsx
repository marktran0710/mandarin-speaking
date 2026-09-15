import { describe, expect, it } from "vitest";
import { auditQuizQuestion } from "../../utils/quizAudit";
import type { VocabQuizEntry, VocabQuizQuestion } from "./StoryVocabQuiz";

describe("auditQuizQuestion — synthetic violations", () => {
  const entries: VocabQuizEntry[] = [
    { word: "高興", translation: "happy", pinyin: "gāoxìng" },
    { word: "開心", translation: "happy", pinyin: "kāixīn" },
    { word: "他", translation: "he", pinyin: "tā" },
    { word: "她", translation: "she", pinyin: "tā" },
    { word: "學校", translation: "school", pinyin: "xuéxiào" },
  ];

  it("flags a missing correct answer", () => {
    const q: VocabQuizQuestion = {
      kind: "translation",
      word: "學校",
      correctTranslation: "school",
      options: ["home", "friend", "water"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("correct-answer-missing");
  });

  it("flags case/punctuation-disguised duplicate options", () => {
    const q: VocabQuizQuestion = {
      kind: "translation",
      word: "學校",
      correctTranslation: "school",
      options: ["school", "School.", "water", "home"],
      isAiGenerated: false,
    };
    const rules = auditQuizQuestion(q, entries).map((i) => i.rule);
    expect(rules).toContain("duplicate-options");
    expect(rules).toContain("distractor-equals-correct");
  });

  it("flags a reverse question whose distractor shares the prompt translation", () => {
    const q: VocabQuizQuestion = {
      kind: "reverse",
      word: "高興",
      translation: "happy",
      correctWord: "高興",
      options: ["高興", "開心", "學校", "他"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("reverse-second-correct");
  });

  it("flags a listening question with a homophone distractor (他/她)", () => {
    const q: VocabQuizQuestion = {
      kind: "listening",
      word: "他",
      correctWord: "他",
      options: ["他", "她", "學校", "高興"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("listening-homophone");
  });

  it("flags a cloze sentence that still shows the answer", () => {
    const q: VocabQuizQuestion = {
      kind: "cloze",
      word: "學校",
      sentenceWithBlank: "我去____，學校很大。",
      correctWord: "學校",
      options: ["學校", "他", "高興"],
      isAiGenerated: true,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("cloze-answer-leak");
  });

  it("flags a synonym question whose distractor shares the prompt's translation", () => {
    const q: VocabQuizQuestion = {
      kind: "synonym",
      word: "高興",
      correctSynonym: "快樂",
      options: ["快樂", "開心", "學校", "他"],
      isAiGenerated: true,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("synonym-second-correct");
  });

  it("accepts a clean question", () => {
    const q: VocabQuizQuestion = {
      kind: "translation",
      word: "學校",
      correctTranslation: "school",
      options: ["school", "home", "friend", "water"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).filter((i) => i.severity === "error")).toEqual([]);
  });
});
