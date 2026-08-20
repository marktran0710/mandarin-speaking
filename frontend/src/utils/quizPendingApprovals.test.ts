import { describe, expect, it } from "vitest";
import {
  isApproved,
  storyPendingApprovals,
  toggleApproval,
  type QuizApprovalMark,
} from "./quizPendingApprovals";

describe("quizPendingApprovals", () => {
  it("toggle adds then removes the same mark", () => {
    const mark: QuizApprovalMark = { word: "知道", kind: "cloze", index: 0 };
    const added = toggleApproval([], mark);
    expect(isApproved(added, "知道", "cloze", 0)).toBe(true);
    expect(toggleApproval(added, mark)).toEqual([]);
  });

  it("distractors marks have no index, matched only against undefined", () => {
    const marks: QuizApprovalMark[] = [{ word: "知道", kind: "distractors" }];
    expect(isApproved(marks, "知道", "distractors")).toBe(true);
    expect(isApproved(marks, "知道", "distractors", 0)).toBe(false);
  });

  it("marks for other words or kinds never match", () => {
    const marks: QuizApprovalMark[] = [{ word: "知道", kind: "cloze", index: 0 }];
    expect(isApproved(marks, "一起", "cloze", 0)).toBe(false);
    expect(isApproved(marks, "知道", "synonym", 0)).toBe(false);
  });

  describe("storyPendingApprovals", () => {
    it("returns [] when the story has never saved any", () => {
      expect(storyPendingApprovals({}, "easy")).toEqual([]);
    });

    it("returns [] for a tier with nothing saved, even if another tier has marks", () => {
      const story = { quizPendingApprovals: { medium: [{ word: "x", kind: "cloze" as const }] } };
      expect(storyPendingApprovals(story, "easy")).toEqual([]);
    });

    it("returns the stored marks for the requested tier", () => {
      const marks: QuizApprovalMark[] = [{ word: "知道", kind: "synonym", index: 1 }];
      const story = { quizPendingApprovals: { easy: marks } };
      expect(storyPendingApprovals(story, "easy")).toEqual(marks);
    });
  });
});
