import type { CustomTeacherStory, StoryDifficultyLevel } from "../../utils/teacherStories";

export interface VocabGroup {
  name: string;
  words: string[];
}

export interface Topic {
  id: string;
  name: string;
  description: string;
  skillFocus: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
  phrases?: Record<number, string[]>;
  phrasesTranslation?: Record<number, string[]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  vocabularyDistractors?: Record<number, string[][]>;
  vocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  vocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  quizVocabulary?: Record<number, string[]>;
  quizVocabularyPinyin?: Record<number, string[]>;
  quizVocabularyPos?: Record<number, string[]>;
  quizVocabularyTranslation?: Record<number, string[]>;
  quizVocabularyDistractors?: Record<number, string[][]>;
  quizVocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  quizVocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  quizSuggestedAnswers?: Record<number, string>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenAudioSources?: Record<number, "teacher" | "tts">;
  listenScripts?: Record<number, string>;
  vocabularyAudioUrls?: Record<number, (string | null)[]>;
  vocabularyReferenceCurves?: Record<number, number[][]>;
  sentenceReferenceCurves?: Record<number, Record<string, number[]>>;
  lessonNumber?: number | null;
  lessonSubOrder?: number | null;
  difficultyLevel?: StoryDifficultyLevel;
  quizMaterialSource?: "live" | "approved";
  quizMaterialApproved?: boolean;
  sourceStory?: CustomTeacherStory;
}

export interface TopicStartOptions {
  startAtQuiz?: boolean;
}

export interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic, options?: TopicStartOptions) => void;
  onLevelSelect?: (
    topic: Topic,
    level: StoryDifficultyLevel,
    options?: TopicStartOptions,
  ) => void;
}
