// Which quiz questions a story can actually produce. Extracted from
// StoryRecorder because the lesson gate needs the same answer: a lesson is
// only finished once every story in it has earned ⭐⭐, which a story with
// no quiz could never do — so the gate has to know exactly which stories
// those are, not guess from a proxy like "has a translated word".

import { collectQuizEntries, type VocabQuizEntry } from "../components/story-vocab-quiz/StoryVocabQuiz";
import { applyExclusionsToWord, storyQuizExclusions } from "./quizExclusions";
import { toPinyin } from "./pinyin";
import type { CustomTeacherStory } from "./teacherStories";
import type { VocabAssessmentQuestion } from "../components/story-vocab-quiz/model";

/** Just the story fields the quiz is built from. Structural on purpose:
 * TopicSelector and StoryRecorder each declare their own `Topic`, so naming
 * either of them here would reject the other. */
export interface QuizSourceTopic {
  quizMaterialSource?: "live" | "approved";
  quizMaterialApproved?: boolean;
  images: string[];
  vocabulary: Record<number, string[]>;
  suggestedAnswers?: Record<number, string>;
  vocabularyTranslation?: Record<number, string[]>;
  vocabularyDistractors?: Record<number, string[][]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  vocabularyPos?: Record<number, string[]>;
  vocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  quizVocabulary?: Record<number, string[]>;
  quizVocabularyTranslation?: Record<number, string[]>;
  quizVocabularyDistractors?: Record<number, string[][]>;
  quizVocabularyPinyin?: Record<number, string[]>;
  quizVocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  quizVocabularyPos?: Record<number, string[]>;
  quizVocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  quizSuggestedAnswers?: Record<number, string>;
  /** Present on teacher-authored topics (see teacherStories.ts's
   * storyToTopic) — carries quizExclusions so a teacher's Quiz Review marks
   * actually take effect here instead of only being saved and ignored. */
  sourceStory?: CustomTeacherStory;
  vocabAssessment?: VocabAssessmentQuestion[];
}

export interface QuizMaterialAuditIssue {
  sceneIndex: number;
  word?: string;
  field: string;
  message: string;
}

function normalizedQuizValue(value: string): string {
  return value.normalize("NFKC").trim().toLowerCase().replace(/\s+/g, " ");
}

/** Read-only audit used before material is trusted by a level's quiz. */
export function auditTopicQuizMaterial(topic: QuizSourceTopic): QuizMaterialAuditIssue[] {
  const wordsByScene = topic.quizVocabulary ?? topic.vocabulary;
  const translationsByScene = topic.quizVocabularyTranslation ?? topic.vocabularyTranslation;
  const pinyinByScene = topic.quizVocabularyPinyin ?? topic.vocabularyPinyin;
  const distractorsByScene = topic.quizVocabularyDistractors ?? topic.vocabularyDistractors;
  const clozeByScene = topic.quizVocabularyCloze ?? topic.vocabularyCloze;
  const synonymByScene = topic.quizVocabularySynonym ?? topic.vocabularySynonym;
  const issues: QuizMaterialAuditIssue[] = [];

  Object.entries(wordsByScene).forEach(([rawSceneIndex, words]) => {
    const sceneIndex = Number(rawSceneIndex);
    const translations = translationsByScene?.[sceneIndex] ?? [];
    const pinyins = pinyinByScene?.[sceneIndex] ?? [];
    const distractors = distractorsByScene?.[sceneIndex] ?? [];
    const cloze = clozeByScene?.[sceneIndex] ?? [];
    const synonyms = synonymByScene?.[sceneIndex] ?? [];
    const alignedArrays: Array<[string, number]> = [
      ["translation", translations.length],
      ["pinyin", pinyins.length],
      ["distractors", distractors.length],
      ["cloze", cloze.length],
      ["synonym", synonyms.length],
    ];
    alignedArrays.forEach(([field, length]) => {
      if (length > words.length) {
        issues.push({ sceneIndex, field, message: `${field} has more entries than canonical vocabulary` });
      }
    });

    words.forEach((word, wordIndex) => {
      const translation = translations[wordIndex]?.trim();
      if (!translation) {
        issues.push({ sceneIndex, word, field: "translation", message: "missing translation" });
      }
      if (!pinyins[wordIndex]?.trim() && !toPinyin(word) && /[\u4e00-\u9fff]/u.test(word)) {
        issues.push({ sceneIndex, word, field: "pinyin", message: "missing pinyin" });
      }
      const wordValue = normalizedQuizValue(word);
      const translationValue = normalizedQuizValue(translation || "");
      const badDistractor = (distractors[wordIndex] ?? []).find(
        (value) => normalizedQuizValue(value) === translationValue,
      );
      if (badDistractor) {
        issues.push({ sceneIndex, word, field: "distractors", message: "correct translation appears as a distractor" });
      }
      (cloze[wordIndex] ?? []).forEach((candidate) => {
        if (candidate.sentence.split(word).length !== 2) {
          issues.push({ sceneIndex, word, field: "cloze", message: "sentence does not contain the word exactly once" });
        }
        if ((candidate.distractors ?? []).some((value) => normalizedQuizValue(value) === wordValue)) {
          issues.push({ sceneIndex, word, field: "cloze", message: "answer appears as a distractor" });
        }
      });
      (synonyms[wordIndex] ?? []).forEach((candidate) => {
        const synonymValue = normalizedQuizValue(candidate.synonym);
        if (!synonymValue || synonymValue === wordValue) {
          issues.push({ sceneIndex, word, field: "synonym", message: "synonym is missing or equals the answer" });
        }
        if ((candidate.distractors ?? []).some((value) => {
          const normalized = normalizedQuizValue(value);
          return normalized === wordValue || normalized === synonymValue;
        })) {
          issues.push({ sceneIndex, word, field: "synonym", message: "answer appears as a distractor" });
        }
      });
    });
  });

  return issues;
}

/** Every glossed word across every scene, deduped — the pool the
 * pre-practice vocabulary quiz draws its questions from. Even a single
 * translated word is enough for a real question: buildQuizQuestions pads
 * out missing distractors with generic filler words. A word only qualifies
 * if it also appears in its scene's suggested-answer sentence (when one
 * exists) — confirms it's used in real context, not just an isolated
 * flashcard pair. */
export function topicQuizEntries(topic: QuizSourceTopic): VocabQuizEntry[] {
  if (topic.vocabAssessment?.length) {
    const byWord = new Map<string, VocabAssessmentQuestion[]>();
    topic.vocabAssessment.forEach((question) => {
      const questions = byWord.get(question.wordId) ?? [];
      questions.push(question);
      byWord.set(question.wordId, questions);
    });
    return Array.from(byWord.entries()).map(([wordId, assessmentQuestions]) => {
      const first = assessmentQuestions[0];
      return {
        word: first.targetWord,
        translation: first.simpleEnglishMeaning,
        wordId,
        pinyin: first.pinyin,
        pos: first.pos,
        assessmentQuestions,
        bktValidationStatus: "APPROVED",
      };
    });
  }
  const quizVocabulary = topic.quizVocabulary ?? topic.vocabulary;
  const quizSuggestedAnswers = topic.quizSuggestedAnswers ?? topic.suggestedAnswers;
  const quizTranslations = topic.quizVocabularyTranslation ?? topic.vocabularyTranslation;
  const quizDistractors = topic.quizVocabularyDistractors ?? topic.vocabularyDistractors;
  const quizPinyin = topic.quizVocabularyPinyin ?? topic.vocabularyPinyin;
  const quizCloze = topic.quizVocabularyCloze ?? topic.vocabularyCloze;
  const quizPos = topic.quizVocabularyPos ?? topic.vocabularyPos;
  const quizSynonym = topic.quizVocabularySynonym ?? topic.vocabularySynonym;
  const words: string[] = [];
  const translations: Array<string | undefined> = [];
  const suggestedAnswers: Array<string | undefined> = [];
  const aiDistractors: Array<string[] | undefined> = [];
  const pinyins: Array<string | undefined> = [];
  const aiCloze: Array<Array<{ sentence: string; distractors: string[] }> | undefined> = [];
  const partsOfSpeech: Array<string | undefined> = [];
  const aiSynonyms: Array<Array<{ synonym: string; distractors: string[] }> | undefined> = [];
  const disabledQuestionKinds: Array<Array<"pinyin" | "reverse"> | undefined> = [];
  const exclusions = topic.sourceStory ? storyQuizExclusions(topic.sourceStory) : [];
  topic.images.forEach((_, si) => {
    const sceneSuggestedAnswer = quizSuggestedAnswers?.[si];
    (quizVocabulary[si] || []).forEach((word, i) => {
      const filtered = applyExclusionsToWord(
        word,
        {
          aiDistractors: quizDistractors?.[si]?.[i],
          aiCloze: quizCloze?.[si]?.[i],
          aiSynonyms: quizSynonym?.[si]?.[i],
        },
        exclusions,
      );
      if (!filtered) return; // whole word excluded by the teacher
      words.push(word);
      translations.push(quizTranslations?.[si]?.[i]);
      suggestedAnswers.push(sceneSuggestedAnswer);
      aiDistractors.push(filtered.aiDistractors);
      // Chinese readings are resolved from the backend cache. Keep the old
      // field only for legacy topics whose key is an English gloss rather
      // than Chinese text, where it is the only available display value.
      const authoredPinyin = quizPinyin?.[si]?.[i]?.trim();
      // Computed Chinese readings are canonical; authored pinyin remains a
      // fallback for legacy/non-Chinese keys that have no computed reading.
      pinyins.push(toPinyin(word) || authoredPinyin);
      aiCloze.push(filtered.aiCloze);
      partsOfSpeech.push(quizPos?.[si]?.[i]);
      aiSynonyms.push(filtered.aiSynonyms);
      const disabled = exclusions
        .filter((exclusion) => exclusion.word === word && (exclusion.kind === "pinyin" || exclusion.kind === "reverse"))
        .map((exclusion) => exclusion.kind as "pinyin" | "reverse");
      disabledQuestionKinds.push(disabled.length > 0 ? Array.from(new Set(disabled)) : undefined);
    });
  });
  const entries = collectQuizEntries(
    words,
    translations,
    suggestedAnswers,
    aiDistractors,
    pinyins,
    aiCloze,
    partsOfSpeech,
    aiSynonyms,
    disabledQuestionKinds,
  );
  return entries.map((entry) => ({
    ...entry,
    bktValidationStatus: topic.quizMaterialSource === "approved" && topic.quizMaterialApproved === true ? "APPROVED" : "DRAFT",
  }));
}

/** Whether this story runs a vocabulary quiz at all — the same test
 * StoryRecorder's `hasVocabQuiz` makes before gating speaking behind it. */
export function topicHasQuiz(topic: QuizSourceTopic): boolean {
  return topicQuizEntries(topic).length >= 1;
}
