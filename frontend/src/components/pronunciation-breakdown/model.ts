import { toPinyin, toPinyinSyllables } from "../../utils/pinyin";
import {
  scoreScriptChunks, scriptAlignmentText, scriptDisplayChars, splitTeacherScriptIntoPhrases,
} from "../../utils/scriptAlignment";
import type { WordProsody, WordProsodySyllable } from "../story-recorder/StoryRecorder";
import { NEUTRAL_LABEL, TONE_STATUS } from "./constants";
import type { BreakdownGroup, PhraseBreakdownGroup } from "./types";

export function isNeutral(syllable: WordProsodySyllable): boolean {
  return syllable.score_provenance === "neutral_not_measured" || syllable.tone === 5;
}

export function isNotScored(syllable: WordProsodySyllable): boolean {
  if (isNeutral(syllable)) return false;
  return syllable.passed === null || syllable.passed === undefined || syllable.score_provenance === "not_scored" || syllable.score_provenance === "constant_short_segment";
}

export function referenceEvidenceAccepted(word?: WordProsody): boolean {
  return Boolean(word?.reference_source === "real_voice" && word.judged !== false && typeof word.shape_accuracy === "number" && word.shape_accuracy >= 58);
}

function hasMeasuredToneEvidence(word: WordProsody): boolean {
  return (word.syllables ?? []).some((syllable) => !isNeutral(syllable) && !isNotScored(syllable) && syllable.passed !== null && syllable.passed !== undefined);
}

function isDisplayFailure(word: WordProsody): boolean {
  if (word.diagnostic_status === "INVALID_AUDIO" || word.diagnostic_status === "INCORRECT") return true;
  if (word.judged === false || word.diagnostic_status === "UNCERTAIN" || word.diagnostic_status === "CORRECT") return false;
  return word.passed === false;
}

function phraseStatus(phraseWordRecords: WordProsody[]): Pick<PhraseBreakdownGroup, "passed" | "uncertain"> {
  const hasHardFailure = phraseWordRecords.some(isDisplayFailure);
  const hasMeasuredEvidence = phraseWordRecords.some(hasMeasuredToneEvidence);
  return {
    passed: phraseWordRecords.length === 0 ? null : hasHardFailure ? false : hasMeasuredEvidence ? true : null,
    uncertain: phraseWordRecords.length > 0 && !hasHardFailure && !hasMeasuredEvidence,
  };
}

export function statusLabel(syllable: WordProsodySyllable, referenceAccepted = false) {
  if (isNeutral(syllable)) return NEUTRAL_LABEL;
  if (isNotScored(syllable)) return TONE_STATUS.INVALID_AUDIO;
  const status = referenceAccepted && syllable.diagnostic_status === "INCORRECT" ? "CORRECT" : syllable.diagnostic_status;
  if (status) return TONE_STATUS[status];
  if (syllable.passed === null || syllable.passed === undefined) return TONE_STATUS.UNCERTAIN;
  return syllable.passed ? TONE_STATUS.CORRECT : { ...TONE_STATUS.INCORRECT, zh: "沒過", en: "Did not pass" };
}

export function breakdownGroups(words: WordProsody[]): BreakdownGroup[] {
  const groups: BreakdownGroup[] = [];
  for (const word of words) {
    const syllables = word.syllables ?? [];
    if (syllables.length === 0) continue;
    const pinyin = toPinyinSyllables(word.token);
    groups.push({
      key: `${word.index}-${word.token}`, token: word.token, pinyin: toPinyin(word.token),
      rows: syllables.map((syllable, index) => ({ key: `${word.index}-${index}-${syllable.char}`, char: syllable.char, pinyin: pinyin[index] ?? "", syllable, word })),
    });
  }
  return groups;
}

export function displayWordsForScript(words: WordProsody[], targetText?: string, transcription?: string): WordProsody[] {
  if (!targetText?.trim() || !transcription?.trim()) return words;
  const displayChars = scriptDisplayChars(targetText, transcription);
  let spokenCursor = 0;
  return words.map((word) => {
    const tokenChars = Array.from(scriptAlignmentText(word.token));
    const replacements = displayChars.slice(spokenCursor, spokenCursor + tokenChars.length);
    spokenCursor += tokenChars.length;
    if (replacements.length === 0 || !tokenChars.some((char, index) => replacements[index] && replacements[index] !== char)) return word;
    return { ...word, token: replacements.join(""), syllables: word.syllables?.map((syllable, index) => ({ ...syllable, char: replacements[index] ?? syllable.char })) };
  });
}

export function breakdownPhraseGroups(groups: BreakdownGroup[], targetText?: string, transcription?: string, teacherPhrases?: string[]): PhraseBreakdownGroup[] {
  const phrases = (teacherPhrases?.length ? teacherPhrases : splitTeacherScriptIntoPhrases(targetText)).filter(Boolean);
  if (phrases.length <= 1) {
    return [{ key: "phrase-0", text: phrases[0] ?? "", words: groups, ...phraseStatus(groups.flatMap((group) => group.rows.map((row) => row.word))) }];
  }
  const words = groups.map((group) => group.rows[0]?.word).filter(Boolean);
  const scores = scoreScriptChunks(targetText, transcription, words, phrases);
  const phraseWords = phrases.map<BreakdownGroup[]>(() => []);
  const phraseIndexByWord = new Map<WordProsody, number>();
  scores.forEach((score, phraseIndex) => score.tokens.forEach((word) => phraseIndexByWord.set(word, phraseIndex)));
  let fallbackPhraseIndex = 0;
  let fallbackChars = 0;
  const phraseCharCounts = phrases.map((phrase) => Array.from(phrase).filter((char) => /[\p{L}\p{N}]/u.test(char)).length);
  groups.forEach((group) => {
    const word = group.rows[0]?.word;
    let phraseIndex = word ? phraseIndexByWord.get(word) : undefined;
    if (phraseIndex === undefined) {
      const wordChars = Array.from(group.token).filter((char) => /[\p{L}\p{N}]/u.test(char)).length;
      while (fallbackPhraseIndex < phrases.length - 1 && fallbackChars >= phraseCharCounts[fallbackPhraseIndex]) {
        fallbackChars -= phraseCharCounts[fallbackPhraseIndex]; fallbackPhraseIndex += 1;
      }
      phraseIndex = fallbackPhraseIndex; fallbackChars += wordChars;
    }
    phraseWords[Math.min(phraseIndex, phrases.length - 1)].push(group);
  });
  return phrases.map((text, index) => {
    const phraseWordRecords = phraseWords[index].flatMap((group) => group.rows.map((row) => row.word)).filter(Boolean);
    return { key: `phrase-${index}-${text}`, text, words: phraseWords[index], ...phraseStatus(phraseWordRecords) };
  });
}

export function countByBucket(groups: BreakdownGroup[]): Record<string, number> {
  const counts: Record<string, number> = { correct: 0, uncertain: 0, incorrect: 0, invalid: 0, neutral: 0, not_scored: 0 };
  for (const group of groups) for (const { syllable, word } of group.rows) {
    if (isNeutral(syllable)) { counts.neutral += 1; continue; }
    if (isNotScored(syllable)) { counts.not_scored += 1; counts.invalid += 1; continue; }
    switch (statusLabel(syllable, referenceEvidenceAccepted(word)).tone) {
      case "pass": counts.correct += 1; break;
      case "fail": counts.incorrect += 1; break;
      case "retry": counts.invalid += 1; break;
      case "uncertain": counts.uncertain += 1; break;
      default: if (syllable.passed) counts.correct += 1; else counts.incorrect += 1;
    }
  }
  return counts;
}
