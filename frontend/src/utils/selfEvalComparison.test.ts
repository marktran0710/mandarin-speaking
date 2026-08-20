import {
  selfEvalLevelsMatch,
  systemContentLevel,
  systemPronunciationLevel,
} from "./selfEvalComparison";
import type { PraatMetrics } from "../components/StoryRecorder";

const metrics = (overrides: Partial<PraatMetrics> = {}): PraatMetrics => ({
  pitch_contour: [],
  detected_tone: 1,
  tone_accuracy: 90,
  formants: {},
  speech_rate: 3,
  fluency_score: 80,
  pitch_statistics: {},
  feedback: "",
  ...overrides,
});

describe("systemContentLevel", () => {
  it("is bad when content_accuracy rejects the attempt", () => {
    const m = metrics({
      ai_feedback: {
        provider: "test",
        vocabulary_coverage: { score: 100, used: [], missing: [], feedback: "" },
        coherence: { score: 0, feedback: "", corrections: [] },
        pronunciation_note: { score: 0, feedback: "" },
        content_accuracy: {
          score: 0,
          feedback: "wrong meaning",
          matched_details: [],
          missed_details: ["x"],
          accepted: false,
          judged: true,
        },
        improved_version: "",
        practice_prompt: "",
      },
    });
    expect(systemContentLevel(m, false)).toBe("bad");
  });

  it("is bad when the script mismatches even if content_accuracy is silent", () => {
    expect(systemContentLevel(metrics(), true)).toBe("bad");
  });

  it("is ok when accepted but vocabulary is still missing", () => {
    const m = metrics({
      ai_feedback: {
        provider: "test",
        vocabulary_coverage: { score: 50, used: ["a"], missing: ["b"], feedback: "" },
        coherence: { score: 0, feedback: "", corrections: [] },
        pronunciation_note: { score: 0, feedback: "" },
        improved_version: "",
        practice_prompt: "",
      },
    });
    expect(systemContentLevel(m, false)).toBe("ok");
  });

  it("is good when accepted with no missing vocabulary and no script mismatch", () => {
    expect(systemContentLevel(metrics(), false)).toBe("good");
  });
});

describe("systemPronunciationLevel", () => {
  it("is good at or above 80", () => {
    expect(systemPronunciationLevel(metrics({ tone_accuracy: 80 }))).toBe("good");
    expect(systemPronunciationLevel(metrics({ tone_accuracy: 95 }))).toBe("good");
  });

  it("is ok between 55 and 79", () => {
    expect(systemPronunciationLevel(metrics({ tone_accuracy: 55 }))).toBe("ok");
    expect(systemPronunciationLevel(metrics({ tone_accuracy: 79 }))).toBe("ok");
  });

  it("is bad below 55", () => {
    expect(systemPronunciationLevel(metrics({ tone_accuracy: 0 }))).toBe("bad");
    expect(systemPronunciationLevel(metrics({ tone_accuracy: 54 }))).toBe("bad");
  });
});

describe("selfEvalLevelsMatch", () => {
  it("is true only when both levels are identical", () => {
    expect(selfEvalLevelsMatch("good", "good")).toBe(true);
    expect(selfEvalLevelsMatch("good", "ok")).toBe(false);
    expect(selfEvalLevelsMatch("bad", "ok")).toBe(false);
  });
});
