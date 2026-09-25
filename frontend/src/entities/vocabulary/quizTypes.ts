import type {
  VocabAssessmentQuestion,
  VocabQuizQuestionKind,
} from "./types";
import type { TierMode } from "./progression";

export const CLOZE_BLANK = "____";

export interface VocabQuizTranslationQuestion {
  kind: "translation";
  word: string;
  correctTranslation: string;
  options: string[];
  isAiGenerated: boolean;
}
export interface VocabQuizClozeQuestion {
  kind: "cloze";
  word: string;
  sentenceWithBlank: string;
  correctWord: string;
  options: string[];
  isAiGenerated: true;
}

export interface VocabQuizPinyinQuestion {
  kind: "pinyin";
  word: string;
  correctPinyin: string;
  options: string[];
  isAiGenerated: false;
}

export interface VocabQuizPosQuestion {
  kind: "pos";
  word: string;
  correctPos: string;
  options: string[];
  isAiGenerated: false;
}

export interface VocabQuizSynonymQuestion {
  kind: "synonym";
  word: string;
  correctSynonym: string;
  options: string[];
  isAiGenerated: true;
}

export interface VocabQuizReverseQuestion {
  kind: "reverse";
  word: string;
  translation: string;
  correctWord: string;
  options: string[];
  isAiGenerated: boolean;
}

export interface VocabQuizListeningQuestion {
  kind: "listening";
  word: string;
  correctWord: string;
  options: string[];
  isAiGenerated: boolean;
}

export interface VocabQuizAssessmentQuestion {
  kind: "assessment";
  word: string;
  prompt: string;
  options: string[];
  correctAnswer: string;
  acceptedAnswers: string[];
  explanation: string;
  assessment: VocabAssessmentQuestion;
  isAiGenerated: false;
}

export type VocabQuizQuestion =
  | VocabQuizTranslationQuestion
  | VocabQuizClozeQuestion
  | VocabQuizPinyinQuestion
  | VocabQuizPosQuestion
  | VocabQuizSynonymQuestion
  | VocabQuizReverseQuestion
  | VocabQuizListeningQuestion
  | VocabQuizAssessmentQuestion;

export interface VocabQuizQuestionResult {
  word: string;
  correct: boolean;
  timeMs: number;
  /** Stable identity fields are optional so old attempts remain readable. */
  itemId?: string;
  conceptId?: string;
  questionKind?: VocabQuizQuestionKind | VocabAssessmentQuestion["questionType"];
  roundType?: "know_it" | "say_it" | "use_it";
  knowledgeDimension?: "meaning" | "pinyin_production" | "contextual_recall";
  activityType?: "diagnostic" | "personalized_practice" | "scheduled_maintenance" | "challenge" | "practice";
  level?: "easy" | "medium" | "hard";
  baseStoryId?: string;
  itemVersion?: string;
  isBktEligible?: boolean;
  bktEligibilityErrors?: string[];
  diagnosticExposureId?: string;
  assistedResponse?: boolean;
  bktValidationStatus?: "APPROVED" | "DRAFT";
  selectedAnswer?: string;
  correctAnswer?: string;
  presentedOptions?: string[];
  questionPrompt?: string;
  answeredAt?: string;
  questionIndex?: number;
  lessonId?: string;
  quizId?: string;
}

/** Normalized concept identity shared by all question types and story levels. */
export function quizConceptId(word: string): string {
  return word.normalize("NFKC").trim().replace(/\s+/g, " ");
}

/** Stable across option shuffles and question rerenders. */
export function quizItemId(
  baseStoryId: string,
  word: string,
  questionKind: VocabQuizQuestionKind,
  itemVersion = "v1",
): string {
  return [baseStoryId, quizConceptId(word), questionKind, itemVersion]
    .map((part) => encodeURIComponent(part))
    .join(":");
}

export type VocabQuizMode = TierMode | "free" | "weak_words" | "maintenance_review" | "challenge";

export interface VocabQuizSummary {
  mode: VocabQuizMode;
  totalQuestions: number;
  correctCount: number;
  totalTimeMs: number;
  questionResults: VocabQuizQuestionResult[];
}
