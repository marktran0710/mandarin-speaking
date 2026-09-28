import { describe, expect, it } from "vitest";
import { buildModelOverlay, parseSentenceModelContour, type SentenceModelContour } from "./modelOverlay";

const contour: SentenceModelContour = {
  text: "我想喝水。",
  tokens: [
    { token: "我", points: [[0, -2], [1, -4]] },
    { token: "想", points: [[0, -5], [0.5, -6], [1, -3]] },
    { token: "喝水", points: [[0, 4], [1, 0]] },
  ],
};

const words = [
  { token: "我", index: 0, start_time: 0.1, end_time: 0.4 },
  { token: "想", index: 1, start_time: 0.4, end_time: 0.9 },
  { token: "喝水", index: 2, start_time: 0.9, end_time: 1.9 },
];

// Student voice centred on 110 Hz — well below any teacher recording.
const pitchContour: Array<[number, number]> = [[0.2, 100], [0.6, 110], [1.2, 120], [1.5, 0]];

describe("buildModelOverlay", () => {
  it("stretches each model token onto the student's own word span, anchored at the student's median pitch", () => {
    const overlay = buildModelOverlay({ contour, targetScript: "我想喝水。", transcript: "我想喝水", words, pitchContour });

    expect(overlay.status).toBe("ok");
    if (overlay.status !== "ok") return;
    expect(overlay.segments.map((segment) => segment.wordIndex)).toEqual([0, 1, 2]);
    const [first, , last] = overlay.segments;
    expect(first.points[0][0]).toBeCloseTo(0.1);
    expect(first.points[1][0]).toBeCloseTo(0.4);
    expect(last.points[1][0]).toBeCloseTo(1.9);
    // 0 semitones = the student's median (110 Hz); +12 would be one octave up.
    expect(last.points[1][1]).toBeCloseTo(110);
    expect(last.points[0][1]).toBeCloseTo(110 * 2 ** (4 / 12));
  });

  it("reports a missing model voice when the scene has no contour", () => {
    expect(buildModelOverlay({ contour: null, targetScript: "我想喝水", words, pitchContour }).status).toBe("missing");
  });

  it("treats a contour recorded for a different script as missing", () => {
    expect(buildModelOverlay({ contour, targetScript: "我不喝水", words, pitchContour }).status).toBe("missing");
  });

  it("hides the model line when the learner said a different sentence", () => {
    const overlay = buildModelOverlay({ contour, targetScript: "我想喝水", transcript: "你好嗎", words, pitchContour });
    expect(overlay.status).toBe("mismatch");
  });

  it("hides the model line when the attempt was tokenized from other text", () => {
    const otherWords = [{ token: "你好", index: 0, start_time: 0, end_time: 1 }];
    const overlay = buildModelOverlay({ contour, targetScript: "我想喝水", words: otherWords, pitchContour });
    expect(overlay.status).toBe("mismatch");
  });
});

describe("parseSentenceModelContour", () => {
  it("parses stored JSON and drops malformed points", () => {
    const parsed = parseSentenceModelContour(JSON.stringify({
      text: "我",
      tokens: [{ token: "我", points: [[0, 1], ["x", 2], [1, 3]] }],
    }));
    expect(parsed).toEqual({ text: "我", tokens: [{ token: "我", points: [[0, 1], [1, 3]] }] });
  });

  it("returns null for empty or invalid values", () => {
    expect(parseSentenceModelContour("")).toBeNull();
    expect(parseSentenceModelContour("{nope")).toBeNull();
    expect(parseSentenceModelContour({ text: "我", tokens: [] })).toBeNull();
  });
});
