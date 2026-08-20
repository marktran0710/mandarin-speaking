import { describe, expect, it } from "vitest";
import { toneTrapVariants } from "./toneTraps";

describe("toneTrapVariants", () => {
  it("generates variants differing in exactly one syllable's tone", () => {
    const variants = toneTrapVariants("hē chá");
    expect(variants).toContain("hé chá");
    expect(variants).toContain("hè chá");
    expect(variants).toContain("hē chà");
    expect(variants).toContain("hē chā");
  });

  it("never includes the original reading", () => {
    expect(toneTrapVariants("hē chá")).not.toContain("hē chá");
    expect(toneTrapVariants("mā")).not.toContain("mā");
  });

  it("works on a single syllable", () => {
    expect(toneTrapVariants("mā")).toEqual(
      expect.arrayContaining(["má", "mǎ", "mà"]),
    );
  });

  it("changes only one syllable per variant", () => {
    for (const variant of toneTrapVariants("nǐ hǎo")) {
      const original = ["nǐ", "hǎo"];
      const changed = variant
        .split(" ")
        .filter((syl, i) => syl !== original[i]).length;
      expect(changed).toBe(1);
    }
  });

  it("handles ü syllables", () => {
    expect(toneTrapVariants("nǚ")).toContain("nǘ");
  });

  it("re-tones neutral (unmarked) syllables too", () => {
    expect(toneTrapVariants("ma")).toContain("mā");
  });

  it("returns [] for non-pinyin input", () => {
    expect(toneTrapVariants("")).toEqual([]);
    expect(toneTrapVariants("喝茶")).toEqual([]);
  });
});
