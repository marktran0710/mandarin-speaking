import { describe, expect, it } from "vitest";
import { topicQuizEntries, type QuizSourceTopic } from "./topicQuiz";
import { speakingVocabularyItems } from "./speakingVocabulary";

function makeTopic(overrides: Partial<QuizSourceTopic> = {}): QuizSourceTopic {
  return {
    images: ["scene-1.png", "scene-2.png"],
    vocabulary: { 0: ["知道", "一起"], 1: ["朋友", "下午茶"] },
    vocabularyTranslation: { 0: ["to know", "together"], 1: ["friend", "afternoon tea"] },
    vocabularyPinyin: { 0: ["zhīdào", "yìqǐ"], 1: ["péngyǒu", "xiàwǔchá"] },
    vocabularyPos: { 0: ["V", "Adv"], 1: ["N", "N"] },
    ...overrides,
  };
}

describe("speakingVocabularyItems", () => {
  it("uses exactly topicQuizEntries's word set and order - the same source the quiz itself uses", () => {
    const topic = makeTopic();
    const items = speakingVocabularyItems(topic);
    const quizWords = topicQuizEntries(topic).map((entry) => entry.word);
    expect(items.map((item) => item.word)).toEqual(quizWords);
  });

  it("carries pinyin/pos/meaning through from the quiz entry", () => {
    const [first] = speakingVocabularyItems(makeTopic());
    expect(first).toMatchObject({ word: "知道", pinyin: "zhīdào", pos: "V", meaning: "to know" });
  });

  it("a 15-word quiz pool produces a 15-word preview, not a per-scene count", () => {
    const vocabulary: Record<number, string[]> = {};
    const translation: Record<number, string[]> = {};
    for (let scene = 0; scene < 3; scene += 1) {
      vocabulary[scene] = Array.from({ length: 5 }, (_, i) => `word-${scene}-${i}`);
      translation[scene] = Array.from({ length: 5 }, (_, i) => `meaning-${scene}-${i}`);
    }
    const items = speakingVocabularyItems(makeTopic({
      images: ["scene-1.png", "scene-2.png", "scene-3.png"],
      vocabulary,
      vocabularyTranslation: translation,
      vocabularyPinyin: undefined,
      vocabularyPos: undefined,
    }));
    expect(items).toHaveLength(15);
  });

  it("looks up a word's model audio from vocabularyAudioUrls when present", () => {
    const topic = {
      ...makeTopic(),
      vocabularyAudioUrls: { 0: ["/uploads/audio/zhidao.mp3", null], 1: [null, null] },
    };
    const items = speakingVocabularyItems(topic);
    expect(items.find((item) => item.word === "知道")?.audioUrl).toBe("/uploads/audio/zhidao.mp3");
    expect(items.find((item) => item.word === "一起")?.audioUrl).toBeUndefined();
  });

  it("leaves audioUrl undefined when no vocabularyAudioUrls exist at all", () => {
    const items = speakingVocabularyItems(makeTopic());
    expect(items.every((item) => item.audioUrl === undefined)).toBe(true);
  });

  it("returns an empty list for a story with no quiz vocabulary", () => {
    const items = speakingVocabularyItems(makeTopic({ vocabulary: {}, vocabularyTranslation: {}, vocabularyPinyin: {}, vocabularyPos: {} }));
    expect(items).toEqual([]);
  });
});
