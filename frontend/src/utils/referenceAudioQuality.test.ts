import { describe, expect, it } from "vitest";
import { assessReferenceAudio } from "./referenceAudioQuality";

const goodEvidence = {
  pitchContour: [[0, 180], [0.2, 190], [0.4, 210]],
  wordProsody: [
    { pitch_contour: [[0, 180], [0.2, 190]], tone_accuracy: 82 },
  ],
  feedbackQuality: {
    status: "review",
    can_score_pronunciation: true,
  },
};

describe("assessReferenceAudio", () => {
  it("accepts a reference with sentence and word-level pitch evidence", () => {
    expect(assessReferenceAudio(goodEvidence)).toMatchObject({
      quality: "usable",
      reason: "enough_pitch_evidence",
    });
  });

  it("does not present an audio file with no measurable contour as a model", () => {
    expect(
      assessReferenceAudio({
        pitchContour: [],
        wordProsody: [],
        feedbackQuality: { can_score_pronunciation: false, status: "retry" },
      }),
    ).toMatchObject({
      quality: "limited",
      reason: "recording_quality_gate",
    });
  });

  it("keeps a low-evidence clip from looking like a full-score example", () => {
    expect(
      assessReferenceAudio({
        pitchContour: [[0, 180]],
        wordProsody: [{ pitch_contour: [], tone_accuracy: 0 }],
      }),
    ).toMatchObject({
      quality: "limited",
      reason: "insufficient_pitch_evidence",
    });
  });
});
