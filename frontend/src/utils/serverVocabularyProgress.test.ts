import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadLocalStars, recordLocalStars } from "@entities/vocabulary";
import { loadPhaseFlags, markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { loadSubmittedStoryIds, markStoryLevelSubmitted } from "./storyLevelProgress";
import { loadCompletedVocabQuizzes, markVocabQuizCompleted } from "./vocabQuizStorage";
import { syncServerVocabularyProgress } from "./serverVocabularyProgress";
import type { VocabularyProgression } from "../services/api/quiz-analytics";

vi.mock("./studentSession", () => ({ getStudentScopeKey: () => "student-1" }));

function progress(stars: 0 | 1 | 2 | 3): VocabularyProgression {
  return { storyId: "lesson-1", quizStars: stars, requiredStars: 3, tiers: {} as VocabularyProgression["tiers"], speakingUnlocked: stars === 3, conversationAvailable: true, conversationUnlocked: stars === 3 };
}

describe("server vocabulary progress", () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });

  it.each([0, 2] as const)("removes revoked completion signals at %i stars and preserves another lesson", (stars) => {
    for (const lesson of ["lesson-1", "lesson-2"]) {
      recordLocalStars(lesson, 3);
      markStoryLevelSubmitted(lesson);
      markVocabQuizCompleted(lesson);
      markPhaseSeen(lesson, "speaking");
    }
    syncServerVocabularyProgress(progress(stars));
    expect(loadLocalStars("lesson-1")).toBe(stars);
    expect(loadSubmittedStoryIds().has("lesson-1")).toBe(false);
    expect(loadCompletedVocabQuizzes()["lesson-1"]).toBeUndefined();
    expect(loadPhaseFlags("lesson-1").speaking).toBe(false);
    expect(loadLocalStars("lesson-2")).toBe(3);
    expect(loadSubmittedStoryIds().has("lesson-2")).toBe(true);
    expect(loadPhaseFlags("lesson-2").speaking).toBe(true);
  });

  it("preserves completion when the server still confirms three stars", () => {
    markStoryLevelSubmitted("lesson-1");
    markPhaseSeen("lesson-1", "speaking");
    syncServerVocabularyProgress(progress(3));
    expect(loadLocalStars("lesson-1")).toBe(3);
    expect(loadSubmittedStoryIds().has("lesson-1")).toBe(true);
    expect(loadPhaseFlags("lesson-1").speaking).toBe(true);
  });
});
