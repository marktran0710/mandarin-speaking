import { describe, expect, it } from "vitest";
import { topicQuizEntries, type QuizSourceTopic } from "@entities/vocabulary";
import { speakingVocabularyItems } from "./preview";

const makeTopic = (overrides: Partial<QuizSourceTopic> = {}): QuizSourceTopic & { vocabulary: Record<number, string[]> } => ({
  vocabulary: { 0: ["知道"] },
  vocabularyTranslation: { 0: ["to know"] },
  vocabularyPinyin: { 0: ["zhidao"] },
  vocabularyPos: { 0: ["V"] },
  vocabAssessment: [{
    questionId: "know-easy",
    wordId: "know-1",
    targetWord: "知道",
    pinyin: "zhidao",
    pos: "V",
    simpleEnglishMeaning: "to know",
    level: "easy",
    difficultyWeight: 1,
    questionType: "basic_meaning_mcq",
    answerFormat: "single_choice",
    prompt: "What does 知道 mean?",
    options: ["to know", "to eat"],
    correctAnswer: "to know",
    acceptedAnswers: ["to know"],
    explanation: "",
  }],
  ...overrides,
});

describe("speakingVocabularyItems", () => {
  it("uses exactly the canonical quiz word set", () => {
    const topic = makeTopic();
    expect(speakingVocabularyItems(topic).map((item) => item.word)).toEqual(topicQuizEntries(topic).map((entry) => entry.word));
  });

  it("carries canonical meaning metadata and model audio", () => {
    const topic = makeTopic({ vocabularyAudioUrls: { 0: ["/uploads/audio/zhidao.mp3"] } });
    expect(speakingVocabularyItems(topic)[0]).toMatchObject({ word: "知道", pinyin: "zhidao", pos: "V", meaning: "to know", audioUrl: "/uploads/audio/zhidao.mp3" });
  });

  it("prefers canonical imported word audio over the scene fallback", () => {
    const topic = makeTopic({
      vocabAssessment: [{ ...makeTopic().vocabAssessment![0], audioUrl: "/uploads/audio/imported.mp3" }],
      vocabularyAudioUrls: { 0: ["/uploads/audio/scene-slice.mp3"] },
    });
    expect(speakingVocabularyItems(topic)[0].audioUrl).toBe("/uploads/audio/imported.mp3");
  });

  it("returns an empty list without vocab_assessment", () => {
    expect(speakingVocabularyItems(makeTopic({ vocabAssessment: undefined }))).toEqual([]);
  });
});
