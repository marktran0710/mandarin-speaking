import { toPinyin } from "./pinyin";
import type {
  VocabQuizEntry,
  VocabQuizQuestion,
  VocabQuizMode,
} from "../components/story-vocab-quiz/StoryVocabQuiz";

export type QuizQuestionKind = VocabQuizQuestion["kind"];

export interface QuizSessionIssue {
  rule: "duplicate-question" | "duplicate-concept" | "forward-answer-leak";
  questionIndex: number;
  relatedQuestionIndex?: number;
  detail: string;
}

export interface QuizSessionPlan {
  questions: VocabQuizQuestion[];
  requestedCount: number;
  reducedCount: number;
}

export interface QuizQuestionBuildContext {
  distractorEntries: VocabQuizEntry[];
  excludedKinds: ReadonlySet<QuizQuestionKind>;
  forbiddenAnswers: ReadonlySet<string>;
}

export type QuizQuestionFactory = (
  entry: VocabQuizEntry,
  mode: VocabQuizMode,
  context: QuizQuestionBuildContext,
) => VocabQuizQuestion | null;

const ALL_KINDS: QuizQuestionKind[] = [
  "translation",
  "cloze",
  "pinyin",
  "pos",
  "synonym",
  "reverse",
  "listening",
];

/** Normal form used only for cross-question comparisons. */
export function normalizeQuizExposure(text: string): string {
  return text
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[\p{P}\p{S}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function hasHan(text: string): boolean {
  return /\p{Script=Han}/u.test(text);
}

/**
 * True when a visible prompt/option contains an answer. Chinese answers use
 * substring matching; alphabetic answers use token boundaries so a short
 * answer such as "car" does not falsely match "scarf".
 */
export function visibleTextContainsAnswer(visible: string, answer: string): boolean {
  const haystack = normalizeQuizExposure(visible);
  const needle = normalizeQuizExposure(answer);
  if (!haystack || !needle) return false;
  if (hasHan(needle)) return haystack.includes(needle);
  return ` ${haystack} `.includes(` ${needle} `);
}

export function quizQuestionAnswer(question: VocabQuizQuestion): string {
  switch (question.kind) {
    case "translation":
      return question.correctTranslation;
    case "pinyin":
      return question.correctPinyin;
    case "pos":
      return question.correctPos;
    case "synonym":
      return question.correctSynonym;
    case "cloze":
    case "reverse":
    case "listening":
      return question.correctWord;
  }
}

export function quizQuestionPrompt(question: VocabQuizQuestion): string {
  switch (question.kind) {
    case "cloze":
      return question.sentenceWithBlank;
    case "reverse":
      return question.translation;
    default:
      return question.word;
  }
}

/** Everything a learner can see or hear before moving to the next item. */
export function quizQuestionExposure(question: VocabQuizQuestion): string[] {
  return [quizQuestionPrompt(question), ...question.options];
}

export function quizQuestionFingerprint(question: VocabQuizQuestion): string {
  return [
    question.kind,
    normalizeQuizExposure(question.word),
    normalizeQuizExposure(quizQuestionPrompt(question)),
    normalizeQuizExposure(quizQuestionAnswer(question)),
  ].join("|");
}

function entryIdentityAliases(entry: VocabQuizEntry): Set<string> {
  const aliases = [entry.word, entry.translation, entry.pinyin || toPinyin(entry.word)];
  for (const candidate of entry.aiSynonym ?? []) aliases.push(candidate.synonym);
  return new Set(aliases.map(normalizeQuizExposure).filter(Boolean));
}

function entryPotentialAnswers(entry: VocabQuizEntry): Set<string> {
  const answers = entryIdentityAliases(entry);
  if (entry.pos) answers.add(normalizeQuizExposure(entry.pos));
  return answers;
}

function intersects(left: ReadonlySet<string>, right: ReadonlySet<string>): boolean {
  for (const value of left) if (right.has(value)) return true;
  return false;
}

function uniqueEntries(entries: VocabQuizEntry[]): VocabQuizEntry[] {
  const seen = new Set<string>();
  return entries.filter((entry) => {
    const key = normalizeQuizExposure(entry.word);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Audits relationships between questions, not just each item in isolation. */
export function auditQuizSession(questions: VocabQuizQuestion[]): QuizSessionIssue[] {
  const issues: QuizSessionIssue[] = [];
  const fingerprints = new Map<string, number>();
  const concepts = new Map<string, number>();

  questions.forEach((question, index) => {
    const fingerprint = quizQuestionFingerprint(question);
    const duplicateAt = fingerprints.get(fingerprint);
    if (duplicateAt !== undefined) {
      issues.push({
        rule: "duplicate-question",
        questionIndex: index,
        relatedQuestionIndex: duplicateAt,
        detail: `Question ${index + 1} duplicates question ${duplicateAt + 1}.`,
      });
    } else {
      fingerprints.set(fingerprint, index);
    }

    const concept = normalizeQuizExposure(question.word);
    const conceptAt = concepts.get(concept);
    if (conceptAt !== undefined) {
      issues.push({
        rule: "duplicate-concept",
        questionIndex: index,
        relatedQuestionIndex: conceptAt,
        detail: `Concept "${question.word}" is tested more than once.`,
      });
    } else {
      concepts.set(concept, index);
    }
  });

  for (let later = 1; later < questions.length; later += 1) {
    const answer = quizQuestionAnswer(questions[later]);
    for (let earlier = 0; earlier < later; earlier += 1) {
      if (quizQuestionExposure(questions[earlier]).some((text) => visibleTextContainsAnswer(text, answer))) {
        issues.push({
          rule: "forward-answer-leak",
          questionIndex: earlier,
          relatedQuestionIndex: later,
          detail: `Question ${earlier + 1} reveals the answer to question ${later + 1}: "${answer}".`,
        });
      }
    }
  }

  return issues;
}

/**
 * Builds a complete quiz before it is shown. Targets are unique and aliases
 * that represent the same concept are collapsed. Each earlier item is built
 * without future target entries as distractors, then checked against every
 * possible answer form of the remaining targets.
 */
export function planQuizSession(
  entries: VocabQuizEntry[],
  mode: VocabQuizMode,
  requestedCount: number,
  buildQuestion: QuizQuestionFactory,
): QuizSessionPlan {
  const pool = uniqueEntries(entries);
  const targets: VocabQuizEntry[] = [];
  const reservedAliases = new Set<string>();

  for (const entry of pool) {
    if (targets.length >= requestedCount) break;
    const aliases = entryIdentityAliases(entry);
    if (intersects(aliases, reservedAliases)) continue;
    targets.push(entry);
    aliases.forEach((alias) => reservedAliases.add(alias));
  }

  const targetWords = new Set(targets.map((entry) => normalizeQuizExposure(entry.word)));
  const nonTargets = pool.filter((entry) => !targetWords.has(normalizeQuizExposure(entry.word)));
  const questions: VocabQuizQuestion[] = [];
  const fingerprints = new Set<string>();
  const previousExposure: string[] = [];
  const pastTargets: VocabQuizEntry[] = [];

  targets.forEach((entry, targetIndex) => {
    const futureAnswers = new Set<string>();
    targets.slice(targetIndex + 1).forEach((future) => {
      entryPotentialAnswers(future).forEach((answer) => futureAnswers.add(answer));
    });

    const distractorEntries = uniqueEntries([entry, ...pastTargets, ...nonTargets]);
    const excludedKinds = new Set<QuizQuestionKind>();
    let accepted: VocabQuizQuestion | null = null;

    while (excludedKinds.size < ALL_KINDS.length) {
      const candidate = buildQuestion(entry, mode, {
        distractorEntries,
        excludedKinds,
        forbiddenAnswers: futureAnswers,
      });
      if (!candidate) break;

      const answer = quizQuestionAnswer(candidate);
      const exposure = quizQuestionExposure(candidate);
      const fingerprint = quizQuestionFingerprint(candidate);
      const leakedPreviously = previousExposure.some((text) => visibleTextContainsAnswer(text, answer));
      const leaksFuture = [...futureAnswers].some((futureAnswer) =>
        exposure.some((text) => visibleTextContainsAnswer(text, futureAnswer)),
      );

      if (!fingerprints.has(fingerprint) && !leakedPreviously && !leaksFuture) {
        accepted = candidate;
        break;
      }
      excludedKinds.add(candidate.kind);
    }

    if (accepted) {
      questions.push(accepted);
      fingerprints.add(quizQuestionFingerprint(accepted));
      previousExposure.push(...quizQuestionExposure(accepted));
      pastTargets.push(entry);
    }
  });

  const audit = auditQuizSession(questions);
  if (audit.length > 0) {
    throw new Error(`Quiz session planner produced an invalid session: ${audit[0].detail}`);
  }

  return {
    questions,
    requestedCount,
    reducedCount: Math.max(0, requestedCount - questions.length),
  };
}
