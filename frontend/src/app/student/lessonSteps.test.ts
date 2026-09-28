import { describe, expect, it } from "vitest";
import type { SceneSubmission } from "../../services/database";
import {
  computeLessonSteps,
  firstUnfinishedPhase,
  sceneSubmissionsFromProgress,
  scenesForSubmission,
  type LessonProgressInput,
} from "./lessonSteps";

const fresh: LessonProgressInput = {
  hasQuiz: true,
  previewDone: false,
  quizDone: false,
  sceneCount: 3,
  scenesRecorded: 0,
  turnCount: 2,
  turnsRecorded: 0,
  conversationAvailable: true,
  submitted: false,
};

function unlocked(input: LessonProgressInput) {
  const steps = computeLessonSteps(input);
  return Object.fromEntries(Object.entries(steps).map(([phase, step]) => [phase, step.unlocked]));
}

describe("computeLessonSteps", () => {
  it("opens only the preview for a fresh lesson, with a reason on every locked step", () => {
    const steps = computeLessonSteps(fresh);
    expect(unlocked(fresh)).toEqual({
      "vocab-preview": true, "vocab-quiz": false, "story-speaking": false, conversation: false, submit: false,
    });
    expect(steps["vocab-quiz"].lockReason).toBe("lockedUntilPreview");
    expect(steps["story-speaking"].lockReason).toBe("lockedUntilQuizRounds");
    expect(steps.submit.lockReason).toBe("lockedUntilPracticePath");
  });

  it("opens the quiz after the preview, and both practice paths together after all three rounds", () => {
    expect(unlocked({ ...fresh, previewDone: true })["vocab-quiz"]).toBe(true);
    expect(unlocked({ ...fresh, previewDone: true })["story-speaking"]).toBe(false);
    const afterQuiz = unlocked({ ...fresh, previewDone: true, quizDone: true });
    expect(afterQuiz["story-speaking"]).toBe(true);
    expect(afterQuiz.conversation).toBe(true);
    expect(afterQuiz.submit).toBe(false);
  });

  it("opens Submit once either path is fully recorded, not while one is half done", () => {
    const base = { ...fresh, previewDone: true, quizDone: true };
    expect(unlocked({ ...base, scenesRecorded: 2 }).submit).toBe(false);
    expect(unlocked({ ...base, scenesRecorded: 3 }).submit).toBe(true);
    expect(unlocked({ ...base, turnsRecorded: 2 }).submit).toBe(true);
    expect(computeLessonSteps({ ...base, turnsRecorded: 2 }).conversation.done).toBe(true);
  });

  it("hides the quiz and gates practice on the preview for a lesson with no quiz", () => {
    // A quiz-less lesson counts its (absent) quiz as done; that must not
    // count as having finished the preview.
    const noQuiz = { ...fresh, hasQuiz: false, quizDone: true };
    expect(firstUnfinishedPhase(noQuiz)).toBe("vocab-preview");
    expect(computeLessonSteps(noQuiz)["vocab-quiz"].visible).toBe(false);
    expect(computeLessonSteps(noQuiz)["story-speaking"].lockReason).toBe("lockedUntilPreview");
    expect(unlocked({ ...noQuiz, previewDone: true })["story-speaking"]).toBe(true);
  });

  it("keeps Conversation locked with its own reason when the lesson has none", () => {
    const steps = computeLessonSteps({ ...fresh, previewDone: true, quizDone: true, conversationAvailable: false, turnCount: 0 });
    expect(steps.conversation.unlocked).toBe(false);
    expect(steps.conversation.lockReason).toBe("lockedNoConversation");
  });

  it("opens every step for review once the lesson is submitted", () => {
    expect(unlocked({ ...fresh, submitted: true })).toEqual({
      "vocab-preview": true, "vocab-quiz": true, "story-speaking": true, conversation: true, submit: true,
    });
  });
});

describe("firstUnfinishedPhase", () => {
  it("lands a reopened lesson on its first unfinished step", () => {
    expect(firstUnfinishedPhase(fresh)).toBe("vocab-preview");
    expect(firstUnfinishedPhase({ ...fresh, previewDone: true })).toBe("vocab-quiz");
    expect(firstUnfinishedPhase({ ...fresh, previewDone: true, quizDone: true })).toBe("story-speaking");
    expect(firstUnfinishedPhase({ ...fresh, previewDone: true, quizDone: true, turnsRecorded: 1 })).toBe("conversation");
    expect(firstUnfinishedPhase({ ...fresh, previewDone: true, quizDone: true, scenesRecorded: 3 })).toBe("submit");
  });
});

function scene(sceneIndex: number, transcription: string): SceneSubmission {
  return { sceneIndex, imageUrl: "", transcription, vocabUsed: [], vocabMissing: [], vocabScore: 0, toneAccuracy: 0, pronScore: 0 };
}

describe("sceneSubmissionsFromProgress", () => {
  it("rebuilds speaking scenes and conversation turns, later saves winning", () => {
    const restored = sceneSubmissionsFromProgress([
      { sceneIndex: 0, latestResult: scene(0, "scene zero"), updatedAt: "2026-09-01" },
      { sceneIndex: 0, turnId: "t1", turnIndex: 1, latestResult: scene(0, "old turn"), updatedAt: "2026-09-01" },
      { sceneIndex: 0, turnId: "t1", turnIndex: 1, latestResult: scene(0, "new turn"), updatedAt: "2026-09-02" },
      { sceneIndex: 2, latestResult: null },
    ]);
    expect(Object.keys(restored).sort()).toEqual(["conversation:1", "speaking:0"]);
    expect(restored["conversation:1"].transcription).toBe("new turn");
  });
});

describe("scenesForSubmission", () => {
  it("submits only finished paths, in scene order", () => {
    const submissions = {
      "speaking:10": scene(10, "s10"),
      "speaking:2": scene(2, "s2"),
      "conversation:1": scene(0, "c1"),
    };
    expect(scenesForSubmission(submissions, { speaking: true, conversation: false }).map((s) => s.transcription)).toEqual(["s2", "s10"]);
    expect(scenesForSubmission(submissions, { speaking: false, conversation: true }).map((s) => s.transcription)).toEqual(["c1"]);
  });
});
