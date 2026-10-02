export interface VocabQuizClozeCandidate {
  sentence: string;
  distractors: string[];
}

export interface VocabQuizSynonymCandidate {
  synonym: string;
  distractors: string[];
}

export type VocabAssessmentLevel = "easy" | "medium" | "hard";
export type VocabAssessmentRound = 1 | 2 | 3;

export interface VocabAssessmentQuestion {
  questionId: string;
  wordId: string;
  targetWord: string;
  pinyin: string;
  pos: string;
  simpleEnglishMeaning: string;
  /** Canonical bank field. Legacy level/weight values are read-only compatibility fields. */
  round?: VocabAssessmentRound;
  tier?: "tier1" | "tier2" | "tier3";
  level?: VocabAssessmentLevel;
  difficultyWeight?: 1 | 2 | 3;
  questionType: "basic_meaning_mcq" | "context_cloze_mcq" | "productive_recall" | "character_to_pinyin_typing" | "contextual_productive_recall";
  answerFormat: "single_choice" | "free_text";
  prompt: string;
  options: string[];
  correctAnswer: string;
  acceptedAnswers: string[];
  explanation: string;
  audioUrl?: string;
}

/** The three required learning dimensions (Know it / Say it / Use it). */
export type VocabQuizDimension = "meaning" | "pinyin" | "context";

export type VocabQuizQuestionKind = "translation" | "cloze" | "pinyin" | "pos" | "synonym" | "reverse" | "listening" | "assessment";

export interface VocabQuizEntry {
  word: string;
  translation: string;
  audioUrl?: string;
  lessonSentences?: readonly string[];
  wordId?: string;
  assessmentQuestions?: VocabAssessmentQuestion[];
  bktValidationStatus?: "APPROVED" | "DRAFT";
  bktSeenQuestionKinds?: ReadonlyArray<string>;
  /**
   * The dimension the SERVER says to practice next (practice.nextDimension).
   * This is the only corrective-targeting input: it is derived server-side
   * from the word's currently unresolved dimensions, never from a history of
   * failed question types, so selection and completion cannot disagree.
   */
  bktNextDimension?: VocabQuizDimension;
  bktObservationCount?: number;
  bktLastResponseAt?: string | null;
  pinyin?: string;
  pos?: string;
  aiDistractors?: string[];
  aiCloze?: VocabQuizClozeCandidate[];
  aiSynonym?: VocabQuizSynonymCandidate[];
  disabledQuestionKinds?: ReadonlyArray<"pinyin" | "reverse">;
}
