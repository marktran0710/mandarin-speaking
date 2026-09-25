import type { VocabAssessmentQuestion, VocabAssessmentRound, VocabQuizEntry } from "./types";

export interface QuizSourceTopic {
  images?: string[];
  vocabulary?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyAudioUrls?: Record<number, (string | null)[]>;
  vocabAssessment?: VocabAssessmentQuestion[];
}

function normalizedRound(value: unknown, questionType: string): VocabAssessmentRound | null {
  const parsed = Number(String(value ?? "").replace(/^round\s*/i, "").trim());
  if (parsed === 1 || parsed === 2 || parsed === 3) return parsed;
  // Published banks now use numeric rounds. Keep this read-only fallback so
  // old story snapshots remain playable while they are being migrated.
  const legacyRound = String(value ?? "").trim().toLocaleLowerCase();
  if (legacyRound === "easy") return 1;
  if (legacyRound === "medium") return 2;
  if (legacyRound === "hard") return 3;
  if (questionType === "basic_meaning_mcq") return 1;
  if (questionType === "character_to_pinyin_typing") return 2;
  if (questionType === "context_cloze_mcq") return 3;
  return null;
}

function contextPrompts(questions: VocabAssessmentQuestion[], targetWord: string): string[] {
  return Array.from(new Set(
    questions
      .filter((question) => question.questionType === "context_cloze_mcq" || question.questionType === "contextual_productive_recall")
      .map((question) => question.prompt.trim())
      .filter((prompt) => prompt && prompt.includes(targetWord)),
  ));
}

export function topicQuizEntries(topic: QuizSourceTopic): VocabQuizEntry[] {
  if (!Array.isArray(topic.vocabAssessment)) return [];
  const byWord = new Map<string, VocabAssessmentQuestion[]>();
  topic.vocabAssessment.forEach((rawQuestion) => {
    const round = normalizedRound(rawQuestion.round ?? rawQuestion.level, rawQuestion.questionType);
    if (!round || !rawQuestion.wordId) return;
    const legacyLevel = typeof rawQuestion.level === "string"
      ? rawQuestion.level.toLocaleLowerCase() as "easy" | "medium" | "hard"
      : undefined;
    const question = {
      ...rawQuestion,
      round,
      tier: `tier${round}` as const,
      ...(legacyLevel ? { level: legacyLevel } : {}),
    };
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
      ...(first.audioUrl ? { audioUrl: first.audioUrl } : {}),
      ...(lessonSentences.length ? { lessonSentences } : {}),
      assessmentQuestions,
      bktValidationStatus: "APPROVED",
    };
  });
}

export function topicHasQuiz(topic: QuizSourceTopic): boolean {
  return topicQuizEntries(topic).length >= 1;
}
