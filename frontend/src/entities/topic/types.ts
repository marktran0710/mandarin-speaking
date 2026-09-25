import type { ConversationTurn } from "../conversation";
import type { CustomTeacherStory, StoryDifficultyLevel, VocabGroup } from "../story";
import type { VocabAssessmentQuestion } from "../vocabulary";

export interface Topic {
  id: string;
  name: string;
  description?: string;
  skillFocus?: string;
  level?: string;
  images: string[];
  conversationTurns?: ConversationTurn[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
  phrases?: Record<number, string[]>;
  phrasesTranslation?: Record<number, string[]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenAudioSources?: Record<number, "teacher">;
  listenScripts?: Record<number, string>;
  vocabularyAudioUrls?: Record<number, (string | null)[]>;
  vocabularyReferenceCurves?: Record<number, number[][]>;
  sentenceReferenceCurves?: Record<number, Record<string, number[]>>;
  lessonNumber?: number | null;
  lessonSubOrder?: number | null;
  difficultyLevel?: StoryDifficultyLevel;
  sourceStory?: CustomTeacherStory;
  vocabAssessment?: VocabAssessmentQuestion[];
}

export interface TopicStartOptions {
  startAtQuiz?: boolean;
}

export interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic, options?: TopicStartOptions) => void;
  publishedTopics?: Topic[];
}
