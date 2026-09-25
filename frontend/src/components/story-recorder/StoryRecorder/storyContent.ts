import type { CustomTeacherStory, StoryDifficultyLevel } from "../../../utils/teacherStories";
import type { VocabAssessmentQuestion } from "../../story-vocab-quiz/model";
import type { ConversationTurn } from "./conversation";

export type SpeechModel = "webspeech" | "ctwhisper" | "groq" | "vibevoice" | "openai";

export interface AiProviderOption {
  id: string;
  label: string;
  available: boolean;
}

interface VocabGroup {
  name: string;
  words: string[];
}

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

export function buildSceneReferenceCurves(
  topic: Pick<Topic, "vocabulary" | "vocabularyReferenceCurves" | "sentenceReferenceCurves">,
  sceneIndex: number,
): Record<string, number[]> | null {
  const byWord: Record<string, number[]> = { ...(topic.sentenceReferenceCurves?.[sceneIndex] || {}) };
  const words = topic.vocabulary[sceneIndex] || [];
  const curves = topic.vocabularyReferenceCurves?.[sceneIndex];
  if (curves && curves.length > 0) {
    words.forEach((word, index) => {
      const curve = curves[index];
      if (curve && curve.length > 0 && !byWord[word]) byWord[word] = curve;
    });
  }
  return Object.keys(byWord).length > 0 ? byWord : null;
}

export function vocabTooltip(pos?: string, translation?: string): string | undefined {
  if (pos && translation) return `(${pos}) ${translation}`;
  if (pos) return `(${pos})`;
  return translation;
}
