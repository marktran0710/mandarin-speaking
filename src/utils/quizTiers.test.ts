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

  it("returns the highest tier any attempt passed", () => {
    expect(
      starsFromAttempts([
        { mode: "tier1", correctCount: 15 },
        { mode: "tier2", correctCount: 19 },
        { mode: "tier2", correctCount: 3 },
      ]),
    ).toBe(2);
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

describe("practiceUnlocked", () => {
  it("opens speaking practice at two stars, not one", () => {
    expect(practiceUnlocked(0)).toBe(false);
    expect(practiceUnlocked(1)).toBe(false);
    expect(practiceUnlocked(2)).toBe(true);
    expect(practiceUnlocked(3)).toBe(true);
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
