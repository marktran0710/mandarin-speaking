import { describe, expect, it } from "vitest";
import type { VocabAssessmentQuestion, VocabQuizQuestion } from "@entities/vocabulary";
import {
  applyToneMark,
  extractClozeSentence,
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
