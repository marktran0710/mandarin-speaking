import type { VocabQuizEntry, VocabAssessmentQuestion } from "../components/story-vocab-quiz/model";

/** The student quiz reads only the canonical assessment bank.
 *
 * Story frames remain speaking context, but they are no longer a fallback
 * quiz database. This keeps the learner, BKT and research paths on the same
 * `vocab_assessment` contract and removes the old frame-pool/Quiz Review
 * compatibility branch.
 */
export interface QuizSourceTopic {
  images?: string[];
  vocabulary?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyAudioUrls?: Record<number, (string | null)[]>;
  vocabAssessment?: VocabAssessmentQuestion[];
}

function normalizedLevel(value: unknown): VocabAssessmentQuestion["level"] | null {
  const level = String(value ?? "").trim().toLowerCase();
  return level === "easy" || level === "medium" || level === "hard"
    ? level
    : null;
}

function contextPrompts(questions: VocabAssessmentQuestion[], targetWord: string): string[] {
  return Array.from(new Set(
    questions
      .filter((question) =>
        question.questionType === "context_cloze_mcq" ||
        question.questionType === "contextual_productive_recall",
      )
      .map((question) => question.prompt.trim())
      .filter((prompt) => prompt && prompt.includes(targetWord)),
  ));
}

export function topicQuizEntries(topic: QuizSourceTopic): VocabQuizEntry[] {
  if (!Array.isArray(topic.vocabAssessment)) return [];

  const byWord = new Map<string, VocabAssessmentQuestion[]>();
  topic.vocabAssessment.forEach((rawQuestion) => {
    const level = normalizedLevel(rawQuestion.level);
    if (!level || !rawQuestion.wordId) return;
    const question = { ...rawQuestion, level };
    const questions = byWord.get(question.wordId) ?? [];
    questions.push(question);
    byWord.set(question.wordId, questions);
  });

  return Array.from(byWord.entries()).map(([wordId, assessmentQuestions]) => {
    const first = assessmentQuestions[0];
    const lessonSentences = contextPrompts(assessmentQuestions, first.targetWord);
    return {
      word: first.targetWord,
      translation: first.simpleEnglishMeaning,
      wordId,
      pinyin: first.pinyin,
      pos: first.pos,
      ...(lessonSentences.length ? { lessonSentences } : {}),
      assessmentQuestions,
      bktValidationStatus: "APPROVED",
    };
  });
}

export function topicHasQuiz(topic: QuizSourceTopic): boolean {
  return topicQuizEntries(topic).length >= 1;
}
