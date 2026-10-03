import type { VocabQuizEntry, VocabQuizQuestion } from "@entities/vocabulary";
import type { VocabQuizDimension } from "@entities/vocabulary/types";

type PriorityReviewSnapshot = {
  wordId: string;
  word: string;
  seenQuestionTypes?: readonly string[];
  observationCount?: number;
  lastResponseAt?: string | null;
  vocabularyState?: {
    practice?: { nextDimension?: VocabQuizDimension | null } | null;
  } | null;
};

export function correctAnswer(question: VocabQuizQuestion) {
  switch (question.kind) {
    case "translation": return question.correctTranslation;
    case "cloze": return question.correctWord;
    case "pinyin": return question.correctPinyin;
    case "pos": return question.correctPos;
    case "synonym": return question.correctSynonym;
    case "reverse":
    case "listening": return question.correctWord;
    case "assessment": return question.correctAnswer;
  }
}

export function entriesInServerPriorityOrder(entries: VocabQuizEntry[], priorityReviewWords: readonly PriorityReviewSnapshot[]): VocabQuizEntry[] {
  return priorityReviewWords.flatMap((priorityWord) => {
    const entry = entries.find((candidate) => candidate.wordId === priorityWord.wordId)
      ?? entries.find((candidate) => candidate.word === priorityWord.word);
    if (!entry) return [];
    // Corrective targeting comes only from the server's current unresolved
    // state (practice.nextDimension), never from a history of failed types.
    const nextDimension = priorityWord.vocabularyState?.practice?.nextDimension ?? undefined;
    return priorityWord.seenQuestionTypes?.length || nextDimension
      ? [{
        ...entry,
        bktSeenQuestionKinds: priorityWord.seenQuestionTypes,
        bktNextDimension: nextDimension,
        bktObservationCount: priorityWord.observationCount,
        bktLastResponseAt: priorityWord.lastResponseAt,
      }]
      : [entry];
  });
}
