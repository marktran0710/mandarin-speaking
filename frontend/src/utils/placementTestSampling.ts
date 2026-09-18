import type { StoredCustomStory } from "../services/database";

/** One placement-test item: an "easy" (know-it/tier1) question, carrying
 * everything a real tier1 submission needs (see useQuizSession's `choose`)
 * plus its origin story, since a placement test spans many lessons at once
 * while the server's answer resolver is scoped to a single story per
 * submission (backend/analytics/bkt_assessment_resolver.py). */
export interface PlacementTestQuestion {
  storyId: string;
  wordId: string;
  targetWord: string;
  itemId: string;
  prompt: string;
  options: string[];
  correctAnswer: string;
  level: "easy";
}

/** Samples up to `wordsPerLesson` know-it (tier1, "easy") questions from
 * every published story that has a vocabulary assessment bank, so a
 * placement test can give BKT a starting read on words the student hasn't
 * reached yet ("cold start") without waiting for each lesson's own Round 1.
 * Deterministic (first N in bank order), not shuffled, so a re-render or a
 * retake shows the same set. */
export function samplePlacementTestQuestions(
  stories: StoredCustomStory[],
  wordsPerLesson: number,
): PlacementTestQuestion[] {
  const questions: PlacementTestQuestion[] = [];
  for (const story of stories) {
    if (!story.published || !Array.isArray(story.vocabAssessment)) continue;
    const easyQuestions = story.vocabAssessment.filter((item) => item.level === "easy");
    for (const item of easyQuestions.slice(0, wordsPerLesson)) {
      questions.push({
        storyId: story.id,
        wordId: item.wordId,
        targetWord: item.targetWord,
        itemId: item.questionId,
        prompt: item.prompt,
        options: item.options,
        correctAnswer: item.correctAnswer,
        level: "easy",
      });
    }
  }
  return questions;
}
