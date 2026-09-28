import { beforeEach, describe, expect, it } from "vitest";
import {
  TIER_CONFIGS,
  attemptEarnsStar,
  starsFromAttempts,
  isTierUnlocked,
  practiceUnlocked,
  latestRoundScores,
  loadLocalStars,
  roundScore,
  recordLocalStars,
} from "@entities/vocabulary";

describe("TIER_CONFIGS", () => {
  it("defines the three rounds; only Use It is timed", () => {
    expect(TIER_CONFIGS.tier1).toEqual({ tier: 1, mode: "tier1", timeLimitMs: null });
    expect(TIER_CONFIGS.tier2).toEqual({ tier: 2, mode: "tier2", timeLimitMs: null });
    expect(TIER_CONFIGS.tier3).toEqual({ tier: 3, mode: "tier3", timeLimitMs: 150_000 });
  });
});

describe("attemptEarnsStar", () => {
  it("earns the round for any finished run, whatever the accuracy", () => {
    expect(attemptEarnsStar("tier1", 14, 20)).toBe(1);
    expect(attemptEarnsStar("tier1", 0, 20)).toBe(1);
    expect(attemptEarnsStar("tier2", 3, 22)).toBe(2);
    expect(attemptEarnsStar("tier3", 1, 25)).toBe(3);
  });

  it("returns null for an empty run", () => {
    expect(attemptEarnsStar("tier1", 0, 0)).toBeNull();
    expect(attemptEarnsStar("tier1", 5)).toBeNull();
  });

  it("returns null for non-tier modes (speed, strikes, weak_words, null)", () => {
    expect(attemptEarnsStar("speed", 20, 20)).toBeNull();
    expect(attemptEarnsStar("strikes", 20, 20)).toBeNull();
    expect(attemptEarnsStar("weak_words", 20, 20)).toBeNull();
    expect(attemptEarnsStar(null, 20, 20)).toBeNull();
  });
});

describe("roundScore", () => {
  it("scales first-try correct answers to 0–100", () => {
    expect(roundScore(7, 10)).toBe(70);
    expect(roundScore(2, 3)).toBe(67);
    expect(roundScore(0, 12)).toBe(0);
    expect(roundScore(12, 12)).toBe(100);
    expect(roundScore(0, 0)).toBe(0);
  });
});

describe("latestRoundScores", () => {
  it("reports each round's most recent finished attempt, not its best", () => {
    expect(
      latestRoundScores([
        { mode: "tier1", correctCount: 9, totalQuestions: 10, completedAt: "2026-09-01T00:00:00.000Z" },
        { mode: "tier1", correctCount: 4, totalQuestions: 10, completedAt: "2026-09-02T00:00:00.000Z" },
        { mode: "tier2", correctCount: 5, totalQuestions: 10, completedAt: "2026-09-01T00:00:00.000Z" },
        { mode: "weak_words", correctCount: 3, totalQuestions: 3, completedAt: "2026-09-03T00:00:00.000Z" },
      ]),
    ).toEqual({ tier1: 40, tier2: 50 });
  });
});

describe("starsFromAttempts", () => {
  it("returns 0 with no attempts", () => {
    expect(starsFromAttempts([])).toBe(0);
  });

  it("counts contiguous finished rounds", () => {
    expect(
      starsFromAttempts([
        { mode: "tier1", correctCount: 2, totalQuestions: 20 },
        { mode: "tier2", correctCount: 0, totalQuestions: 22 },
      ]),
    ).toBe(2);
  });

  it("does not let a lone tier 3 run unlock the ladder", () => {
    expect(starsFromAttempts([{ mode: "tier3", correctCount: 25, totalQuestions: 25 }])).toBe(0);
  });

  it("does not skip tier 2 when tiers 1 and 3 were finished", () => {
    expect(
      starsFromAttempts([
        { mode: "tier1", correctCount: 14, totalQuestions: 20 },
        { mode: "tier3", correctCount: 22, totalQuestions: 25 },
      ]),
    ).toBe(1);
  });

  it("accepts all three finished rounds regardless of attempt order", () => {
    expect(
      starsFromAttempts([
        { mode: "tier3", correctCount: 2, totalQuestions: 25 },
        { mode: "tier1", correctCount: 1, totalQuestions: 20 },
        { mode: "tier2", correctCount: 0, totalQuestions: 22 },
      ]),
    ).toBe(3);
  });

  it("ignores legacy modes and empty runs", () => {
    expect(
      starsFromAttempts([
        { mode: "speed", correctCount: 20, totalQuestions: 20 },
        { mode: "tier1", correctCount: 0, totalQuestions: 0 },
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
    const { starsByStory } = await import("@entities/vocabulary");
    expect(
      starsByStory([
        { storyId: "a", mode: "tier1", correctCount: 15, totalQuestions: 20 },
        { storyId: "a", mode: "tier2", correctCount: 19, totalQuestions: 22 },
        { storyId: "b", mode: "tier2", correctCount: 3, totalQuestions: 20 },
        { storyId: "c", mode: "speed", correctCount: 20, totalQuestions: 20 },
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
    const { starsByStory } = await import("@entities/vocabulary");
    expect(
      starsByStory([
        { storyId: "skipped", mode: "tier3", correctCount: 25, totalQuestions: 25 },
        { storyId: "partial", mode: "tier1", correctCount: 15, totalQuestions: 20 },
        { storyId: "partial", mode: "tier3", correctCount: 25, totalQuestions: 25 },
      ]),
    ).toEqual({ skipped: 0, partial: 1 });
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
