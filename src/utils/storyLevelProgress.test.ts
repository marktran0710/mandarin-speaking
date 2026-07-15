import { beforeEach, describe, expect, it } from "vitest";
import { isStoryLevelUnlocked, markStoryLevelSubmitted } from "./storyLevelProgress";

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

  it("tracks progress independently per story", () => {
    markStoryLevelSubmitted("story-1", "easy");
    expect(isStoryLevelUnlocked("story-2", "medium")).toBe(false);
  });
});
