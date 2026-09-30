import { describe, expect, it } from "vitest";
import type { Topic } from "@entities/topic";
import type { PronunciationFeatureSet } from "@shared/api/pronunciation";
import {
  contourSeries,
  evaluationScenes,
  feedbackBadge,
  flagLabel,
  shapeLabel,
  syllableBoundaries,
} from "./model";

const topic = (extra: Partial<Topic>): Topic => ({
  id: "t1", name: "T", images: ["a.png", "b.png", "c.png"], vocabulary: {}, ...extra,
});

describe("evaluationScenes", () => {
  it("lists only scenes that have a teacher recording, with their sentence", () => {
    const scenes = evaluationScenes(topic({
      listenAudioUrls: { 0: "/uploads/a.wav", 2: "/uploads/c.wav" },
      listenScripts: { 0: "友美，妳好", 2: "" },
      suggestedAnswers: { 2: "我很好" },
    }));
    expect(scenes).toEqual([
      { index: 0, text: "友美，妳好" },
      { index: 2, text: "我很好" },
    ]);
  });

  it("is empty when nothing has a recording or there is no topic", () => {
    expect(evaluationScenes(topic({}))).toEqual([]);
    expect(evaluationScenes(undefined)).toEqual([]);
  });

  it("excludes audio that has no known target sentence", () => {
    expect(evaluationScenes(topic({ listenAudioUrls: { 1: "/uploads/b.wav" } }))).toEqual([]);
  });
});

const features = (): PronunciationFeatureSet => ({
  duration_ms: 1500,
  syllables: [
    { expected: { hanzi: "媽", pinyin: "ma1", expected_tone: 1 }, start_ms: 200, end_ms: 500, direction: "flat", f0_points: [[200, 0], [350, 0.5], [490, 0]] },
    { expected: { hanzi: "罵", pinyin: "ma4", expected_tone: 4 }, start_ms: 500, end_ms: 800, direction: "fall", f0_points: [[500, 4], [800, -4]] },
  ],
});

describe("contourSeries", () => {
  it("spreads the utterance over 0..1 so different speaking speeds overlay", () => {
    const series = contourSeries(features());
    expect(series[0].x).toBeCloseTo(0, 5);
    expect(series[series.length - 1].x).toBeCloseTo(1, 5);
    expect(series.map((p) => p.y)).toEqual([0, 0.5, 0, 4, -4]);
  });

  it("is empty without features", () => {
    expect(contourSeries(null)).toEqual([]);
    expect(contourSeries({ duration_ms: 0, syllables: [] })).toEqual([]);
  });
});

describe("syllableBoundaries", () => {
  it("marks where each syllable starts on the same 0..1 axis", () => {
    const marks = syllableBoundaries(features());
    expect(marks).toHaveLength(2);
    expect(marks[0].x).toBe(0);
    expect(marks[1].x).toBeCloseTo(0.5, 5);
    expect(marks[1].label).toBe("罵");
  });
});

describe("labels", () => {
  it("turns a flag code into a plain sentence", () => {
    expect(flagLabel("tone_contour_too_flat")).toMatch(/flat/i);
    expect(flagLabel("something_new")).toBe("something new");
  });

  it("names pitch shapes", () => {
    expect(shapeLabel("fall")).toBe("falling");
    expect(shapeLabel("unvoiced")).toBe("no pitch");
  });

  it("says whether feedback came from the model or fell back", () => {
    expect(feedbackBadge({ summary: "", focus_words: [], practice_tip: "", source: "llm", model: "gpt-6-luna" }))
      .toEqual({ label: "gpt-6-luna", tone: "llm" });
    expect(feedbackBadge({ summary: "", focus_words: [], practice_tip: "", source: "local", fallback_reason: "llm_timeout" }))
      .toEqual({ label: "local feedback (llm_timeout)", tone: "local" });
    expect(feedbackBadge({ summary: "", focus_words: [], practice_tip: "", source: "local" }))
      .toEqual({ label: "local feedback", tone: "local" });
  });
});
