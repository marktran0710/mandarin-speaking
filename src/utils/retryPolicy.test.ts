import { describe, expect, it } from "vitest";
import { MAX_AUTOMATIC_RETRIES, canAlwaysProgress, progressionOutcome, shouldOfferRetry } from "./retryPolicy";

// PART 18 safety test #6: CHECK_THIS_TONE (NEEDS_PRACTICE) cannot cause
// endless retries -- at most MAX_AUTOMATIC_RETRIES (1) offer, ever, and
// progression is never blocked regardless of how many retries were used.
describe("shouldOfferRetry", () => {
  it("offers a retry for CHECK_THIS_TONE only before the cap is reached", () => {
    expect(shouldOfferRetry("NEEDS_PRACTICE", 0)).toBe(true);
  });

  it("never offers a second retry once the cap (1) is reached", () => {
    expect(shouldOfferRetry("NEEDS_PRACTICE", 1)).toBe(false);
    expect(shouldOfferRetry("NEEDS_PRACTICE", 2)).toBe(false);
    expect(shouldOfferRetry("NEEDS_PRACTICE", 100)).toBe(false);
  });

  it("never offers a retry for ACCEPT or UNCERTAIN, at any retry count", () => {
    for (const retriesUsed of [0, 1, 2]) {
      expect(shouldOfferRetry("ACCEPT", retriesUsed)).toBe(false);
      expect(shouldOfferRetry("UNCERTAIN", retriesUsed)).toBe(false);
    }
  });

  it("never offers a retry when there is no state at all", () => {
    expect(shouldOfferRetry(null, 0)).toBe(false);
  });

  it("the cap is exactly one, not a tunable that could silently grow", () => {
    expect(MAX_AUTOMATIC_RETRIES).toBe(1);
  });
});

describe("canAlwaysProgress", () => {
  it("is true for every assistive state -- this policy never hard-blocks progression", () => {
    expect(canAlwaysProgress("ACCEPT")).toBe(true);
    expect(canAlwaysProgress("UNCERTAIN")).toBe(true);
    expect(canAlwaysProgress("NEEDS_PRACTICE")).toBe(true);
    expect(canAlwaysProgress(null)).toBe(true);
  });
});

describe("progressionOutcome", () => {
  it("is never a blocked/abandoned-by-policy outcome", () => {
    const outcomes = [
      progressionOutcome("NEEDS_PRACTICE", 0),
      progressionOutcome("NEEDS_PRACTICE", 1),
      progressionOutcome("ACCEPT", 0),
      progressionOutcome("UNCERTAIN", 0),
      progressionOutcome(null, 0),
    ];
    for (const outcome of outcomes) {
      expect(["continued_immediately", "continued_after_retry", "continued_after_cap"]).toContain(outcome);
    }
  });

  it("labels the capped case distinctly from an immediate continue", () => {
    expect(progressionOutcome("NEEDS_PRACTICE", 0)).toBe("continued_immediately");
    expect(progressionOutcome("NEEDS_PRACTICE", 1)).toBe("continued_after_cap");
  });
});
