import { describe, expect, it } from "vitest";
import { modelSimilarity } from "./modelSimilarity";
import type { ModelOverlay } from "./modelOverlay";

// Two words: a fall (0.0–0.5 s) then a rise (0.5–1.0 s).
const overlay: ModelOverlay = {
  status: "ok",
  segments: [
    { wordIndex: 0, points: [[0, 200], [0.25, 170], [0.5, 140]] },
    { wordIndex: 1, points: [[0.5, 140], [0.75, 170], [1.0, 210]] },
  ],
};

function sample(fn: (t: number) => number, step = 0.01): Array<[number, number]> {
  const points: Array<[number, number]> = [];
  for (let t = 0; t <= 1.0001; t += step) points.push([Number(t.toFixed(3)), fn(t)]);
  return points;
}

// Same shape as the model but in a much lower voice.
const lowVoiceSameShape = sample((t) => (t < 0.5 ? 100 - 30 * t * 2 : 70 + 35 * (t - 0.5) * 2) );

describe("modelSimilarity (mean per-word Pearson r)", () => {
  it("scores the same shape highly regardless of voice pitch", () => {
    const result = modelSimilarity(overlay, lowVoiceSameShape);
    expect(result).not.toBeNull();
    expect(result!.r).toBeGreaterThan(0.95);
    expect(result!.score).toBeGreaterThan(95);
    expect(result!.wordsCompared).toBe(2);
  });

  it("survives pitch-tracker octave jumps", () => {
    const withJumps = lowVoiceSameShape.map(([t, hz], i): [number, number] => [t, i % 17 === 0 ? hz * 2 : hz]);
    expect(modelSimilarity(overlay, withJumps)!.score).toBeGreaterThan(90);
  });

  it("scores an inverted shape as 0", () => {
    const inverted = sample((t) => (t < 0.5 ? 100 + 30 * t * 2 : 130 - 35 * (t - 0.5) * 2));
    const result = modelSimilarity(overlay, inverted);
    expect(result!.r).toBeLessThan(0);
    expect(result!.score).toBe(0);
  });

  it("scores a completely flat attempt as 0", () => {
    const result = modelSimilarity(overlay, sample(() => 120));
    expect(result!.score).toBe(0);
  });

  it("returns null without a lined-up model voice", () => {
    expect(modelSimilarity({ status: "missing" }, lowVoiceSameShape)).toBeNull();
    expect(modelSimilarity({ status: "mismatch" }, lowVoiceSameShape)).toBeNull();
  });

  it("returns null when too little of the sentence was voiced", () => {
    // Voiced only for the first 0.2 s: not even one word has enough pitch.
    expect(modelSimilarity(overlay, lowVoiceSameShape.filter(([t]) => t < 0.2))).toBeNull();
  });
});
