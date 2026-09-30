import { describe, expect, it } from "vitest";
import { foldOctaveBlocks } from "./pitchCleaning";

const smooth = (n: number, from: number, to: number) => Array.from({ length: n }, (_, i) => from + ((to - from) * i) / (n - 1));

function maxStep(values: number[]) {
  return Math.max(...values.slice(1).map((value, i) => Math.abs(value - values[i])));
}

describe("foldOctaveBlocks", () => {
  it("leaves a clean curve untouched", () => {
    const curve = smooth(20, 4, -8);
    expect(foldOctaveBlocks(curve)).toEqual(curve);
  });

  it("folds a lone half/double-frequency spike back onto the curve", () => {
    const curve = smooth(21, 2, 2);
    const spiked = curve.map((value, i) => (i === 10 ? value + 12 : value));
    const fixed = foldOctaveBlocks(spiked);
    expect(Math.max(...fixed) - Math.min(...fixed)).toBeLessThan(0.5);
  });

  it("folds a long octave-error block that a local median cannot see", () => {
    // A level tone whose last 11 of 24 frames the tracker reports an octave low.
    const truth = Array.from({ length: 24 }, () => 3);
    const broken = truth.map((value, i) => (i >= 13 ? value - 12 : value));
    const fixed = foldOctaveBlocks(broken);
    expect(Math.max(...fixed) - Math.min(...fixed)).toBeLessThan(0.5);
  });

  it("keeps a genuine syllable-boundary reset (~9 semitones) intact", () => {
    const twoSyllables = [...smooth(12, -8, -14), ...smooth(12, -5, 3)];
    expect(foldOctaveBlocks(twoSyllables)).toEqual(twoSyllables);
  });

  it("keeps a steep tone-4 style fall intact", () => {
    const fall = smooth(24, 8, -10);
    expect(foldOctaveBlocks(fall)).toEqual(fall);
  });

  it("does not turn a real 10-semitone excursion at the end into an octave fix", () => {
    const curve = [...smooth(16, 0, 0), ...smooth(8, 10, 10)];
    expect(foldOctaveBlocks(curve)).toEqual(curve);
  });

  it("handles very short input", () => {
    expect(foldOctaveBlocks([])).toEqual([]);
    expect(foldOctaveBlocks([3, 15])).toEqual([3, 15]);
  });

  it("only ever shifts by whole octaves, so the shape is preserved", () => {
    const noisy = smooth(30, 0, -6).map((value, i) => (i % 9 === 4 ? value + 12 : value));
    const fixed = foldOctaveBlocks(noisy);
    fixed.forEach((value, i) => expect(Math.abs(value - noisy[i]) % 12).toBeLessThan(1e-9));
    expect(maxStep(fixed)).toBeLessThan(2);
  });
});
