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

describe("modelSimilarity v2 (shape AND size)", () => {
  // The model's pitch in Hz at time t (two words, see `overlay`).
  const modelHz = (t: number) => (t < 0.5 ? 200 - 120 * t : 140 + 140 * (t - 0.5));
  /** The model's movement scaled by `scale` around its own middle, in a lower voice. */
  const attempt = (scale: number, wobble = 0) =>
    sample((t) => 120 * 2 ** ((scale * Math.log2(modelHz(t) / 170)) + wobble * Math.sin(t * 40)));

  it("gives full credit to the model's shape at the model's size", () => {
    const result = modelSimilarity(overlay, attempt(1))!;
    expect(result.score).toBeGreaterThan(95);
    expect(result.shape).toBeGreaterThan(0.95);
    expect(result.range).toBe(1);
  });

  it("does not let a nearly flat attempt ride on a tiny wobble in the right direction", () => {
    const flatish = attempt(0.08);
    expect(modelSimilarity(overlay, flatish, { algorithm: "legacy" })!.score).toBeGreaterThan(80);
    expect(modelSimilarity(overlay, flatish)!.score).toBeLessThan(15);
  });

  it("is generous to a learner who moves less than the teacher, but not to a half-size fall", () => {
    expect(modelSimilarity(overlay, attempt(0.7))!.score).toBeGreaterThan(85);
    const half = modelSimilarity(overlay, attempt(0.4))!.score;
    expect(half).toBeGreaterThan(30);
    expect(half).toBeLessThan(75);
  });

  it("never penalises moving MORE than the model", () => {
    const wide = modelSimilarity(overlay, attempt(1.8))!.score;
    expect(wide).toBeGreaterThanOrEqual(modelSimilarity(overlay, attempt(1))!.score - 2);
  });

  it("is not thrown by a half-frequency error that lasts many frames", () => {
    const clean = attempt(1);
    const broken = clean.map(([t, hz]): [number, number] => [t, t > 0.62 && t < 0.95 ? hz / 2 : hz]);
    expect(modelSimilarity(overlay, broken)!.score).toBeGreaterThan(85);
    expect(modelSimilarity(overlay, broken, { algorithm: "legacy" })!.score).toBeLessThan(85);
  });

  it("reports no shape/range breakdown for the legacy algorithm and keeps the flat/inverted floors", () => {
    const legacy = modelSimilarity(overlay, attempt(1), { algorithm: "legacy" })!;
    expect(legacy.shape).toBeUndefined();
    expect(legacy.range).toBeUndefined();
    const inverted = sample((t) => 120 * 2 ** (-Math.log2(modelHz(t) / 170)));
    expect(modelSimilarity(overlay, inverted)!.score).toBe(0);
  });

  it("lets the parameters be moved without touching the code", () => {
    const strict = modelSimilarity(overlay, attempt(0.7), { params: { rhoFull: 0.9 } })!;
    expect(strict.score).toBeLessThan(modelSimilarity(overlay, attempt(0.7))!.score);
  });
});
