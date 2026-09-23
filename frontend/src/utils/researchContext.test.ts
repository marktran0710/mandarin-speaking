import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getVocabularyResearchContext } = vi.hoisted(() => ({
  getVocabularyResearchContext: vi.fn(),
}));

vi.mock("../services/api/vocabulary-research", () => ({ getVocabularyResearchContext }));

import {
  DEFAULT_RESEARCH_CONTEXT,
  getCachedResearchContext,
  refreshResearchContext,
  resetResearchContextCacheForTests,
} from "./researchContext";

describe("ambient research context cache", () => {
  beforeEach(() => {
    getVocabularyResearchContext.mockReset();
    resetResearchContextCacheForTests();
  });
  afterEach(() => resetResearchContextCacheForTests());

  it("defaults to inactive/production before any fetch - the safe default for every student today", () => {
    expect(getCachedResearchContext()).toEqual(DEFAULT_RESEARCH_CONTEXT);
    expect(getCachedResearchContext().active).toBe(false);
  });

  it("updates the cache after a successful fetch", async () => {
    getVocabularyResearchContext.mockResolvedValue({
      active: true,
      coreCompletionPolicy: "research_coverage",
      practiceAvailable: false,
      reviewAvailable: false,
      probeAvailable: false,
    });

    const result = await refreshResearchContext();

    expect(result.active).toBe(true);
    expect(getCachedResearchContext().active).toBe(true);
    expect(getCachedResearchContext().coreCompletionPolicy).toBe("research_coverage");
  });

  it("falls back to the safe default if the fetch fails - never throws, never leaves a stale active context", async () => {
    getVocabularyResearchContext.mockRejectedValue(new Error("network error"));

    const result = await refreshResearchContext();

    expect(result).toEqual(DEFAULT_RESEARCH_CONTEXT);
    expect(getCachedResearchContext().active).toBe(false);
  });
});
