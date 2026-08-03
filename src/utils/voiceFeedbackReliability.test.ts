import { describe, expect, it } from "vitest";
import { assessVoiceFeedbackReliability } from "./voiceFeedbackReliability";

const scoredWord = {
  tone_accuracy: 78,
  pitch_contour: [
    [0, 180],
    [0.1, 185],
    [0.2, 190],
    [0.3, 195],
  ] as Array<[number, number]>,
};

describe("assessVoiceFeedbackReliability", () => {
  it("rejects a score when independent content verification mismatches", () => {
    expect(
      assessVoiceFeedbackReliability({
        contentMatch: false,
        wordProsody: [scoredWord],
      }),
    ).toMatchObject({
      level: "retry",
      canCountForProgress: false,
      reason: "content-mismatch",
    });
  });

  it("asks for a retake when pitch evidence is too sparse", () => {
    expect(
      assessVoiceFeedbackReliability({
        contentMatch: true,
        wordProsody: [{ ...scoredWord, pitch_contour: [[0, 180]] }],
      }).level,
    ).toBe("retry");
  });

  it("labels measured but unverified feedback as an estimate", () => {
    expect(
      assessVoiceFeedbackReliability({
        contentMatch: null,
        wordProsody: [scoredWord],
      }),
    ).toMatchObject({
      level: "estimate",
      canCountForProgress: false,
    });
  });

  it("uses a non-numeric checked label instead of inventing confidence", () => {
    expect(
      assessVoiceFeedbackReliability({
        contentMatch: true,
        wordProsody: [scoredWord],
      }),
    ).toMatchObject({
      level: "reliable",
      canCountForProgress: true,
      reason: "checked",
    });
  });

  it("maps the backend limited status to an estimate", () => {
    expect(
      assessVoiceFeedbackReliability({
        feedbackQuality: {
          status: "limited",
          can_score_pronunciation: true,
          can_score_content: true,
          reasons: ["content_check_unavailable"],
        },
        wordProsody: [scoredWord],
      }).level,
    ).toBe("estimate");
  });

  it("honors an explicit backend pronunciation gate even with scored-looking data", () => {
    expect(
      assessVoiceFeedbackReliability({
        feedbackQuality: {
          status: "retry",
          can_score_pronunciation: false,
          can_score_content: false,
          reason_codes: ["insufficient_voiced_audio"],
        },
        contentMatch: true,
        wordProsody: [scoredWord],
      }),
    ).toMatchObject({
      level: "retry",
      canCountForProgress: false,
    });
  });
});
