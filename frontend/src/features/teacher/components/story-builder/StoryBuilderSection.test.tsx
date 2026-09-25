import { describe, expect, it } from "vitest";
import { emptyCustomStoryDraft } from "./StoryBuilderSection.helpers";
import { createCustomStory } from "./StoryBuilderSection.model";

describe("StoryBuilderSection canonical content", () => {
  it("creates a story without retired quiz-material keys", () => {
    const story = createCustomStory(emptyCustomStoryDraft);
    const frameKeys = Object.keys(story.frames[0] ?? {}).map((key) =>
      key.toLowerCase(),
    );
    const storyKeys = Object.keys(story).map((key) => key.toLowerCase());

    expect(frameKeys.some((key) => key.includes("distractor"))).toBe(false);
    expect(frameKeys.some((key) => key.includes("cloze"))).toBe(false);
    expect(frameKeys.some((key) => key.includes("synonym"))).toBe(false);
    expect(storyKeys.some((key) => key.includes("snapshot"))).toBe(false);
  });
});
