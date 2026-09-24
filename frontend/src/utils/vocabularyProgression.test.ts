import { describe, expect, it } from "vitest";
import type { Topic } from "../components/content/topic-selector/types";
import { isStoryFinished } from "./lessonGroups";
import { practiceUnlocked } from "./quizTiers";
import { vocabularyGateStateFor, getVocabularyGateState } from "./vocabularyProgression";

// Epic 1 (BKT x SM-2 research-mode plan): proves the production adapter is
// a pure wrapper around the SAME existing functions the rest of the app
// already uses (isStoryFinished, practiceUnlocked) - not a parallel
// reimplementation that could quietly drift from them.

function topic(id: string, hasQuiz = true): Topic {
  return {
    id,
    name: id,
    description: "",
    skillFocus: "Speaking",
    images: ["/x.png"],
    vocabulary: hasQuiz ? { 0: ["市場"] } : {},
    vocabularyTranslation: hasQuiz ? { 0: ["market"] } : undefined,
    vocabAssessment: hasQuiz ? [{
      questionId: `${id}-easy`, wordId: `${id}-word`, targetWord: "撣", pinyin: "shìchǎng",
      pos: "N", simpleEnglishMeaning: "market", level: "easy", difficultyWeight: 1,
      questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "What does this mean?",
      options: ["market", "book", "door", "room"], correctAnswer: "market", acceptedAnswers: ["market"], explanation: "market",
    }] : undefined,
  } as unknown as Topic;
}

describe("vocabularyGateStateFor - production_accuracy policy", () => {
  it("matches isStoryFinished and practiceUnlocked exactly for a fully-starred, submitted story", () => {
    const t = topic("story-a");
    const submitted = new Set(["story-a"]);
    const starsFor = () => 3;

    const state = vocabularyGateStateFor("production_accuracy", t, submitted, starsFor);

    expect(state.coreRoundsCompleted).toBe(true);
    expect(state.speakingUnlocked).toBe(practiceUnlocked(3));
    expect(state.storyVocabularyComplete).toBe(isStoryFinished(t, submitted, starsFor));
    expect(state.speakingUnlocked).toBe(true);
    expect(state.storyVocabularyComplete).toBe(true);
    expect(state.progressDisplay).toBe("3 / 3");
  });

  it("matches existing behavior for a partially-starred, unsubmitted story", () => {
    const t = topic("story-b");
    const submitted = new Set<string>();
    const starsFor = () => 2;

    const state = vocabularyGateStateFor("production_accuracy", t, submitted, starsFor);

    expect(state.coreRoundsCompleted).toBe(false);
    expect(state.speakingUnlocked).toBe(practiceUnlocked(2));
    expect(state.speakingUnlocked).toBe(false);
    expect(state.storyVocabularyComplete).toBe(isStoryFinished(t, submitted, starsFor));
    expect(state.storyVocabularyComplete).toBe(false);
    expect(state.progressDisplay).toBe("2 / 3");
  });

  it("a quiz-less story is core-complete without any stars, matching isStoryFinished's no-quiz exemption", () => {
    const t = topic("story-c", false);
    const submitted = new Set(["story-c"]);
    const starsFor = () => 0;

    const state = vocabularyGateStateFor("production_accuracy", t, submitted, starsFor);

    expect(state.coreRoundsCompleted).toBe(true);
    expect(state.storyVocabularyComplete).toBe(isStoryFinished(t, submitted, starsFor));
    expect(state.storyVocabularyComplete).toBe(true);
  });

  it("stars earned but not submitted is not story-complete, matching isStoryFinished", () => {
    const t = topic("story-d");
    const submitted = new Set<string>();
    const starsFor = () => 3;

    const state = vocabularyGateStateFor("production_accuracy", t, submitted, starsFor);

    expect(state.speakingUnlocked).toBe(true);
    expect(state.storyVocabularyComplete).toBe(isStoryFinished(t, submitted, starsFor));
    expect(state.storyVocabularyComplete).toBe(false);
  });
});

describe("vocabularyGateStateFor - research_coverage policy", () => {
  it("is not implemented yet and throws rather than returning plausible-looking wrong data", () => {
    const t = topic("story-a");
    expect(() =>
      vocabularyGateStateFor("research_coverage", t, new Set(), () => 0),
    ).toThrow(/not implemented until Epic 3/);
  });
});

describe("getVocabularyGateState (localStorage convenience wrapper)", () => {
  it("defaults to production_accuracy and reads real local star/submission state", () => {
    localStorage.clear();
    const t = topic("story-local");

    const state = getVocabularyGateState(t);

    // No stars recorded yet, not submitted - same defaults isStoryFinished
    // and practiceUnlocked already produce for a fresh story.
    expect(state.coreRoundsCompleted).toBe(false);
    expect(state.speakingUnlocked).toBe(false);
    expect(state.storyVocabularyComplete).toBe(false);
  });
});
