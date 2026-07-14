export const VOCAB_QUIZ_COMPLETED_KEY = "vocabQuizCompletedStoryIds";

export function loadCompletedVocabQuizzes(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(VOCAB_QUIZ_COMPLETED_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function markVocabQuizCompleted(topicId: string) {
  try {
    const next = { ...loadCompletedVocabQuizzes(), [topicId]: true };
    localStorage.setItem(VOCAB_QUIZ_COMPLETED_KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable — the quiz will just ask again next time */
  }
}
