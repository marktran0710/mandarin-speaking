import { beforeEach, describe, expect, it } from "vitest";
import {
  TIER_CONFIGS,
  attemptEarnsStar,
  starsFromAttempts,
  isTierUnlocked,
  practiceUnlocked,
  nextStarGap,
  loadLocalStars,
  recordLocalStars,
} from "./quizTiers";

describe("TIER_CONFIGS", () => {
  it("defines the three star tiers with agreed question counts and thresholds", () => {
    expect(TIER_CONFIGS.tier1).toMatchObject({
      tier: 1,
      questionCount: 20,
      passCount: 14,
      timeLimitMs: null,
    });
    expect(TIER_CONFIGS.tier2).toMatchObject({
      tier: 2,
      questionCount: 22,
      passCount: 18,
      timeLimitMs: null,
    });
    expect(TIER_CONFIGS.tier3).toMatchObject({
      tier: 3,
      questionCount: 25,
      passCount: 22,
      timeLimitMs: 150_000,
    });
  });
});

describe("attemptEarnsStar", () => {
  it("returns the tier number when the attempt meets its pass threshold", () => {
    expect(attemptEarnsStar("tier1", 14)).toBe(1);
    expect(attemptEarnsStar("tier2", 18)).toBe(2);
    expect(attemptEarnsStar("tier3", 25)).toBe(3);
  });

  it("returns null when the attempt is below the threshold", () => {
    expect(attemptEarnsStar("tier1", 13)).toBeNull();
    expect(attemptEarnsStar("tier3", 21)).toBeNull();
  });

  it("preserves the pass ratio when a leak-free session has fewer distinct concepts", () => {
    expect(attemptEarnsStar("tier1", 4, 5)).toBe(1);
    expect(attemptEarnsStar("tier1", 3, 5)).toBeNull();
    expect(attemptEarnsStar("tier2", 5, 5)).toBe(2);
  });

  it("returns null for non-tier modes (speed, strikes, weak_words, null)", () => {
    expect(attemptEarnsStar("speed", 20)).toBeNull();
    expect(attemptEarnsStar("strikes", 20)).toBeNull();
    expect(attemptEarnsStar("weak_words", 20)).toBeNull();
    expect(attemptEarnsStar(null, 20)).toBeNull();
  });
});

describe("starsFromAttempts", () => {
  it("returns 0 with no attempts", () => {
    expect(starsFromAttempts([])).toBe(0);
  });

  it("returns the highest contiguous tier any attempt passed", () => {
    expect(
      starsFromAttempts([
        { mode: "tier1", correctCount: 15 },
        { mode: "tier2", correctCount: 19 },
        { mode: "tier2", correctCount: 3 },
      ]),
    ).toBe(2);
  });

  it("does not let a lone tier 3 pass unlock the ladder", () => {
    expect(starsFromAttempts([{ mode: "tier3", correctCount: 25 }])).toBe(0);
  });

  it("does not skip tier 2 when tier 1 and tier 3 pass", () => {
    expect(
      starsFromAttempts([
        { mode: "tier1", correctCount: 14 },
        { mode: "tier3", correctCount: 22 },
      ]),
    ).toBe(1);
  });

  it("accepts all three passed tiers regardless of attempt order", () => {
    expect(
      starsFromAttempts([
        { mode: "tier3", correctCount: 22 },
        { mode: "tier1", correctCount: 14 },
        { mode: "tier2", correctCount: 18 },
      ]),
    ).toBe(3);
  });

  it("does not count failed tiers toward the contiguous proof", () => {
    expect(
      starsFromAttempts([
        { mode: "tier1", correctCount: 14 },
        { mode: "tier2", correctCount: 17 },
        { mode: "tier3", correctCount: 25 },
      ]),
    ).toBe(1);
  });

  it("ignores failing attempts and legacy modes", () => {
    expect(
      starsFromAttempts([
        { mode: "speed", correctCount: 20 },
        { mode: "tier1", correctCount: 10 },
      ]),
    ).toBe(0);
  });
});

describe("isTierUnlocked", () => {
  it("tier 1 is always unlocked", () => {
    expect(isTierUnlocked(1, 0)).toBe(true);
  });

  it("tiers 2 and 3 need the previous star", () => {
    expect(isTierUnlocked(2, 0)).toBe(false);
    expect(isTierUnlocked(2, 1)).toBe(true);
    expect(isTierUnlocked(3, 1)).toBe(false);
    expect(isTierUnlocked(3, 2)).toBe(true);
  });
});

describe("starsByStory", () => {
  it("derives each story's stars from a mixed attempt history", async () => {
    const { starsByStory } = await import("./quizTiers");
    expect(
      starsByStory([
        { storyId: "a", mode: "tier1", correctCount: 15 },
        { storyId: "a", mode: "tier2", correctCount: 19 },
        { storyId: "b", mode: "tier1", correctCount: 3 },
        { storyId: "c", mode: "speed", correctCount: 20 },
      ]),
    ).toEqual({ a: 2, b: 0, c: 0 });
  });
});

describe("practiceUnlocked", () => {
  it("opens speaking practice only after all three stars", () => {
    expect(practiceUnlocked(0)).toBe(false);
    expect(practiceUnlocked(1)).toBe(false);
    expect(practiceUnlocked(2)).toBe(false);
    expect(practiceUnlocked(3)).toBe(true);
  });

  it("uses contiguous tiers per story", async () => {
    const { starsByStory } = await import("./quizTiers");
    expect(
      starsByStory([
        { storyId: "skipped", mode: "tier3", correctCount: 25 },
        { storyId: "partial", mode: "tier1", correctCount: 15 },
        { storyId: "partial", mode: "tier3", correctCount: 25 },
      ]),
    ).toEqual({ skipped: 0, partial: 1 });
  });
});

describe("nextStarGap", () => {
  it("reports how many more correct answers this run needed to pass", () => {
    expect(nextStarGap("tier2", 16)).toBe(2);
  });

  it("reports 0 when the run passed", () => {
    expect(nextStarGap("tier2", 18)).toBe(0);
    expect(nextStarGap("tier2", 22)).toBe(0);
  });

  it("returns null for non-tier modes", () => {
    expect(nextStarGap("weak_words", 3)).toBeNull();
  });

  it("uses the scaled threshold for a reduced session", () => {
    expect(nextStarGap("tier1", 3, 5)).toBe(1);
  });
});

describe("local star storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns 0 stars for an unknown story", () => {
    expect(loadLocalStars("story-x")).toBe(0);
  });

  it("persists earned stars per story and never lowers them", () => {
    recordLocalStars("story-x", 2);
    expect(loadLocalStars("story-x")).toBe(2);
    recordLocalStars("story-x", 1);
    expect(loadLocalStars("story-x")).toBe(2);
    recordLocalStars("story-x", 3);
    expect(loadLocalStars("story-x")).toBe(3);
  });

  it("keeps stories independent", () => {
    recordLocalStars("story-x", 2);
    expect(loadLocalStars("story-y")).toBe(0);
  });
});
