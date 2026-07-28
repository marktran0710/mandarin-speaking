import { getStudentScopeKey } from "./studentSession";

export const VOCAB_QUIZ_COMPLETED_KEY = "vocabQuizCompletedStoryIds";

// Keyed per student so a shared classroom device can't leak one student's
// completed-quiz flags into the next student's session.
function scopedKey(): string {
  return `${VOCAB_QUIZ_COMPLETED_KEY}:${getStudentScopeKey()}`;
}

export function loadCompletedVocabQuizzes(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(scopedKey());
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function markVocabQuizCompleted(topicId: string) {
  try {
    const next = { ...loadCompletedVocabQuizzes(), [topicId]: true };
    localStorage.setItem(scopedKey(), JSON.stringify(next));
  } catch {
    /* storage unavailable — the quiz will just ask again next time */
  }
}
