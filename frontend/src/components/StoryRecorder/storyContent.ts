import type {
  VocabularyClozeUpdate,
  VocabularyDistractorUpdate,
  VocabularySynonymUpdate,
} from "../../services/database";
import type { CustomTeacherStory, StoryDifficultyLevel } from "../../utils/teacherStories";

const MAX_VOCAB_DISTRACTORS_PER_WORD = 8;
const MAX_VOCAB_CLOZE_PER_WORD = 4;
const MAX_VOCAB_SYNONYM_PER_WORD = 4;

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
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenAudioSources?: Record<number, "teacher" | "tts">;
  listenScripts?: Record<number, string>;
  vocabularyAudioUrls?: Record<number, (string | null)[]>;
  vocabularyReferenceCurves?: Record<number, number[][]>;
  sentenceReferenceCurves?: Record<number, Record<string, number[]>>;
  linear?: boolean;
  lessonNumber?: number | null;
  lessonSubOrder?: number | null;
  narrativeMode?: "story" | "describe" | "listen_retell";
  firstFrameIsExample?: boolean;
  difficultyLevel?: StoryDifficultyLevel;
  sourceStory?: CustomTeacherStory;
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

export interface DistractorGrowthCandidate {
  frameIndex: number;
  wordIndex: number;
  word: string;
  translation: string;
  context?: string;
  existing: string[];
}

export function planDistractorGrowth(topic: Pick<Topic, "images" | "vocabulary" | "vocabularyTranslation" | "vocabularyDistractors" | "suggestedAnswers">): DistractorGrowthCandidate[] {
  const candidates: DistractorGrowthCandidate[] = [];
  topic.images.forEach((_, frameIndex) => {
    (topic.vocabulary[frameIndex] || []).forEach((word, wordIndex) => {
      const translation = topic.vocabularyTranslation?.[frameIndex]?.[wordIndex];
      const existing = topic.vocabularyDistractors?.[frameIndex]?.[wordIndex] ?? [];
      if (translation && existing.length < MAX_VOCAB_DISTRACTORS_PER_WORD) candidates.push({ frameIndex, wordIndex, word, translation, context: topic.suggestedAnswers?.[frameIndex], existing });
    });
  });
  return candidates;
}

export function buildDistractorPatchUpdates(candidates: DistractorGrowthCandidate[], results: Array<{ word: string; distractors: string[] }>): VocabularyDistractorUpdate[] {
  const byWord = new Map(results.map((result) => [result.word, result.distractors]));
  return candidates.map((candidate) => ({ frameIndex: candidate.frameIndex, wordIndex: candidate.wordIndex, distractors: byWord.get(candidate.word) ?? [] })).filter((update) => update.distractors.length > 0);
}

export interface ClozeGrowthCandidate extends DistractorGrowthCandidate {}
export function planClozeGrowth(topic: Pick<Topic, "images" | "vocabulary" | "vocabularyTranslation" | "vocabularyCloze" | "suggestedAnswers">): ClozeGrowthCandidate[] {
  const candidates: ClozeGrowthCandidate[] = [];
  topic.images.forEach((_, frameIndex) => (topic.vocabulary[frameIndex] || []).forEach((word, wordIndex) => {
    const translation = topic.vocabularyTranslation?.[frameIndex]?.[wordIndex];
    const existing = topic.vocabularyCloze?.[frameIndex]?.[wordIndex] ?? [];
    if (translation && existing.length < MAX_VOCAB_CLOZE_PER_WORD) candidates.push({ frameIndex, wordIndex, word, translation, context: topic.suggestedAnswers?.[frameIndex], existing: existing.map((entry) => entry.sentence) });
  }));
  return candidates;
}

export function buildClozePatchUpdates(candidates: ClozeGrowthCandidate[], results: Array<{ word: string; sentence: string; distractors: string[] }>): VocabularyClozeUpdate[] {
  const byWord = new Map(results.map((result) => [result.word, result]));
  return candidates.map((candidate) => {
    const result = byWord.get(candidate.word);
    return { frameIndex: candidate.frameIndex, wordIndex: candidate.wordIndex, candidates: result ? [{ sentence: result.sentence, distractors: result.distractors }] : [] };
  }).filter((update) => update.candidates.length > 0);
}

export interface SynonymGrowthCandidate extends DistractorGrowthCandidate {}
export function planSynonymGrowth(topic: Pick<Topic, "images" | "vocabulary" | "vocabularyTranslation" | "vocabularySynonym" | "suggestedAnswers">): SynonymGrowthCandidate[] {
  const candidates: SynonymGrowthCandidate[] = [];
  topic.images.forEach((_, frameIndex) => (topic.vocabulary[frameIndex] || []).forEach((word, wordIndex) => {
    const translation = topic.vocabularyTranslation?.[frameIndex]?.[wordIndex];
    const existing = topic.vocabularySynonym?.[frameIndex]?.[wordIndex] ?? [];
    if (translation && existing.length < MAX_VOCAB_SYNONYM_PER_WORD) candidates.push({ frameIndex, wordIndex, word, translation, context: topic.suggestedAnswers?.[frameIndex], existing: existing.map((entry) => entry.synonym) });
  }));
  return candidates;
}

export function buildSynonymPatchUpdates(candidates: SynonymGrowthCandidate[], results: Array<{ word: string; synonym: string; distractors: string[] }>): VocabularySynonymUpdate[] {
  const byWord = new Map(results.map((result) => [result.word, result]));
  return candidates.map((candidate) => {
    const result = byWord.get(candidate.word);
    return { frameIndex: candidate.frameIndex, wordIndex: candidate.wordIndex, candidates: result ? [{ synonym: result.synonym, distractors: result.distractors }] : [] };
  }).filter((update) => update.candidates.length > 0);
}
