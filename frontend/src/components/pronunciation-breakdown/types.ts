import type { AssistiveFeedbackSyllable } from "../../utils/assistiveFeedback";
import type { WordProsody, WordProsodySyllable } from "../story-recorder/StoryRecorder";

export interface BreakdownRow {
  key: string;
  char: string;
  pinyin: string;
  syllable: WordProsodySyllable;
  word: WordProsody;
}

export interface BreakdownGroup {
  key: string;
  token: string;
  pinyin: string;
  rows: BreakdownRow[];
}

export interface PhraseBreakdownGroup {
  key: string;
  text: string;
  words: BreakdownGroup[];
  passed: boolean | null;
  uncertain: boolean;
}

export interface PronunciationBreakdownProps {
  words: WordProsody[];
  targetText?: string;
  transcription?: string;
  teacherPhrases?: string[];
  debug?: boolean;
  compact?: boolean;
  masteryCounts?: { passed: number; total: number };
  assistiveFeedback?: AssistiveFeedbackSyllable[] | null;
}
