import type {
  DiagnosticStatus,
  WordProsody,
  WordProsodySyllable,
} from "../../components/story-recorder/StoryRecorder";
import { toPinyin, toPinyinSyllables } from "@entities/vocabulary";

export type WordAlignmentStatus = DiagnosticStatus | "NEUTRAL";

export interface WordAlignmentItem {
  key: string;
  hanzi: string;
  pinyin?: string;
  status: WordAlignmentStatus;
  note?: string;
}

type PinyinSyllable = WordProsodySyllable & { pinyin?: string };

function syllablePinyin(word: WordProsody): string {
  const supplied = (word.syllables ?? [])
    .map((syllable) => (syllable as PinyinSyllable).pinyin?.trim() ?? "")
    .filter(Boolean);

  return supplied.length === (word.syllables?.length ?? 0) && supplied.length > 0
    ? supplied.join(" ")
    : toPinyinSyllables(word.token).join(" ") || toPinyin(word.token);
}

function isNeutralWord(word: WordProsody): boolean {
  const syllables = word.syllables ?? [];
  return syllables.length > 0 && syllables.every((syllable) => (
    syllable.score_provenance === "neutral_not_measured" || syllable.tone === 5
  ));
}

function isNotScoredWord(word: WordProsody): boolean {
  const syllables = word.syllables ?? [];
  return syllables.length > 0 && syllables.every((syllable) => (
    syllable.score_provenance === "not_scored"
      || syllable.score_provenance === "constant_short_segment"
      || syllable.passed === null
      || syllable.passed === undefined
  ));
}

function fallbackStatus(word: WordProsody): WordAlignmentStatus {
  if (isNeutralWord(word)) return "NEUTRAL";
  if (isNotScoredWord(word)) return "INVALID_AUDIO";

  const syllables = word.syllables ?? [];
  const syllableStatuses = syllables
    .map((syllable) => syllable.diagnostic_status)
    .filter((status): status is DiagnosticStatus => Boolean(status));
  if (syllableStatuses.includes("INVALID_AUDIO")) return "INVALID_AUDIO";
  if (syllableStatuses.includes("INCORRECT")) return "INCORRECT";
  if (syllableStatuses.includes("UNCERTAIN")) return "UNCERTAIN";
  if (syllableStatuses.length > 0 && syllableStatuses.every((status) => status === "CORRECT")) return "CORRECT";
  if (word.judged === false) return "INVALID_AUDIO";
  if (word.passed === true) return "CORRECT";
  if (word.passed === false) return "INCORRECT";
  return "UNCERTAIN";
}

function wordStatus(word: WordProsody): WordAlignmentStatus {
  if (isNeutralWord(word)) return "NEUTRAL";
  if (isNotScoredWord(word)) return "INVALID_AUDIO";
  const canonical = word.verdict ?? word.diagnostic_status;
  if (canonical) return canonical;
  return fallbackStatus(word);
}

/**
 * Maps the backend's already-decided word/syllable diagnostics into the
 * learner-facing chip contract. This function deliberately does not score,
 * threshold, or reorder anything: word_prosody order is the display order.
 */
export function mapWordProsodyToAlignment(words?: WordProsody[] | null): WordAlignmentItem[] {
  return (words ?? []).map((word) => ({
    key: `${word.index}-${word.token}`,
    hanzi: word.token,
    pinyin: syllablePinyin(word) || undefined,
    status: wordStatus(word),
    note: word.feedback?.trim() || undefined,
  }));
}
