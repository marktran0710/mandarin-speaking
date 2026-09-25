import { numericToToneMarked } from "./api";
import type { VocabAssessmentQuestion } from "./types";
import type { VocabQuizAssessmentQuestion } from "./quizTypes";
import type { VocabQuizEntry } from "./types";
import { quizConceptId } from "./quizTypes";

export function normalizeQuizAnswer(text: string): string {
  return text.normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[\s\p{P}\p{S}_]+/gu, "");
}
export function assessmentAnswerIsCorrect(question: VocabQuizAssessmentQuestion, submittedAnswer: string): boolean {
  const accepted = question.acceptedAnswers.length > 0 ? question.acceptedAnswers : [question.correctAnswer];
  // The pinyin-typing round stores tone-marked readings ("kā fēi tīng"), but a
  // learner typing on a plain keyboard writes tone numbers ("ka1 fei1 ting1").
  // Fold numeric tones to the marked form first so both spellings match. Tone
  // is still required — a toneless "kafeiting" produces no marks and won't
  // match the marked accepted answer. Scoped to the pinyin round so Chinese
  // free-text answers (Round 3) are never rewritten.
  const candidates = question.assessment.questionType === "character_to_pinyin_typing"
    ? [submittedAnswer, numericToToneMarked(submittedAnswer)]
    : [submittedAnswer];
  return accepted.some((answer) => candidates.some(
    (candidate) => normalizeQuizAnswer(answer) === normalizeQuizAnswer(candidate),
  ));
}


export interface RoundCoverageResult { valid: boolean; errors: string[]; }

/** Validate count, uniqueness, and lesson membership before a round starts. */
export function validateRoundCoverage({ lessonVocabulary, roundQuestions }: { lessonVocabulary: VocabQuizEntry[]; roundQuestions: VocabAssessmentQuestion[] }): RoundCoverageResult {
  const expected = new Set(lessonVocabulary.map((entry) => entry.wordId ?? quizConceptId(entry.word)));
  const seen = new Set<string>();
  const errors: string[] = [];
  if (roundQuestions.length !== expected.size) errors.push(`ROUND_COUNT expected ${expected.size}, found ${roundQuestions.length}`);
  roundQuestions.forEach((question) => {
    if (seen.has(question.wordId)) errors.push(`DUPLICATE_WORD ${question.wordId}`);
    seen.add(question.wordId);
    if (!expected.has(question.wordId)) errors.push(`EXTRA_WORD ${question.wordId}`);
    if (!question.questionId || !question.correctAnswer || !question.targetWord) errors.push(`INVALID_QUESTION ${question.wordId}`);
  });
  expected.forEach((wordId) => { if (!seen.has(wordId)) errors.push(`MISSING_WORD ${wordId}`); });
  return { valid: errors.length === 0, errors };
}
