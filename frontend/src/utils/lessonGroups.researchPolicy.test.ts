import { afterEach, describe, expect, it, vi } from "vitest";

// End-to-end cascade proof (Epic 3, Task 3.9/3.10/3.13): a research
// participant's story/lesson completion must bypass the accuracy threshold
// the same way stars do, WITHOUT lessonGroups.ts itself knowing anything
// about research policy - it just reads loadLocalStars, exactly as before.
// This test goes through the real attemptEarnsStar -> recordLocalStars ->
// loadLocalStars -> isStoryFinished chain, not a mock of any of them, so it
// actually proves the cascade this session's design depends on.

const { getCachedResearchContext } = vi.hoisted(() => ({ getCachedResearchContext: vi.fn() }));
vi.mock("./researchContext", () => ({ getCachedResearchContext }));

import { attemptEarnsStar, recordLocalStars } from "@entities/vocabulary";
import { isStoryFinished, isLessonGroupUnlocked, lessonCompletion } from "./lessonGroups";
import type { Topic } from "@entities/topic";

function topic(id: string, lessonNumber: number): Topic {
  return {
    id,
    name: id,
    description: "",
    skillFocus: "Speaking",
    images: ["/x.png"],
    vocabulary: { 0: ["市場"] },
    vocabularyTranslation: { 0: ["market"] },
    vocabAssessment: [{
      questionId: `${id}-easy`, wordId: `${id}-word`, targetWord: "撣", pinyin: "shìchǎng",
      pos: "N", simpleEnglishMeaning: "market", level: "easy", difficultyWeight: 1,
      questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "What does this mean?",
      options: ["market", "book", "door", "room"], correctAnswer: "market", acceptedAnswers: ["market"], explanation: "market",
    }],
    lessonNumber,
  } as unknown as Topic;
}

describe("research-coverage completion cascades through the real star/completion chain", () => {
  afterEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("a low-accuracy but completed ladder finishes the story for a research participant", () => {
    getCachedResearchContext.mockReturnValue({
      active: true, coreCompletionPolicy: "research_coverage",
      practiceAvailable: false, reviewAvailable: false, probeAvailable: false,
    });

    const t = topic("story-research", 5);
    // Simulates what useQuizSession.ts does after each round finishes:
    // attemptEarnsStar -> recordLocalStars, with near-zero accuracy that
    // would fail production's thresholds outright.
    recordLocalStars("story-research", attemptEarnsStar("tier1", 1, 20)!);
    recordLocalStars("story-research", attemptEarnsStar("tier2", 1, 22)!);
    recordLocalStars("story-research", attemptEarnsStar("tier3", 1, 25)!);

    const submitted = new Set(["story-research"]);
    expect(isStoryFinished(t, submitted)).toBe(true);

    const { done, total } = lessonCompletion({ lessonNumber: 5, topics: [t] }, submitted);
    expect(done).toBe(1);
    expect(total).toBe(1);
  });

  it("the same low-accuracy ladder would NOT finish the story under production_accuracy - confirms this is genuinely policy-gated, not just always-true now", () => {
    getCachedResearchContext.mockReturnValue({
      active: false, coreCompletionPolicy: "production_accuracy",
      practiceAvailable: false, reviewAvailable: false, probeAvailable: false,
    });

    const t = topic("story-production", 5);
    // tier1 fails production's 70% threshold at 1/20 (5%), so nothing gets
    // recorded - mirrors exactly what useQuizSession.ts does: it only
    // calls recordLocalStars when attemptEarnsStar returns non-null.
    const earned = attemptEarnsStar("tier1", 1, 20);
    expect(earned).toBeNull();
    if (earned) recordLocalStars("story-production", earned);

    const submitted = new Set(["story-production"]);
    expect(isStoryFinished(t, submitted)).toBe(false);
  });

  it("a research participant's next lesson unlocks once the previous lesson's stories all finish this way", () => {
    getCachedResearchContext.mockReturnValue({
      active: true, coreCompletionPolicy: "research_coverage",
      practiceAvailable: false, reviewAvailable: false, probeAvailable: false,
    });

    const lesson5Story = topic("l5-story", 5);
    recordLocalStars("l5-story", attemptEarnsStar("tier1", 0, 20)!);
    recordLocalStars("l5-story", attemptEarnsStar("tier2", 0, 22)!);
    recordLocalStars("l5-story", attemptEarnsStar("tier3", 0, 25)!);
    const submitted = new Set(["l5-story"]);

    const groups = [
      { lessonNumber: 5, topics: [lesson5Story] },
      { lessonNumber: 6, topics: [topic("l6-story", 6)] },
    ];
    expect(isLessonGroupUnlocked(groups, 1, submitted)).toBe(true);
  });
});
