import { describe, expect, it } from "vitest";
import {
  attemptHistoryFromAudioRecords,
  buildClozePatchUpdates,
  buildDistractorPatchUpdates,
  planClozeGrowth,
  planDistractorGrowth,
  sceneSubmissionFromAudioRecord,
  vocabTooltip,
} from "./StoryRecorder";
describe("vocabTooltip", () => {
  it("combines part of speech and translation", () => {
    expect(vocabTooltip("N", "restaurant")).toBe("(N) restaurant");
  });

  it("returns just the POS in parens when translation is missing", () => {
    expect(vocabTooltip("N", undefined)).toBe("(N)");
  });

  it("returns just the translation when POS is missing", () => {
    expect(vocabTooltip(undefined, "restaurant")).toBe("restaurant");
  });

  it("returns undefined when both are missing", () => {
    expect(vocabTooltip(undefined, undefined)).toBeUndefined();
  });
});

describe("persisted speaking-result restoration", () => {
  it("restores every persisted attempt for each scene in chronological order", () => {
    const history = attemptHistoryFromAudioRecords([
      { id: "newest", timestamp: "3", duration: 1, transcription: "", model: "", imageIndex: 0, attemptNumber: 3, praatMetrics: { tone_accuracy: 90, fluency_score: 80 } },
      { id: "other-scene", timestamp: "2", duration: 1, transcription: "", model: "", imageIndex: 1, praatMetrics: { tone_accuracy: 60, fluency_score: 50 } },
      { id: "oldest", timestamp: "1", duration: 1, transcription: "", model: "", imageIndex: 0, attemptNumber: 1, praatMetrics: { tone_accuracy: 70, fluency_score: 65 } },
    ]);

    expect(history[0]).toEqual([
      { tone: 70, fluency: 65, attempt: 1 },
      { tone: 90, fluency: 80, attempt: 3 },
    ]);
    expect(history[1]).toEqual([{ tone: 60, fluency: 50, attempt: 1 }]);
  });

  it("rebuilds a legacy scene snapshot from the latest audio record", () => {
    expect(sceneSubmissionFromAudioRecord({
      id: "latest", timestamp: "1", duration: 1, transcription: "Saved transcript", model: "",
      imageIndex: 0, imageUrl: "scene.png", audioUrl: "/uploads/latest.wav",
      praatMetrics: {
        tone_accuracy: 82, fluency_score: 71,
        word_prosody: [{ token: "word", index: 0, start_time: 0, end_time: 1, pitch_contour: [], mean_pitch: 0, pitch_range: 0, start_pitch: 0, end_pitch: 0, contour_shape: "", feedback: "", tone_accuracy: 75 }],
        ai_feedback: { vocabulary_coverage: { score: 100, used: ["word"], missing: [], feedback: "" } },
      },
    })).toMatchObject({
      sceneIndex: 0, transcription: "Saved transcript", vocabScore: 100,
      toneAccuracy: 82, fluencyScore: 71, audioUrl: "/uploads/latest.wav",
    });
  });
});

describe("planDistractorGrowth", () => {
  const baseTopic = {
    images: ["scene-1.jpg"],
    vocabulary: { 0: ["餐廳", "吃"] },
    vocabularyTranslation: { 0: ["restaurant", "to eat"] },
    suggestedAnswers: { 0: "我在餐廳吃飯。" },
  };

  it("includes words with no persisted distractors yet", () => {
    const candidates = planDistractorGrowth(baseTopic);
    expect(candidates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        word: "餐廳",
        translation: "restaurant",
        context: "我在餐廳吃飯。",
        existing: [],
      },
      {
        frameIndex: 0,
        wordIndex: 1,
        word: "吃",
        translation: "to eat",
        context: "我在餐廳吃飯。",
        existing: [],
      },
    ]);
  });

  it("skips words that already reached the 8-distractor cap", () => {
    const candidates = planDistractorGrowth({
      ...baseTopic,
      vocabularyDistractors: {
        0: [["a", "b", "c", "d", "e", "f", "g", "h"], ["kitchen"]],
      },
    });
    expect(candidates.map((c) => c.word)).toEqual(["吃"]);
    expect(candidates[0].existing).toEqual(["kitchen"]);
  });

  it("returns an empty array once every word is at cap (signal to skip the AI call)", () => {
    const candidates = planDistractorGrowth({
      ...baseTopic,
      vocabularyDistractors: {
        0: [
          ["a", "b", "c", "d", "e", "f", "g", "h"],
          ["a", "b", "c", "d", "e", "f", "g", "h"],
        ],
      },
    });
    expect(candidates).toEqual([]);
  });

  it("skips words with no translation", () => {
    const candidates = planDistractorGrowth({
      ...baseTopic,
      vocabularyTranslation: { 0: ["restaurant", ""] },
    });
    expect(candidates.map((c) => c.word)).toEqual(["餐廳"]);
  });
});

describe("buildDistractorPatchUpdates", () => {
  const candidates = [
    { frameIndex: 0, wordIndex: 0, word: "餐廳", translation: "restaurant", existing: [] },
    { frameIndex: 0, wordIndex: 1, word: "吃", translation: "to eat", existing: ["kitchen"] },
  ];

  it("maps AI results back to frame/word indices by word text", () => {
    const updates = buildDistractorPatchUpdates(candidates, [
      { word: "餐廳", distractors: ["hotel", "cafe"] },
      { word: "吃", distractors: ["to drink"] },
    ]);
    expect(updates).toEqual([
      { frameIndex: 0, wordIndex: 0, distractors: ["hotel", "cafe"] },
      { frameIndex: 0, wordIndex: 1, distractors: ["to drink"] },
    ]);
  });

  it("drops candidates the AI returned nothing for", () => {
    const updates = buildDistractorPatchUpdates(candidates, [
      { word: "餐廳", distractors: ["hotel"] },
    ]);
    expect(updates).toEqual([{ frameIndex: 0, wordIndex: 0, distractors: ["hotel"] }]);
  });

  it("returns an empty array when the AI returned nothing for any candidate", () => {
    expect(buildDistractorPatchUpdates(candidates, [])).toEqual([]);
  });
});

describe("planClozeGrowth", () => {
  const baseTopic = {
    images: ["scene-1.jpg"],
    vocabulary: { 0: ["餐廳", "吃"] },
    vocabularyTranslation: { 0: ["restaurant", "to eat"] },
    suggestedAnswers: { 0: "我在餐廳吃飯。" },
  };

  it("includes words with no persisted cloze candidates yet", () => {
    const candidates = planClozeGrowth(baseTopic);
    expect(candidates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        word: "餐廳",
        translation: "restaurant",
        context: "我在餐廳吃飯。",
        existing: [],
      },
      {
        frameIndex: 0,
        wordIndex: 1,
        word: "吃",
        translation: "to eat",
        context: "我在餐廳吃飯。",
        existing: [],
      },
    ]);
  });

  it("skips words that already reached the 4-candidate cap, passing existing sentences as the avoid list", () => {
    const candidates = planClozeGrowth({
      ...baseTopic,
      vocabularyCloze: {
        0: [
          [
            { sentence: "s1", distractors: ["a"] },
            { sentence: "s2", distractors: ["b"] },
            { sentence: "s3", distractors: ["c"] },
            { sentence: "s4", distractors: ["d"] },
          ],
          [{ sentence: "s5", distractors: ["e"] }],
        ],
      },
    });
    expect(candidates.map((c) => c.word)).toEqual(["吃"]);
    expect(candidates[0].existing).toEqual(["s5"]);
  });

  it("returns an empty array once every word is at cap (signal to skip the AI call)", () => {
    const fullPool = [
      { sentence: "s1", distractors: ["a"] },
      { sentence: "s2", distractors: ["b"] },
      { sentence: "s3", distractors: ["c"] },
      { sentence: "s4", distractors: ["d"] },
    ];
    const candidates = planClozeGrowth({
      ...baseTopic,
      vocabularyCloze: { 0: [fullPool, fullPool] },
    });
    expect(candidates).toEqual([]);
  });

  it("skips words with no translation", () => {
    const candidates = planClozeGrowth({
      ...baseTopic,
      vocabularyTranslation: { 0: ["restaurant", ""] },
    });
    expect(candidates.map((c) => c.word)).toEqual(["餐廳"]);
  });
});

describe("buildClozePatchUpdates", () => {
  const candidates = [
    { frameIndex: 0, wordIndex: 0, word: "餐廳", translation: "restaurant", existing: [] },
    { frameIndex: 0, wordIndex: 1, word: "吃", translation: "to eat", existing: ["s1"] },
  ];

  it("maps AI results back to frame/word indices by word text", () => {
    const updates = buildClozePatchUpdates(candidates, [
      { word: "餐廳", sentence: "我在餐廳吃飯。", distractors: ["教室", "公園"] },
      { word: "吃", sentence: "我要吃飯。", distractors: ["喝"] },
    ]);
    expect(updates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        candidates: [{ sentence: "我在餐廳吃飯。", distractors: ["教室", "公園"] }],
      },
      {
        frameIndex: 0,
        wordIndex: 1,
        candidates: [{ sentence: "我要吃飯。", distractors: ["喝"] }],
      },
    ]);
  });

  it("drops candidates the AI returned nothing for", () => {
    const updates = buildClozePatchUpdates(candidates, [
      { word: "餐廳", sentence: "我在餐廳吃飯。", distractors: ["教室"] },
    ]);
    expect(updates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        candidates: [{ sentence: "我在餐廳吃飯。", distractors: ["教室"] }],
      },
    ]);
  });

  it("returns an empty array when the AI returned nothing for any candidate", () => {
    expect(buildClozePatchUpdates(candidates, [])).toEqual([]);
  });
});

