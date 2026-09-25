import { describe, expect, it } from "vitest";
import { analyzeSpeakingResult } from "./analysis";
import type { PraatMetrics } from "../../story-recorder/StoryRecorder";

function metrics(overrides: Partial<PraatMetrics> = {}): PraatMetrics {
  return {
    transcription: "",
    pitch_contour: [],
    word_prosody: [],
    detected_tone: 1,
    tone_accuracy: 90,
    formants: {},
    speech_rate: 3,
    fluency_score: 80,
    pitch_statistics: {},
    feedback: "",
    ...overrides,
  } as unknown as PraatMetrics;
}

describe("analyzeSpeakingResult — verdict", () => {
  it("is 'ready' once accepted with nothing left to fix or practice", () => {
    const result = analyzeSpeakingResult({
      modelSentence: "你好",
      praatMetrics: metrics({ transcription: "你好", content_match: true } as never),
      ready: true,
      selectedImageIndex: 0,
    });

    expect(result.verdict).toBe("ready");
    expect(result.hasFix).toBe(false);
    expect(result.hasPractice).toBe(false);
    expect(result.steps).toEqual(["selfEval", "overview"]);
  });

  it("is 'pronounce' when accepted but a word failed pronunciation", () => {
    const result = analyzeSpeakingResult({
      modelSentence: "你好",
      praatMetrics: metrics({
        transcription: "你好",
        content_match: true,
        word_prosody: [
          {
            token: "你好",
            index: 0,
            start_time: 0,
            end_time: 1,
            pitch_contour: [],
            mean_pitch: 200,
            pitch_range: 30,
            start_pitch: 210,
            end_pitch: 190,
            contour_shape: "falling",
            feedback: "",
            passed: false,
            judged: true,
            tone_accuracy: 40,
            shape_accuracy: 40,
          } as never,
        ],
      }),
      ready: false,
      selectedImageIndex: 0,
    });

    expect(result.verdict).toBe("pronounce");
    expect(result.hasFix).toBe(false);
    expect(result.hasPractice).toBe(true);
    expect(result.steps).toEqual(["overview", "practice"]);
  });

  it("is 'vocab' when required vocabulary is missing from the transcript", () => {
    const result = analyzeSpeakingResult({
      modelSentence: "你好",
      praatMetrics: metrics({
        transcription: "你好",
        content_match: true,
        ai_feedback: {
          provider: "test",
          vocabulary_coverage: { score: 0, used: [], missing: ["謝謝"], feedback: "" },
          coherence: { score: 0, feedback: "", corrections: [] },
          pronunciation_note: { score: 0, feedback: "" },
          improved_version: "",
          practice_prompt: "",
        } as never,
      }),
      ready: false,
      selectedImageIndex: 0,
    });

    expect(result.verdict).toBe("vocab");
    expect(result.hasFix).toBe(true);
    expect(result.hasPhrasePractice).toBe(true);
    expect(result.steps).toEqual(["overview", "fix", "practice"]);
  });

  it("is 'join' on a multi-part script that isn't ready yet, once every part matches", () => {
    const result = analyzeSpeakingResult({
      modelSentence: "你好，很好",
      praatMetrics: metrics({ transcription: "你好很好", content_match: true } as never),
      ready: false,
      selectedImageIndex: 0,
    });

    expect(result.isChunked).toBe(true);
    expect(result.verdict).toBe("join");
    expect(result.hasScriptMismatch).toBe(false);
  });

  it("is 'meaning' whenever content_match is explicitly false, regardless of pronunciation", () => {
    const result = analyzeSpeakingResult({
      modelSentence: "你好",
      praatMetrics: metrics({ transcription: "再見", content_match: false } as never),
      ready: false,
      selectedImageIndex: 0,
    });

    expect(result.verdict).toBe("meaning");
    expect(result.hasFix).toBe(true);
  });

  it("includes the self-eval step only when the attempt is ready", () => {
    const notReady = analyzeSpeakingResult({
      modelSentence: "你好",
      praatMetrics: metrics({ transcription: "你好" }),
      ready: false,
      selectedImageIndex: 0,
    });
    const ready = analyzeSpeakingResult({
      modelSentence: "你好",
      praatMetrics: metrics({ transcription: "你好" }),
      ready: true,
      selectedImageIndex: 0,
    });

    expect(notReady.steps).not.toContain("selfEval");
    expect(ready.steps).toContain("selfEval");
  });
});
