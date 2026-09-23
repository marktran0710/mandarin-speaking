// One-Time Vocabulary Preview plan, Epic B: the Story Practice speaking
// preview must show the exact same vocabulary the quiz already tested -
// never a second, independently-aggregated word list that could
// eventually disagree with it. topicQuizEntries already owns the
// vocabAssessment -> quizVocabulary -> topic.vocabulary fallback chain
// (question-bank material, exclusions, dedup); this module only reshapes
// its output for a read-only preview screen, plus a best-effort per-word
// audio lookup topicQuizEntries itself doesn't carry.

import { topicQuizEntries, type QuizSourceTopic } from "./topicQuiz";

export interface SpeakingVocabularyPreviewItem {
  wordId: string;
  word: string;
  pinyin?: string;
  pos?: string;
  meaning?: string;
  audioUrl?: string;
}

type AudioLookupTopic = Pick<QuizSourceTopic, "vocabulary"> & {
  vocabularyAudioUrls?: Record<number, (string | null)[]>;
};

/** word -> first model-voice clip found for it across every scene. Scene-
 * scoped source data (topic.vocabulary[sceneIndex][wordIndex] paired with
 * vocabularyAudioUrls[sceneIndex][wordIndex]) flattened into one lookup,
 * since the preview shows the story's whole vocabulary at once rather
 * than one scene at a time. */
function buildWordAudioMap(topic: AudioLookupTopic): Map<string, string> {
  const audioByWord = new Map<string, string>();
  Object.entries(topic.vocabulary ?? {}).forEach(([sceneIndexKey, words]) => {
    const sceneIndex = Number(sceneIndexKey);
    const audioUrls = topic.vocabularyAudioUrls?.[sceneIndex];
    (words ?? []).forEach((word, index) => {
      const url = audioUrls?.[index];
      if (url && !audioByWord.has(word)) audioByWord.set(word, url);
    });
  });
  return audioByWord;
}

/** The Story Practice speaking preview's vocabulary list - identical set
 * and order to topicQuizEntries(topic), the same source the vocabulary
 * quiz itself uses. */
export function speakingVocabularyItems(topic: QuizSourceTopic & AudioLookupTopic): SpeakingVocabularyPreviewItem[] {
  const entries = topicQuizEntries(topic);
  const audioByWord = buildWordAudioMap(topic);
  return entries.map((entry) => ({
    wordId: entry.wordId ?? entry.word,
    word: entry.word,
    pinyin: entry.pinyin,
    pos: entry.pos,
    meaning: entry.translation,
    audioUrl: audioByWord.get(entry.word),
  }));
}
