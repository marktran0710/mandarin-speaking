// Which quiz questions a story can actually produce. Extracted from
// StoryRecorder because the lesson gate needs the same answer: a lesson is
// only finished once every story in it has earned ⭐⭐, which a story with
// no quiz could never do — so the gate has to know exactly which stories
// those are, not guess from a proxy like "has a translated word".

import { collectQuizEntries, type VocabQuizEntry } from "../components/StoryVocabQuiz";
import { applyExclusionsToWord, storyQuizExclusions } from "./quizExclusions";
import type { CustomTeacherStory } from "./teacherStories";

/** Just the story fields the quiz is built from. Structural on purpose:
 * TopicSelector and StoryRecorder each declare their own `Topic` and the
 * two have drifted (only one declares vocabularyLookalike), so naming
 * either of them here would reject the other. */
export interface QuizSourceTopic {
  images: string[];
  vocabulary: Record<number, string[]>;
  suggestedAnswers?: Record<number, string>;
  vocabularyTranslation?: Record<number, string[]>;
  vocabularyDistractors?: Record<number, string[][]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  vocabularyPos?: Record<number, string[]>;
  vocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  vocabularyLookalike?: Record<number, string[][]>;
  /** Present on teacher-authored topics (see teacherStories.ts's
   * storyToTopic) — carries quizExclusions so a teacher's Quiz Review marks
   * actually take effect here instead of only being saved and ignored. */
  sourceStory?: CustomTeacherStory;
}

/** Every glossed word across every scene, deduped — the pool the
 * pre-practice vocabulary quiz draws its questions from. Even a single
 * translated word is enough for a real question: buildQuizQuestions pads
 * out missing distractors with generic filler words. A word only qualifies
 * if it also appears in its scene's suggested-answer sentence (when one
 * exists) — confirms it's used in real context, not just an isolated
 * flashcard pair. */
export function topicQuizEntries(topic: QuizSourceTopic): VocabQuizEntry[] {
  const words: string[] = [];
  const translations: Array<string | undefined> = [];
  const suggestedAnswers: Array<string | undefined> = [];
  const aiDistractors: Array<string[] | undefined> = [];
  const pinyins: Array<string | undefined> = [];
  const aiCloze: Array<Array<{ sentence: string; distractors: string[] }> | undefined> = [];
  const partsOfSpeech: Array<string | undefined> = [];
  const aiSynonyms: Array<Array<{ synonym: string; distractors: string[] }> | undefined> = [];
  const aiLookalikes: Array<string[] | undefined> = [];
  const exclusions = topic.sourceStory ? storyQuizExclusions(topic.sourceStory) : [];
  topic.images.forEach((_, si) => {
    const sceneSuggestedAnswer = topic.suggestedAnswers?.[si];
    (topic.vocabulary[si] || []).forEach((word, i) => {
      const filtered = applyExclusionsToWord(
        word,
        {
          aiDistractors: topic.vocabularyDistractors?.[si]?.[i],
          aiCloze: topic.vocabularyCloze?.[si]?.[i],
          aiSynonyms: topic.vocabularySynonym?.[si]?.[i],
          aiLookalikes: topic.vocabularyLookalike?.[si]?.[i],
        },
        exclusions,
      );
      if (!filtered) return; // whole word excluded by the teacher
      words.push(word);
      translations.push(topic.vocabularyTranslation?.[si]?.[i]);
      suggestedAnswers.push(sceneSuggestedAnswer);
      aiDistractors.push(filtered.aiDistractors);
      pinyins.push(topic.vocabularyPinyin?.[si]?.[i]);
      aiCloze.push(filtered.aiCloze);
      partsOfSpeech.push(topic.vocabularyPos?.[si]?.[i]);
      aiSynonyms.push(filtered.aiSynonyms);
      aiLookalikes.push(filtered.aiLookalikes);
    });
  });
  return collectQuizEntries(
    words,
    translations,
    suggestedAnswers,
    aiDistractors,
    pinyins,
    aiCloze,
    partsOfSpeech,
    aiSynonyms,
    aiLookalikes,
  );
}

/** Whether this story runs a vocabulary quiz at all — the same test
 * StoryRecorder's `hasVocabQuiz` makes before gating speaking behind it. */
export function topicHasQuiz(topic: QuizSourceTopic): boolean {
  return topicQuizEntries(topic).length >= 1;
}
