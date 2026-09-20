import { describe, expect, it } from "vitest";
import { pickStripMessage } from "./journeyStrip";

// Attempt shape mirrors VocabQuizAttempt fields the picker needs.
const attempt = (
  storyId: string,
  mode: string,
  correctCount: number,
  completedAt: string,
) => ({ storyId, mode, correctCount, totalQuestions: mode === "tier1" ? 20 : mode === "tier2" ? 22 : 25, completedAt });

describe("pickStripMessage", () => {
  it("welcomes a brand-new student with no attempts", () => {
    const msg = pickStripMessage([]);
    expect(msg.kind).toBe("welcome");
  });

  it("points at the story whose latest attempt was a near-miss (gap <= 2)", () => {
    const msg = pickStripMessage([
      attempt("s-market", "tier2", 17, "2026-07-23T10:00:00Z"), // gap 2
      attempt("s-tea", "tier1", 20, "2026-07-22T10:00:00Z"),
    ]);
    expect(msg).toMatchObject({ kind: "near_miss", storyId: "s-market", gap: 2 });
  });

  it("ignores a near-miss that a later attempt on the same story already passed", () => {
    const msg = pickStripMessage([
      attempt("s-market", "tier2", 17, "2026-07-23T10:00:00Z"),
      attempt("s-market", "tier2", 19, "2026-07-23T11:00:00Z"), // passed after
    ]);
    expect(msg.kind).toBe("milestone");
  });

  it("praises the most recent star milestone when nothing is near-miss", () => {
    const msg = pickStripMessage([
      attempt("s-tea", "tier1", 20, "2026-07-22T10:00:00Z"),
      attempt("s-market", "tier2", 22, "2026-07-23T10:00:00Z"),
    ]);
    expect(msg).toMatchObject({ kind: "milestone", storyId: "s-market", stars: 2 });
  });

  it("falls back to welcome when attempts exist but none earned stars nor near-missed", () => {
    const msg = pickStripMessage([
      attempt("s-market", "tier1", 5, "2026-07-23T10:00:00Z"), // gap 9
    ]);
    expect(msg.kind).toBe("welcome");
  });
});
