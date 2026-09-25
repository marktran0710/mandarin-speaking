// One-Time Vocabulary Preview plan, Epic B: the Story Practice speaking
// preview must show the exact same vocabulary the quiz already tested -
// never a second, independently-aggregated word list that could
// eventually disagree with it. topicQuizEntries owns the canonical
// vocabAssessment bank and deduplication; this module only reshapes
// its output for a read-only preview screen.

import { topicQuizEntries, type QuizSourceTopic } from "./model";

export interface SpeakingVocabularyPreviewItem {
  wordId: string;
  word: string;
  pinyin?: string;
  pos?: string;
  meaning?: string;
  audioUrl?: string;
}

/** The Story Practice speaking preview's vocabulary list - identical set
 * and order to topicQuizEntries(topic), the same source the vocabulary
 * quiz itself uses. */
export function speakingVocabularyItems(topic: QuizSourceTopic): SpeakingVocabularyPreviewItem[] {
  const entries = topicQuizEntries(topic);
  return entries.map((entry) => ({
    wordId: entry.wordId ?? entry.word,
    word: entry.word,
    pinyin: entry.pinyin,
    pos: entry.pos,
    meaning: entry.translation,
    audioUrl: entry.audioUrl,
  }));
}
