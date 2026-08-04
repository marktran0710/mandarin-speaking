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

  it("labels the gate as a content mismatch when the backend's own reason says so, even though the caller's lenient contentMatch passed", () => {
    // PhrasePracticeDrill: the backend's independent verify_word ASR pass
    // mismatched content (status can be "review", not "retry", when pitch
    // and transcript were both fine), while the caller's own more lenient
    // ratio-based contentMatch says "close enough". Before this fix, the
    // reason bucket was picked from the caller's contentMatch alone, so this
    // showed "not enough clear pitch evidence" — the wrong explanation for
    // a content-verification slip that has nothing to do with pitch.
    expect(
      assessVoiceFeedbackReliability({
        feedbackQuality: {
          status: "review",
          can_score_pronunciation: false,
          can_score_content: false,
          reason_codes: ["target_content_mismatch"],
        },
        contentMatch: true,
        wordProsody: [scoredWord],
      }),
    ).toMatchObject({
      level: "retry",
      canCountForProgress: false,
      reason: "content-mismatch",
    });
  });

  it("still labels it too-little-audio when the backend's own reason is a pitch/transcript gap", () => {
    expect(
      assessVoiceFeedbackReliability({
        feedbackQuality: {
          status: "retry",
          can_score_pronunciation: false,
          can_score_content: false,
          reason_codes: ["insufficient_voiced_pitch"],
        },
        contentMatch: true,
        wordProsody: [scoredWord],
      }),
    ).toMatchObject({
      level: "retry",
      reason: "too-little-audio",
    });
  });
});
