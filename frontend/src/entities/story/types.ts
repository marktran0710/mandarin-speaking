import type { ConversationTurn } from "../conversation";
import type { VocabAssessmentQuestion } from "../vocabulary";

export interface VocabGroup {
  name: string;
  words: string[];
}

export type StoryDifficultyLevel = "easy";

export interface StoryVocabulary {
  vocabulary: string;
  vocabularyPinyin: string;
  vocabularyPos: string;
  vocabularyTranslation: string;
}

export interface StoryPhrases {
  phrases: string;
  phrasesTranslation: string;
}

export type StoryVocabularyByLevel = Record<StoryDifficultyLevel, StoryVocabulary>;
export type StoryPhrasesByLevel = Record<StoryDifficultyLevel, StoryPhrases>;

export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: VocabGroup[];
  phrases?: string;
  phrasesTranslation?: string;
  vocabularyPinyin?: string;
  vocabularyPos?: string;
  vocabularyTranslation?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenAudioSource?: "teacher";
  listenScript?: string;
  vocabularyAudioUrls?: string;
  vocabularyReferenceCurves?: string;
  sentenceReferenceCurves?: string;
}

export interface CustomTeacherStory {
  id: string;
  title: string;
  frames: CustomStoryFrame[];
  conversationTurns?: ConversationTurn[];
  storyVocabulary?: StoryVocabularyByLevel;
  storyPhrases?: StoryPhrasesByLevel;
  published?: boolean;
  lessonNumber?: number | null;
  lessonSubOrder?: number | null;
  rubricScores?: Record<string, unknown> | null;
  vocabAssessment?: VocabAssessmentQuestion[];
}
