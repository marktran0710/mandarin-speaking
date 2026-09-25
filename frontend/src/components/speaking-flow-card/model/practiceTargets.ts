import type { WordProsody } from "../../story-recorder/StoryRecorder";

/** Pure logic split out of the deleted SpeakingResultsFlow.helpers.tsx —
 * that file mixed this with presentation components that no longer exist.
 * analyzeSpeakingResult (SpeakingResultsFlow.analysis.ts) depends on this;
 * do not fold presentation back in here. */

export type ResultsStep = "selfEval" | "overview" | "fix" | "practice";

export interface PracticeTarget {
  /** Stable identity for the word-level record or an unmatched backend part. */
  key: string;
  label: string;
  word: WordProsody | null;
}

export function practiceWordKey(word: WordProsody): string {
  return `word:${word.index}`;
}

/**
 * Join the backend's learner-facing practice parts to the exact word-level
 * records that contain the contour, tone and feedback. The old implementation
 * used an index into a separately filtered/sorted list; when a backend part
 * was uncertain or otherwise filtered out, the index stayed at zero and the
 * first word was shown instead.
 */
export function buildPracticeTargets(parts: string[], words: WordProsody[]): PracticeTarget[] {
  const usedWordKeys = new Set<string>();

  return parts.map((rawPart, partIndex) => {
    const label = rawPart.trim();
    const word = words.find((candidate) => {
      const key = practiceWordKey(candidate);
      return candidate.token === label && !usedWordKeys.has(key);
    });

    if (word) {
      const key = practiceWordKey(word);
      usedWordKeys.add(key);
      return { key, label, word };
    }

    return { key: `part:${partIndex}:${label}`, label, word: null };
  });
}
