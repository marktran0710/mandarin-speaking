import { PRACTICE_UNLOCK_STARS, syncLocalStars } from "@entities/vocabulary";
import { clearPhaseFlags } from "@shared/lib/studyProgressFlags";
import type { VocabularyProgression } from "../services/api/quiz-analytics";
import { clearStoryLevelSubmitted } from "./storyLevelProgress";
import { clearVocabQuizCompleted } from "./vocabQuizStorage";

/** A successful server read replaces every local completion signal that
 * depends on the quiz gate. Local mirrors cannot keep a revoked gate open. */
export function syncServerVocabularyProgress(progress: VocabularyProgression): void {
  syncLocalStars(progress.storyId, progress.quizStars);
  if (progress.quizStars < PRACTICE_UNLOCK_STARS) {
    clearStoryLevelSubmitted(progress.storyId);
    clearVocabQuizCompleted(progress.storyId);
    clearPhaseFlags(progress.storyId);
  }
}
