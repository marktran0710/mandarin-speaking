import { describe, expect, it } from "vitest";
import {
  conversationTurnsToExchanges,
  createCustomStory,
  exchangesToConversationTurns,
  storyToDraft,
} from "./StoryBuilderSection.model";
import { blankConversationExchange, emptyCustomStoryDraft } from "./StoryBuilderSection.helpers";

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

describe("exchangesToConversationTurns", () => {
  it("converts one exchange into an alternating system/student turn pair", () => {
    const exchange = {
      ...blankConversationExchange("ex-1"),
      characterText: "你好",
      characterPinyin: "Nǐ hǎo",
      characterTranslation: "Hello",
      characterAudioUrl: "data:audio/wav;base64,AAA",
      studentText: "你好！",
      studentPinyin: "Nǐ hǎo!",
      studentTranslation: "Hello!",
      studentModelAudioUrl: "data:audio/wav;base64,BBB",
    };

    const turns = exchangesToConversationTurns([exchange]);

    expect(turns).toEqual([
      { id: "system-ex-1", speaker: "system", text: "你好", pinyin: "Nǐ hǎo", translation: "Hello", audioUrl: "data:audio/wav;base64,AAA" },
      { id: "student-ex-1", speaker: "student", text: "你好！", targetText: "你好！", pinyin: "Nǐ hǎo!", translation: "Hello!", targetAudioUrl: "data:audio/wav;base64,BBB" },
    ]);
  });

  it("never puts the character's audio on the student turn or vice versa", () => {
    const exchange = {
      ...blankConversationExchange("ex-1"),
      characterText: "你好",
      characterAudioUrl: "data:audio/wav;base64,CHARACTER",
      studentText: "你好！",
      studentModelAudioUrl: "data:audio/wav;base64,STUDENT",
    };
    const [systemTurn, studentTurn] = exchangesToConversationTurns([exchange])!;
    expect(systemTurn.audioUrl).toBe("data:audio/wav;base64,CHARACTER");
    expect((studentTurn as any).audioUrl).toBeUndefined();
    expect(studentTurn.targetAudioUrl).toBe("data:audio/wav;base64,STUDENT");
  });

  it("skips a completely blank exchange and returns undefined when nothing is left", () => {
    expect(exchangesToConversationTurns([blankConversationExchange("ex-1")])).toBeUndefined();
  });

  it("drops only the blank exchanges, keeping filled-in ones", () => {
    const filled = { ...blankConversationExchange("ex-2"), characterText: "你好", studentText: "你好！" };
    const turns = exchangesToConversationTurns([blankConversationExchange("ex-1"), filled]);
    expect(turns).toHaveLength(2);
    expect(turns![0].id).toBe("system-ex-2");
  });
});

describe("conversationTurnsToExchanges", () => {
  it("is the inverse of exchangesToConversationTurns", () => {
    const exchange = {
      ...blankConversationExchange("ex-1"),
      characterText: "你好",
      characterPinyin: "Nǐ hǎo",
      characterAudioUrl: "/uploads/audio/a.wav",
      studentText: "你好！",
      studentModelAudioUrl: "/uploads/audio/b.wav",
    };
    const turns = exchangesToConversationTurns([exchange]);
    const roundTripped = conversationTurnsToExchanges(turns);

    expect(roundTripped).toEqual([
      { id: "ex-1", characterText: "你好", characterPinyin: "Nǐ hǎo", characterTranslation: "", characterAudioUrl: "/uploads/audio/a.wav", studentText: "你好！", studentPinyin: "", studentTranslation: "", studentModelAudioUrl: "/uploads/audio/b.wav" },
    ]);
  });

  it("returns an empty array for a story with no conversation turns", () => {
    expect(conversationTurnsToExchanges(undefined)).toEqual([]);
  });
});

describe("createCustomStory / storyToDraft with conversation content", () => {
  it("includes conversationTurns only when the toggle is enabled", () => {
    const enabledDraft = {
      ...emptyCustomStoryDraft,
      title: "Conversation story",
      conversationEnabled: true,
      conversationExchanges: [
        { ...blankConversationExchange("ex-1"), characterText: "你好", studentText: "你好！" },
      ],
    };
    const enabledStory = createCustomStory(enabledDraft);
    expect(enabledStory.conversationTurns).toHaveLength(2);

    const disabledDraft = { ...enabledDraft, conversationEnabled: false };
    const disabledStory = createCustomStory(disabledDraft);
    expect(disabledStory.conversationTurns).toBeUndefined();
  });

  it("round-trips an existing conversation story back into the draft", () => {
    const draft = storyToDraft({
      id: "conv-story",
      title: "Conversation story",
      frames: [{ imageUrl: "a", prompt: "p", vocabulary: "" }],
      conversationTurns: [
        { id: "system-1", speaker: "system", text: "你好", audioUrl: "/uploads/audio/a.wav" },
        { id: "student-1", speaker: "student", text: "你好！", targetText: "你好！" },
      ],
    });

    expect(draft.conversationEnabled).toBe(true);
    expect(draft.conversationExchanges).toHaveLength(1);
    expect(draft.conversationExchanges[0].characterText).toBe("你好");
    expect(draft.conversationExchanges[0].studentText).toBe("你好！");
  });

  it("a legacy story with no conversation turns opens with the toggle off", () => {
    const draft = storyToDraft({
      id: "legacy",
      title: "Legacy story",
      frames: [{ imageUrl: "a", prompt: "p", vocabulary: "" }],
    });
    expect(draft.conversationEnabled).toBe(false);
    expect(draft.conversationExchanges).toEqual([]);
  });
});
