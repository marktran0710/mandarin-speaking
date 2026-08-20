import { describe, expect, it, beforeEach } from "vitest";
import {
  getAnalysisVersion,
  saveAnalysisVersion,
  analysisVersionStorageKey,
} from "./analysisVersion";

describe("analysis version persistence", () => {
  beforeEach(() => localStorage.clear());

  it("defaults to Stable V1 and scopes by student", () => {
    expect(getAnalysisVersion("student-a")).toBe("stable_v1");
    saveAnalysisVersion("phoneme_tone_v2", "student-a");
    expect(getAnalysisVersion("student-a")).toBe("phoneme_tone_v2");
    expect(getAnalysisVersion("student-b")).toBe("stable_v1");
    expect(localStorage.getItem(analysisVersionStorageKey("student-a"))).toBe("phoneme_tone_v2");
  });

  it("falls back when storage contains an unknown version", () => {
    localStorage.setItem(analysisVersionStorageKey("student-a"), "removed_v9");
    expect(getAnalysisVersion("student-a")).toBe("stable_v1");
  });
});
