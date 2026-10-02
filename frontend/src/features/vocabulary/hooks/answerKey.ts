import type { VocabPriorityReviewWord } from "../../../services/database";
import type { VocabQuizEntry, VocabQuizQuestion } from "@entities/vocabulary";

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

export function entriesInServerPriorityOrder(entries: VocabQuizEntry[], priorityReviewWords: VocabPriorityReviewWord[]): VocabQuizEntry[] {
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
        bktSeenQuestionKinds: priorityWord.seenQuestionTypes as VocabQuizEntry["bktSeenQuestionKinds"],
        bktNextDimension: nextDimension,
        bktObservationCount: priorityWord.observationCount,
        bktLastResponseAt: priorityWord.lastResponseAt,
      }]
      : [entry];
  });
}
