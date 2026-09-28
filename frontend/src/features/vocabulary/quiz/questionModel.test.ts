import { describe, expect, it } from "vitest";
import type { VocabAssessmentQuestion, VocabQuizQuestion } from "@entities/vocabulary";
import {
  applyToneMark,
  diagnosePinyin,
  extractClozeSentence,
  questionHint,
  questionPresentation,
  sentenceSegments,
} from "./questionModel";

function assessmentQuestion(
  questionType: VocabAssessmentQuestion["questionType"],
  answerFormat: VocabAssessmentQuestion["answerFormat"],
  prompt: string,
): VocabQuizQuestion {
  const assessment: VocabAssessmentQuestion = {
    questionId: `${questionType}-1`,
    wordId: "word-1",
    targetWord: "電話",
    pinyin: "diàn huà",
    pos: "N",
    simpleEnglishMeaning: "telephone",
    level: "easy",
    difficultyWeight: 1,
    questionType,
    answerFormat,
    prompt,
    options: ["電話", "朋友", "老師", "電腦"],
    correctAnswer: answerFormat === "free_text" ? "diàn huà" : "電話",
    acceptedAnswers: [answerFormat === "free_text" ? "diàn huà" : "電話"],
    explanation: "A useful context clue.",
  };
  return {
    kind: "assessment",
    word: "電話",
    prompt,
    options: assessment.options,
    correctAnswer: assessment.correctAnswer,
    acceptedAnswers: assessment.acceptedAnswers,
    explanation: assessment.explanation,
    assessment,
    isAiGenerated: false,
  };
}

describe("quiz question presentation", () => {
  it.each([
    ["basic_meaning_mcq", "single_choice", "meaning"],
    ["character_to_pinyin_typing", "free_text", "pinyin"],
    ["context_cloze_mcq", "single_choice", "context"],
  ] as const)("maps %s to the %s surface", (questionType, answerFormat, surface) => {
    const question = assessmentQuestion(questionType, answerFormat, "Choose the correct answer.");
    const presentation = questionPresentation(question);
    expect(presentation.surface).toBe(surface);
    if (surface === "context") expect(presentation.label).toBe("Sentence completion");
    if (surface === "pinyin") expect(presentation.pinyin).toBeUndefined();
  });

  it("parses a cloze marker without inventing a translation", () => {
    expect(extractClozeSentence("Choose the correct word in the sentence: 我找不到____。"))
      .toEqual({ before: "我找不到", after: "。", hasBlank: true });
    expect(extractClozeSentence("他在___裡看書。"))
      .toEqual({ before: "他在", after: "裡看書。", hasBlank: true });
    expect(extractClozeSentence("他在CLOZE_BLANK裡看書。"))
      .toEqual({ before: "他在", after: "裡看書。", hasBlank: true });
    expect(extractClozeSentence("我找不到電話。", "我找不到____。"))
      .toEqual({ before: "我找不到", after: "。", hasBlank: true });
  });

  it("falls back to plain sentence text when aligned pinyin is unavailable", () => {
    expect(sentenceSegments("我找不到____。"))
      .toEqual([{ text: "我找不到" }, { text: "____。" }]);
  });
});

describe("tone keypad editing", () => {
  it("replaces a tone number with a tone mark in the current syllable", () => {
    expect(applyToneMark("ni3", 2, 3, 3)).toEqual({ value: "ní", cursor: 2 });
  });

  it.each([
    [1, "mā"],
    [2, "má"],
    [3, "mǎ"],
    [4, "mà"],
  ] as const)("maps the %s keypad tone to the matching mark", (tone, expected) => {
    expect(applyToneMark("ma", tone, 2, 2).value).toBe(expected);
  });

  it("treats v as the keyboard spelling for ü", () => {
    expect(applyToneMark("lv4", 3, 3, 3)).toEqual({ value: "lǚ", cursor: 2 });
  });

  it("preserves the rest of a multi-syllable draft", () => {
    expect(applyToneMark("ni hao", 3, 6, 6).value).toBe("ni hǎo");
  });
});

describe("diagnosePinyin", () => {
  it("points at the syllable with the wrong tone without giving the reading", () => {
    expect(diagnosePinyin("ni3 hao4", "nǐ hǎo")).toEqual({ syllableIssues: [{ syllable: 2, issue: "tone" }] });
    expect(diagnosePinyin("nǐ háo", "nǐ hǎo")).toEqual({ syllableIssues: [{ syllable: 2, issue: "tone" }] });
  });

  it("separates a wrong initial from a wrong final", () => {
    expect(diagnosePinyin("zhi1 dao4", "zhī dào")).toEqual({ syllableIssues: [] });
    expect(diagnosePinyin("chi1 dao4", "zhī dào")).toEqual({ syllableIssues: [{ syllable: 1, issue: "initial" }] });
    expect(diagnosePinyin("zhī dòu", "zhī dào")).toEqual({ syllableIssues: [{ syllable: 2, issue: "final" }] });
  });

  it("aligns run-together numeric input by its tone digits", () => {
    expect(diagnosePinyin("ni3hao3", "nǐ hǎo")).toEqual({ syllableIssues: [] });
    expect(diagnosePinyin("ni2hao3", "nǐ hǎo")).toEqual({ syllableIssues: [{ syllable: 1, issue: "tone" }] });
  });

  it("flags a different number of syllables", () => {
    expect(diagnosePinyin("ni3", "nǐ hǎo")).toEqual({ syllableCountWrong: true });
  });
});

function hintQuestion(assessment: Omit<VocabAssessmentQuestion, "level" | "difficultyWeight">): VocabQuizQuestion {
  return {
    kind: "assessment",
    word: assessment.targetWord,
    prompt: assessment.prompt,
    options: assessment.options,
    correctAnswer: assessment.correctAnswer,
    acceptedAnswers: assessment.acceptedAnswers,
    explanation: assessment.explanation,
    assessment,
    isAiGenerated: false,
  };
}

describe("questionHint", () => {
  const baseAssessment = {
    questionId: "q1",
    wordId: "w1",
    targetWord: "喜歡",
    pinyin: "xǐ huān",
    pos: "V",
    simpleEnglishMeaning: "to like",
    options: [],
    acceptedAnswers: [],
    explanation: "",
  };

  it("Know It: a lesson sentence with the word, else its word class — never the meaning", () => {
    const question = hintQuestion({ ...baseAssessment, questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "喜歡", correctAnswer: "to like" });
    expect(questionHint(question, { word: "喜歡", translation: "to like", lessonSentences: ["他很喜歡喝茶。"] }, "to eat"))
      .toEqual({ example: "他很喜歡喝茶。" });
    expect(questionHint(question, { word: "喜歡", translation: "to like" }, "to eat")).toEqual({ wordClass: "V" });
  });

  it("Say It: the English meaning plus the syllable diagnosis", () => {
    const question = hintQuestion({ ...baseAssessment, questionType: "character_to_pinyin_typing", answerFormat: "free_text", prompt: "喜歡", correctAnswer: "xǐ huān" });
    expect(questionHint(question, undefined, "xi3 huan2")).toEqual({
      meaning: "to like",
      syllableIssues: [{ syllable: 2, issue: "tone" }],
    });
  });

  it("Use It: the pinyin of the missing word", () => {
    const question = hintQuestion({ ...baseAssessment, questionType: "context_cloze_mcq", answerFormat: "single_choice", prompt: "我____喝茶。", correctAnswer: "喜歡" });
    expect(questionHint(question, undefined, "看")).toEqual({ pinyin: "xǐ huān" });
  });
});
