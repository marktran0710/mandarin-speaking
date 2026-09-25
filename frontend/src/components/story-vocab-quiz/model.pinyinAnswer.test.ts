import { describe, expect, it } from "vitest";
import { assessmentAnswerIsCorrect, type VocabQuizAssessmentQuestion } from "@entities/vocabulary";

/** Build a minimal assessment question of a given questionType + accepted answers. */
function question(
  questionType: VocabQuizAssessmentQuestion["assessment"]["questionType"],
  acceptedAnswers: string[],
): VocabQuizAssessmentQuestion {
  const correctAnswer = acceptedAnswers[0];
  return {
    kind: "assessment",
    word: "咖啡廳",
    prompt: "Type the pinyin for 咖啡廳.",
    options: [],
    correctAnswer,
    acceptedAnswers,
    explanation: "",
    isAiGenerated: false,
    assessment: {
      questionId: "q1", wordId: "w1", targetWord: "咖啡廳", pinyin: correctAnswer,
      pos: "n", simpleEnglishMeaning: "café", level: "medium", difficultyWeight: 2,
      questionType, answerFormat: "free_text", prompt: "Type the pinyin for 咖啡廳.",
      options: [], correctAnswer, acceptedAnswers, explanation: "",
    },
  };
}

describe("assessmentAnswerIsCorrect — pinyin typing round accepts tone numbers", () => {
  const pinyin = question("character_to_pinyin_typing", ["kā fēi tīng"]);

  it("accepts the tone-marked reading (spaced or unspaced)", () => {
    expect(assessmentAnswerIsCorrect(pinyin, "kā fēi tīng")).toBe(true);
    expect(assessmentAnswerIsCorrect(pinyin, "kāfēitīng")).toBe(true);
  });

  it("accepts numeric tones, spaced and unspaced", () => {
    expect(assessmentAnswerIsCorrect(pinyin, "ka1 fei1 ting1")).toBe(true);
    expect(assessmentAnswerIsCorrect(pinyin, "ka1fei1ting1")).toBe(true);
    expect(assessmentAnswerIsCorrect(pinyin, "KA1 FEI1 TING1")).toBe(true);
  });

  it("requires tone: a toneless spelling stays wrong", () => {
    expect(assessmentAnswerIsCorrect(pinyin, "kafeiting")).toBe(false);
    expect(assessmentAnswerIsCorrect(pinyin, "ka fei ting")).toBe(false);
  });

  it("rejects a wrong tone", () => {
    // Third-tone káfēitīng ≠ first-tone answer.
    expect(assessmentAnswerIsCorrect(pinyin, "ka2 fei1 ting1")).toBe(false);
  });

  it("handles the ü / v spelling and neutral tone", () => {
    const nv = question("character_to_pinyin_typing", ["nǚ"]);
    expect(assessmentAnswerIsCorrect(nv, "nv3")).toBe(true);
    expect(assessmentAnswerIsCorrect(nv, "nü3")).toBe(true);
    const neutral = question("character_to_pinyin_typing", ["wǒ men"]);
    expect(assessmentAnswerIsCorrect(neutral, "wo3 men5")).toBe(true);
    expect(assessmentAnswerIsCorrect(neutral, "wo3 men")).toBe(true);
  });

  it("does NOT rewrite numbers in a non-pinyin free-text answer", () => {
    // Round 3 answers are Chinese, not pinyin — the numeric fold must not apply.
    const contextual = question("contextual_productive_recall", ["ka1 fei1 ting1"]);
    // The stored answer literally contains the numbers, so the raw match still
    // works, but a tone-marked submission must NOT be folded into it.
    expect(assessmentAnswerIsCorrect(contextual, "ka1 fei1 ting1")).toBe(true);
    expect(assessmentAnswerIsCorrect(contextual, "kā fēi tīng")).toBe(false);
  });
});
