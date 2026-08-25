import { describe, expect, it } from "vitest";
import { createCustomStory, storyToDraft } from "./StoryBuilderSection.model";
import { emptyCustomStoryDraft } from "./StoryBuilderSection.helpers";

describe("story-wide learning content", () => {
  it("serializes vocabulary and phrases outside the frame list", () => {
    const draft = {
      ...emptyCustomStoryDraft,
      title: "A shared lesson",
      imageUrls: { easy: ["image"], medium: [""], hard: [""] },
      prompts: { easy: ["Say this"], medium: [""], hard: [""] },
      storyVocabulary: {
        easy: { vocabulary: "學校", vocabularyPinyin: "xuéxiào", vocabularyPos: "N", vocabularyTranslation: "school" },
        medium: { vocabulary: "", vocabularyPinyin: "", vocabularyPos: "", vocabularyTranslation: "" },
        hard: { vocabulary: "", vocabularyPinyin: "", vocabularyPos: "", vocabularyTranslation: "" },
      },
      storyPhrases: {
        easy: { phrases: "在學校", phrasesTranslation: "at school" },
        medium: { phrases: "", phrasesTranslation: "" },
        hard: { phrases: "", phrasesTranslation: "" },
      },
    };

    const story = createCustomStory(draft);
    expect(story.storyVocabulary?.easy.vocabulary).toBe("學校");
    expect(story.storyPhrases?.easy.phrases).toBe("在學校");
    expect(story.frames[0].vocabulary).toBe("");
  });

  it("aggregates legacy per-frame content when opening an old story", () => {
    const draft = storyToDraft({
      id: "legacy",
      title: "Legacy story",
      frames: [
        { imageUrl: "a", prompt: "一", vocabulary: "學校", vocabularyTranslation: "school", phrases: "在學校", phrasesTranslation: "at school" },
        { imageUrl: "b", prompt: "二", vocabulary: "老師", vocabularyTranslation: "teacher", phrases: "在學校, 跟老師", phrasesTranslation: "at school, with the teacher" },
      ],
    });

    expect(draft.storyVocabulary.easy.vocabulary).toBe("學校, 老師");
    expect(draft.storyPhrases.easy.phrases).toBe("在學校, 跟老師");
  });
});
