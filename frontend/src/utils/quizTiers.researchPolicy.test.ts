import { afterEach, describe, expect, it, vi } from "vitest";

const { getCachedResearchContext } = vi.hoisted(() => ({ getCachedResearchContext: vi.fn() }));
vi.mock("./researchContext", () => ({ getCachedResearchContext }));

import { attemptEarnsStar, effectiveTimeLimitMs, starsFromAttempts } from "./quizTiers";

function mockPolicy(coreCompletionPolicy: "production_accuracy" | "research_coverage") {
  getCachedResearchContext.mockReturnValue({
    active: coreCompletionPolicy === "research_coverage",
    coreCompletionPolicy,
    practiceAvailable: false,
    reviewAvailable: false,
    probeAvailable: false,
  });
}

describe("attemptEarnsStar under research_coverage policy", () => {
  afterEach(() => vi.clearAllMocks());

  it("earns the tier's star for a completed round regardless of accuracy", () => {
    mockPolicy("research_coverage");
    // Only 2/20 correct - would fail production's 70% threshold outright.
    expect(attemptEarnsStar("tier1", 2, 20)).toBe(1);
    expect(attemptEarnsStar("tier3", 0, 25)).toBe(3);
  });

  it("still returns null for a non-tier mode or zero-length round", () => {
    mockPolicy("research_coverage");
    expect(attemptEarnsStar("weak_words", 5, 5)).toBeNull();
    expect(attemptEarnsStar("tier1", 0, 0)).toBeNull();
    expect(attemptEarnsStar("tier1", 0, undefined)).toBeNull();
  });

  it("still requires the full ladder in order via starsFromAttempts (tier3 alone does not unlock)", () => {
    mockPolicy("research_coverage");
    expect(
      starsFromAttempts([{ mode: "tier3", correctCount: 0, totalQuestions: 25 }]),
    ).toBe(0);
    expect(
      starsFromAttempts([
        { mode: "tier1", correctCount: 1, totalQuestions: 20 },
        { mode: "tier2", correctCount: 1, totalQuestions: 22 },
        { mode: "tier3", correctCount: 1, totalQuestions: 25 },
      ]),
    ).toBe(3);
  });
});

describe("attemptEarnsStar under production_accuracy policy (default, unchanged)", () => {
  afterEach(() => vi.clearAllMocks());

  it("still gates on the accuracy threshold", () => {
    mockPolicy("production_accuracy");
    expect(attemptEarnsStar("tier1", 2, 20)).toBeNull(); // 10% < 70%
    expect(attemptEarnsStar("tier1", 14, 20)).toBe(1); // 70% passes
  });
});

describe("effectiveTimeLimitMs", () => {
  afterEach(() => vi.clearAllMocks());

  it("production keeps tier3's configured time limit", () => {
    mockPolicy("production_accuracy");
    expect(effectiveTimeLimitMs("tier3")).toBe(150_000);
    expect(effectiveTimeLimitMs("tier1")).toBeNull();
  });

  it("research disables the timer for every tier, including tier3", () => {
    mockPolicy("research_coverage");
    expect(effectiveTimeLimitMs("tier3")).toBeNull();
    expect(effectiveTimeLimitMs("tier1")).toBeNull();
  });
});
