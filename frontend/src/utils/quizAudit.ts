import { toPinyin } from "./pinyin";
import {
  CLOZE_BLANK,
  type VocabQuizEntry,
  type VocabQuizQuestion,
} from "../components/story-vocab-quiz/StoryVocabQuiz";

/** One rule violation found in a generated quiz question. `error` means the
 * question is broken for a student (missing/duplicate/second correct
 * answer); `warning` flags data that deserves a human look but doesn't make
 * the question unanswerable. */
export interface QuizAuditIssue {
  severity: "error" | "warning";
  rule: string;
  detail: string;
}

// Mirrors the quiz builder's own normalizeAnswer (StoryVocabQuiz.tsx): the
// "would a student read these as the same answer?" form. Kept in sync by the
// audit test's synthetic cases rather than by importing a private function.
function normalizeAnswer(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[.。!！?？]+$/u, "")
    .trim();
}

function normalizeReadingText(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

function entryReading(entry: VocabQuizEntry): string {
  return normalizeReadingText(entry.pinyin || toPinyin(entry.word));
}

function wordReading(word: string, entries: VocabQuizEntry[]): string {
  const entry = entries.find((e) => e.word === word);
  return entry ? entryReading(entry) : normalizeReadingText(toPinyin(word));
}

function entryByWord(entries: VocabQuizEntry[], word: string): VocabQuizEntry | undefined {
  return entries.find((e) => e.word === word);
}

/** The question's correct answer, as the raw option string it must appear
 * among `options`. */
function correctAnswerOf(question: VocabQuizQuestion): string {
  switch (question.kind) {
    case "translation":
      return question.correctTranslation;
    case "cloze":
    case "reverse":
    case "listening":
      return question.correctWord;
    case "pinyin":
      return question.correctPinyin;
    case "pos":
      return question.correctPos;
    case "synonym":
      return question.correctSynonym;
  }
}

/** Runs every mechanical single-correct-answer rule against one generated
 * question. `entries` is the same story vocabulary pool the question was
 * built from — the source of truth for "does this distractor secretly mean
 * the same thing?" checks. */
export function auditQuizQuestion(
  question: VocabQuizQuestion,
  entries: VocabQuizEntry[],
): QuizAuditIssue[] {
  const issues: QuizAuditIssue[] = [];
  const label = `[${question.kind}] ${question.word}`;
  const correct = correctAnswerOf(question);
  const options = question.options;

  // ── Every kind: correct answer present, options distinct, enough options ──
  if (!options.includes(correct)) {
    issues.push({
      severity: "error",
      rule: "correct-answer-missing",
      detail: `${label}: correct answer "${correct}" not among options [${options.join(" | ")}]`,
    });
  }

  const normalized = options.map(normalizeAnswer);
  const dupes = normalized.filter((opt, i) => normalized.indexOf(opt) !== i);
  if (dupes.length > 0) {
    issues.push({
      severity: "error",
      rule: "duplicate-options",
      detail: `${label}: options normalize to duplicates (${dupes.join(", ")}) in [${options.join(" | ")}]`,
    });
  }

  if (options.length < 2) {
    issues.push({
      severity: "error",
      rule: "too-few-options",
      detail: `${label}: only ${options.length} option(s)`,
    });
  } else if (options.length < 4) {
    issues.push({
      severity: "warning",
      rule: "under-four-options",
      detail: `${label}: ${options.length} options (story too small to fill 4)`,
    });
  }

  const normalizedCorrect = normalizeAnswer(correct);
  const distractors = options.filter((opt) => opt !== correct);

  // ── Kind-specific "disguised second correct answer" rules ──
  switch (question.kind) {
    case "reverse": {
      // Prompt is the English translation; any option word that a story
      // entry glosses with that same translation is a second right answer.
      const promptTranslation = normalizeAnswer(question.translation);
      for (const opt of distractors) {
        const optEntry = entryByWord(entries, opt);
        if (optEntry && normalizeAnswer(optEntry.translation) === promptTranslation) {
          issues.push({
            severity: "error",
            rule: "reverse-second-correct",
            detail: `${label}: option "${opt}" also translates as "${question.translation}"`,
          });
        }
      }
      break;
    }
    case "listening": {
      // Prompt is spoken. A distractor with the same reading (incl. tones)
      // is indistinguishable by ear; one with the same translation is
      // ambiguous the moment the student translates what they heard.
      const correctEntry = entryByWord(entries, question.correctWord);
      const correctReading = correctEntry
        ? entryReading(correctEntry)
        : normalizeReadingText(toPinyin(question.correctWord));
      for (const opt of distractors) {
        if (correctReading && wordReading(opt, entries) === correctReading) {
          issues.push({
            severity: "error",
            rule: "listening-homophone",
            detail: `${label}: option "${opt}" sounds identical to "${question.correctWord}" (${correctReading})`,
          });
        }
        const optEntry = entryByWord(entries, opt);
        if (
          correctEntry &&
          optEntry &&
          normalizeAnswer(optEntry.translation) === normalizeAnswer(correctEntry.translation)
        ) {
          issues.push({
            severity: "error",
            rule: "listening-same-translation",
            detail: `${label}: option "${opt}" shares the translation "${correctEntry.translation}"`,
          });
        }
      }
      break;
    }
    case "pinyin": {
      // Duplicate-after-reading-normalization traps ("hē chá" vs "hē  chá",
      // case differences) — indistinguishable readings shown side by side.
      const readings = options.map(normalizeReadingText);
      const readingDupes = readings.filter((r, i) => readings.indexOf(r) !== i);
      if (readingDupes.length > 0) {
        issues.push({
          severity: "error",
          rule: "pinyin-duplicate-readings",
          detail: `${label}: readings normalize to duplicates (${readingDupes.join(", ")})`,
        });
      }
      break;
    }
    case "cloze": {
      // The blanked sentence must actually hide the answer: exactly one
      // blank, and no remaining occurrence of the word (a sentence using the
      // word twice would leak the answer next to the blank).
      const blanks = question.sentenceWithBlank.split(CLOZE_BLANK).length - 1;
      if (blanks !== 1) {
        issues.push({
          severity: "error",
          rule: "cloze-blank-count",
          detail: `${label}: sentence has ${blanks} blanks: "${question.sentenceWithBlank}"`,
        });
      }
      if (question.sentenceWithBlank.includes(question.correctWord)) {
        issues.push({
          severity: "error",
          rule: "cloze-answer-leak",
          detail: `${label}: answer still visible in "${question.sentenceWithBlank}"`,
        });
      }
      // A story-word distractor meaning the same as the answer fits the
      // blank equally well.
      const answerEntry = entryByWord(entries, question.correctWord);
      for (const opt of distractors) {
        const optEntry = entryByWord(entries, opt);
        if (
          answerEntry &&
          optEntry &&
          normalizeAnswer(optEntry.translation) === normalizeAnswer(answerEntry.translation)
        ) {
          issues.push({
            severity: "error",
            rule: "cloze-second-correct",
            detail: `${label}: option "${opt}" means the same as the answer ("${answerEntry.translation}")`,
          });
        }
      }
      break;
    }
    case "synonym": {
      // The synonym answer must differ from the prompt word itself, and no
      // story-word distractor may share the prompt word's translation (that
      // word would be a synonym too).
      if (question.correctSynonym === question.word) {
        issues.push({
          severity: "error",
          rule: "synonym-is-prompt",
          detail: `${label}: correct synonym equals the prompt word`,
        });
      }
      const promptEntry = entryByWord(entries, question.word);
      for (const opt of distractors) {
        const optEntry = entryByWord(entries, opt);
        if (
          promptEntry &&
          optEntry &&
          normalizeAnswer(optEntry.translation) === normalizeAnswer(promptEntry.translation)
        ) {
          issues.push({
            severity: "error",
            rule: "synonym-second-correct",
            detail: `${label}: option "${opt}" shares the prompt's translation ("${promptEntry.translation}")`,
          });
        }
      }
      break;
    }
    case "translation": {
      // A distractor equal to another story translation is fine (it's
      // wrong for THIS word) — but a distractor that normalizes to the
      // correct translation is a duplicate, covered above. Nothing extra
      // mechanical here; near-synonym English distractors are the semantic
      // review's job.
      break;
    }
    case "pos":
      break;
  }

  // Correct answer accidentally duplicated among distractors in raw form is
  // covered by duplicate-options; also catch normalized-equal distractors
  // for non-listening kinds uniformly.
  for (const opt of distractors) {
    if (normalizeAnswer(opt) === normalizedCorrect) {
      issues.push({
        severity: "error",
        rule: "distractor-equals-correct",
        detail: `${label}: distractor "${opt}" reads as the correct answer "${correct}"`,
      });
    }
  }

  return issues;
}

/** Story-data checks that don't depend on any particular generated question:
 * authored pinyin that disagrees with the computed reading (possible typo —
 * or a legitimate multi-reading word, hence warning), and two different
 * words glossed with the identical translation (forces every builder onto
 * its same-translation guard; worth a human look). */
export function auditQuizEntries(entries: VocabQuizEntry[]): QuizAuditIssue[] {
  const issues: QuizAuditIssue[] = [];

  for (const entry of entries) {
    if (!entry.pinyin) continue;
    // Compare with ALL spaces removed: authored pinyin joins syllables
    // ("xiàkè") while the computed reading spaces them ("xià kè") — that
    // difference is convention, not a typo. What's left after despacing is
    // real signal: wrong tones, missing syllables, or a different word's
    // reading entirely. (Multi-reading characters still produce some noise
    // — 樂 yuè/lè — hence warning, not error.)
    const despace = (s: string) => normalizeReadingText(s).replace(/\s+/g, "");
    const computed = despace(toPinyin(entry.word));
    if (computed && despace(entry.pinyin) !== computed) {
      issues.push({
        severity: "warning",
        rule: "pinyin-mismatch",
        detail: `${entry.word}: authored "${entry.pinyin}" vs computed "${computed}" (typo or multi-reading word)`,
      });
    }
  }

  const byTranslation = new Map<string, string[]>();
  for (const entry of entries) {
    const key = normalizeAnswer(entry.translation);
    byTranslation.set(key, [...(byTranslation.get(key) ?? []), entry.word]);
  }
  for (const [translation, words] of byTranslation) {
    if (words.length > 1) {
      issues.push({
        severity: "warning",
        rule: "shared-translation",
        detail: `"${translation}" is the translation of ${words.length} words: ${words.join("、")}`,
      });
    }
  }

  return issues;
}
