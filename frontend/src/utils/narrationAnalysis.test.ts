import { describe, expect, it } from "vitest";
import { getAnalysisVisibility, isUsableScore, type AnalysisResult } from "./narrationAnalysis";

const baseResult = (overrides: Partial<AnalysisResult> = {}): AnalysisResult => ({
  transcription: "今天下雨。",
  tone_accuracy: 82,
  fluency_score: 78,
  word_prosody: [{ token: "今", tone_accuracy: 82 }],
  ai_feedback: {
    provider: "test",
    vocabulary_coverage: {
      score: 80,
      used: ["今天"],
      missing: [],
      feedback: "Good coverage",
    },
    content_accuracy: {
      score: 80,
      feedback: "Good match",
      matched_details: ["today"],
      missed_details: [],
      judged: true,
    },
  },
  feedback_quality: {
    status: "reliable",
    can_score_pronunciation: true,
    can_score_content: true,
  },
  content_match: true,
  ...overrides,
});

describe("getAnalysisVisibility", () => {
  it("hides scores when the backend says the attempt needs a retry", () => {
    const visibility = getAnalysisVisibility(
      baseResult({
        feedback_quality: {
          status: "retry",
          can_score_pronunciation: false,
          can_score_content: false,
        },
      }),
    );

    expect(visibility.needsRetry).toBe(true);
    expect(visibility.showPronunciation).toBe(false);
    expect(visibility.showContentScore).toBe(false);
    expect(visibility.showContentDetails).toBe(false);
    expect(visibility.showVocabulary).toBe(false);
  });

  it("keeps pronunciation visible while hiding unverified content", () => {
    const visibility = getAnalysisVisibility(
      baseResult({
        content_match: null,
        ai_feedback: {
          provider: "test",
          content_accuracy: {
            score: 70,
            feedback: "Unverified",
            matched_details: [],
            missed_details: [],
          },
        },
      }),
    );

    expect(visibility.showPronunciation).toBe(true);
    expect(visibility.showContentDetails).toBe(false);
    expect(visibility.showContentScore).toBe(false);
  });

  it("shows the complete result only after content is verified", () => {
    const visibility = getAnalysisVisibility(baseResult());

    expect(visibility.showPronunciation).toBe(true);
    expect(visibility.showContentDetails).toBe(true);
    expect(visibility.showContentScore).toBe(true);
    expect(visibility.showVocabulary).toBe(true);
  });

  it("treats a retry status as authoritative even when numeric fields look complete", () => {
    const visibility = getAnalysisVisibility(
      baseResult({
        ai_feedback: {
          provider: "test",
          practice_prompt: "Try the sentence again.",
        },
        feedback_quality: {
          status: "retry",
          can_score_pronunciation: true,
          can_score_content: true,
        },
      }),
    );

    expect(visibility.needsRetry).toBe(true);
    expect(visibility.showPronunciation).toBe(false);
    expect(visibility.showPracticePrompt).toBe(false);
  });

  it("does not treat NaN or infinity as student-visible scores", () => {
    expect(isUsableScore(82)).toBe(true);
    expect(isUsableScore(Number.NaN)).toBe(false);
    expect(isUsableScore(Number.POSITIVE_INFINITY)).toBe(false);
    expect(isUsableScore("82")).toBe(false);
  });
});
