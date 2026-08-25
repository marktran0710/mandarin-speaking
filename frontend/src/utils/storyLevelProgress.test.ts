import { beforeEach, describe, expect, it } from "vitest";
import {
  hasStoryLevelBeenSubmitted,
  isStoryLevelUnlocked,
  loadSubmittedLevels,
  markStoryLevelSubmitted,
  mergeSubmittedStoryLevels,
} from "./storyLevelProgress";
import type { StorySubmission } from "../services/database";

describe("storyLevelProgress", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("always unlocks easy", () => {
    expect(isStoryLevelUnlocked("story-1", "easy")).toBe(true);
  });

  it("keeps medium/hard locked until the previous tier is submitted", () => {
    expect(isStoryLevelUnlocked("story-1", "medium")).toBe(false);
    expect(isStoryLevelUnlocked("story-1", "hard")).toBe(false);

    markStoryLevelSubmitted("story-1", "easy");
    expect(isStoryLevelUnlocked("story-1", "medium")).toBe(true);
    expect(isStoryLevelUnlocked("story-1", "hard")).toBe(false);

    markStoryLevelSubmitted("story-1", "medium");
    expect(isStoryLevelUnlocked("story-1", "hard")).toBe(true);
  });

  it("only advances after an explicit submitted-level signal", () => {
    // Vocabulary quiz state, including all three earned stars, is purposely
    // stored elsewhere and is not an unlock signal for the next difficulty.
    window.localStorage.setItem(
      "storyLevelProgress:student",
      JSON.stringify({ "story-1": { easy: false } }),
    );

    expect(hasStoryLevelBeenSubmitted("story-1", "easy")).toBe(false);
    expect(isStoryLevelUnlocked("story-1", "medium")).toBe(false);

    markStoryLevelSubmitted("story-1", "easy");
    expect(hasStoryLevelBeenSubmitted("story-1", "easy")).toBe(true);
    expect(loadSubmittedLevels("story-1")).toEqual({ easy: true });
    expect(isStoryLevelUnlocked("story-1", "medium")).toBe(true);
  });

  it("tracks progress independently per story", () => {
    markStoryLevelSubmitted("story-1", "easy");
    expect(isStoryLevelUnlocked("story-2", "medium")).toBe(false);
  });

  it("hydrates submitted tiers from the current student's scene metadata without replacing local progress", () => {
    markStoryLevelSubmitted("local-story", "easy");
    const submissions = [
      {
        id: "submission-1",
        storyId: "teacher-ignored-fallback",
        studentId: "student-1",
        studentName: "Ada",
        scenes: [{ baseStoryId: "server-story", difficultyLevel: "medium" }],
      },
      {
        id: "submission-2",
        storyId: "teacher-other-hard",
        studentId: "another-student",
        studentName: "Other",
        scenes: [{ baseStoryId: "other-story", difficultyLevel: "hard" }],
      },
    ] as StorySubmission[];

    expect(mergeSubmittedStoryLevels(submissions, { studentId: "student-1", studentName: "Ada" })).toBe(true);
    expect(loadSubmittedLevels("local-story")).toEqual({ easy: true });
    expect(loadSubmittedLevels("server-story")).toEqual({ medium: true });
    expect(loadSubmittedLevels("other-story")).toEqual({});
    expect(mergeSubmittedStoryLevels(submissions, { studentId: "student-1", studentName: "Ada" })).toBe(false);
  });

  it("uses the tier-suffixed topic id only when legacy submissions lack scene context", () => {
    const submission = {
      id: "legacy-submission",
      storyId: "teacher-story-7-hard",
      studentName: "Student",
      scenes: [],
    } as StorySubmission;

    mergeSubmittedStoryLevels([submission], { studentName: "Student" });
    expect(loadSubmittedLevels("story-7")).toEqual({ hard: true });
  });
});
