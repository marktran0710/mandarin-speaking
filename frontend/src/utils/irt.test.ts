import { describe, expect, it } from "vitest";
import { calibrateItems, estimateAbility, irtProbability, selectNextItem } from "./irt";

const items = [
  { itemId: "easy", prompt: "A", targetTonePattern: "T1", difficulty: -1, discrimination: 1 },
  { itemId: "mid", prompt: "B", targetTonePattern: "T2", difficulty: 0, discrimination: 1 },
  { itemId: "hard", prompt: "C", targetTonePattern: "T4", difficulty: 1, discrimination: 1 },
];

describe("IRT question bank", () => {
  it("selects an item near current ability", () => {
    expect(selectNextItem(items, 0)?.itemId).toBe("mid");
  });

  it("moves ability up after correct responses", () => {
    expect(estimateAbility(items.map((item) => ({ item, correct: true })))).toBeGreaterThan(0);
    expect(irtProbability(1, items[2])).toBeCloseTo(0.5);
  });

  it("flags under-calibrated items instead of silently publishing them", () => {
    const result = calibrateItems(items, [{ studentId: "s1", itemId: "mid", correct: true }]);
    expect(result[1].usable).toBe(false);
    expect(result[1].flags).toContain("small_sample");
  });
});
