import { beforeEach, describe, expect, it } from "vitest";
import {
  loadSubmittedStoryIds,
  markStoryLevelSubmitted,
  mergeSubmittedStoryLevels,
} from "./storyLevelProgress";
import type { StorySubmission } from "../services/database";

describe("storyLevelProgress", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("marks a story submitted, ignoring the legacy level argument", () => {
    expect(loadSubmittedStoryIds().has("story-1")).toBe(false);
    // The StoryRecorder runtime still passes the scene difficulty level; it is
    // accepted for call-site compatibility and ignored.
    markStoryLevelSubmitted("story-1", "hard");
    expect(loadSubmittedStoryIds().has("story-1")).toBe(true);
  });

  it("tracks submission independently per story", () => {
    markStoryLevelSubmitted("story-1");
    expect(loadSubmittedStoryIds().has("story-1")).toBe(true);
    expect(loadSubmittedStoryIds().has("story-2")).toBe(false);
  });

  it("reads the legacy nested { easy: true } shape as a submitted story", () => {
    window.localStorage.setItem(
      "storyLevelProgress:student",
      JSON.stringify({ "legacy-story": { easy: true }, "unstarted": { easy: false } }),
    );
    const submitted = loadSubmittedStoryIds();
    expect(submitted.has("legacy-story")).toBe(true);
    expect(submitted.has("unstarted")).toBe(false);
  });

  it("hydrates submitted stories from the current student's scene metadata without replacing local progress", () => {
    markStoryLevelSubmitted("local-story");
    const submissions = [
      {
        id: "submission-1",
        storyId: "teacher-ignored-fallback",
        storyTitle: "Ignored fallback",
        studentId: "student-1",
        studentName: "Ada",
        submittedAt: "2026-09-01T00:00:00.000Z",
        scenes: [{ baseStoryId: "server-story", difficultyLevel: "medium" }],
        reviewStatus: "pending",
      },
      {
        id: "submission-2",
        storyId: "teacher-other-hard",
        storyTitle: "Other story",
        studentId: "another-student",
        studentName: "Other",
        submittedAt: "2026-09-01T00:00:00.000Z",
        scenes: [{ baseStoryId: "other-story", difficultyLevel: "hard" }],
        reviewStatus: "pending",
      },
    ] as StorySubmission[];

    expect(mergeSubmittedStoryLevels(submissions, { studentId: "student-1", studentName: "Ada" })).toBe(true);
    const submitted = loadSubmittedStoryIds();
    expect(submitted.has("local-story")).toBe(true);
    expect(submitted.has("server-story")).toBe(true);
    expect(submitted.has("other-story")).toBe(false);
    expect(mergeSubmittedStoryLevels(submissions, { studentId: "student-1", studentName: "Ada" })).toBe(false);
  });

  it("does not guess a story id from an ambiguous legacy -medium/-hard topic id", () => {
    const submission = {
      id: "legacy-submission",
      storyId: "teacher-story-7-hard",
      storyTitle: "Legacy story",
      studentName: "Student",
      submittedAt: "2026-09-01T00:00:00.000Z",
      scenes: [],
      reviewStatus: "pending",
    } as StorySubmission;

    mergeSubmittedStoryLevels([submission], { studentName: "Student" });
    const submitted = loadSubmittedStoryIds();
    expect(submitted.has("story-7")).toBe(false);
    expect(submitted.has("story-7-hard")).toBe(false);
  });
});
