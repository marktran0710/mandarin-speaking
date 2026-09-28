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
    return priorityWord.seenQuestionTypes?.length || priorityWord.failedQuestionTypes?.length
      ? [{
        ...entry,
        bktSeenQuestionKinds: priorityWord.seenQuestionTypes as VocabQuizEntry["bktSeenQuestionKinds"],
        bktFailedQuestionKinds: priorityWord.failedQuestionTypes as VocabQuizEntry["bktFailedQuestionKinds"],
        bktObservationCount: priorityWord.observationCount,
        bktLastResponseAt: priorityWord.lastResponseAt,
      }]
      : [entry];
  });
}
