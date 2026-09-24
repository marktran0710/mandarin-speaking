import { describe, expect, it } from "vitest";
import {
  attemptHistoryFromAudioRecords,
  sceneSubmissionFromAudioRecord,
  vocabTooltip,
} from "./StoryRecorder";

describe("vocabTooltip", () => {
  it("combines part of speech and translation", () => {
    expect(vocabTooltip("N", "restaurant")).toBe("(N) restaurant");
  });

  it("handles either metadata field independently", () => {
    expect(vocabTooltip("N", undefined)).toBe("(N)");
    expect(vocabTooltip(undefined, "restaurant")).toBe("restaurant");
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

  it("rebuilds a scene snapshot from the latest audio record", () => {
    expect(sceneSubmissionFromAudioRecord({
      id: "latest", timestamp: "1", duration: 1, transcription: "Saved transcript", model: "",
      imageIndex: 0, imageUrl: "scene.png", audioUrl: "/uploads/latest.wav",
      praatMetrics: { tone_accuracy: 82, fluency_score: 71, ai_feedback: { vocabulary_coverage: { score: 100, used: ["word"], missing: [], feedback: "" } } },
    })).toMatchObject({ sceneIndex: 0, transcription: "Saved transcript", vocabScore: 100, toneAccuracy: 82, fluencyScore: 71, audioUrl: "/uploads/latest.wav" });
  });
});
