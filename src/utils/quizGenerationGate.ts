import {
  normalizeQuizExposure,
  visibleTextContainsAnswer,
} from "./quizSessionPlanner";

export interface GeneratedQuizVocabulary {
  word: string;
  translation: string;
}

export interface GeneratedDistractorResult {
  word: string;
  distractors: string[];
}

export interface GeneratedClozeResult {
  word: string;
  sentence: string;
  distractors: string[];
}

export interface GeneratedSynonymResult {
  word: string;
  synonym: string;
  distractors: string[];
}

export interface GeneratedQuizMaterial {
  distractors: GeneratedDistractorResult[];
  cloze: GeneratedClozeResult[];
  synonym: GeneratedSynonymResult[];
}

export interface ProtectedGeneratedQuizMaterial extends GeneratedQuizMaterial {
  removedCount: number;
}

function uniqueValues(values: string[], forbidden: ReadonlySet<string>): string[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    const key = normalizeQuizExposure(value);
    if (!key || forbidden.has(key) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function containsAnyAnswer(visible: string, answers: Iterable<string>): boolean {
  for (const answer of answers) {
    if (visibleTextContainsAnswer(visible, answer)) return true;
  }
  return false;
}

/**
 * Deterministic safety gate for the teacher's Generate Questions action.
 *
 * The model output is treated as untrusted: duplicate candidates, self leaks,
 * and values that are a known answer for another vocabulary item are removed
 * before the teacher can accept or persist them. Session ordering still goes
 * through quizSessionPlanner, which is the final forward-leak check.
 */
export function protectGeneratedQuizMaterial(
  vocabulary: GeneratedQuizVocabulary[],
  generated: GeneratedQuizMaterial,
): ProtectedGeneratedQuizMaterial {
  const wordAnswers = new Map<string, string>();
  const translationAnswers = new Set<string>();
  for (const entry of vocabulary) {
    const word = normalizeQuizExposure(entry.word);
    const translation = normalizeQuizExposure(entry.translation);
    if (word && !wordAnswers.has(word)) wordAnswers.set(word, entry.word.trim());
    if (translation) translationAnswers.add(translation);
  }

  const rawSynonymAnswers = new Set(
    generated.synonym
      .map((result) => normalizeQuizExposure(result.synonym))
      .filter(Boolean),
  );
  const chineseAnswers = new Set([...wordAnswers.keys(), ...rawSynonymAnswers]);
  let removedCount = 0;

  const distractors: GeneratedDistractorResult[] = [];
  const seenDistractorWords = new Set<string>();
  for (const result of generated.distractors) {
    const word = normalizeQuizExposure(result.word);
    if (!wordAnswers.has(word) || seenDistractorWords.has(word)) {
      removedCount += 1;
      continue;
    }
    seenDistractorWords.add(word);
    const safe = uniqueValues(result.distractors, translationAnswers);
    removedCount += result.distractors.length - safe.length;
    if (safe.length) distractors.push({ ...result, distractors: safe });
    else removedCount += 1;
  }

  const synonym: GeneratedSynonymResult[] = [];
  const seenSynonymWords = new Set<string>();
  const seenSynonymAnswers = new Set<string>();
  for (const result of generated.synonym) {
    const word = normalizeQuizExposure(result.word);
    const answer = normalizeQuizExposure(result.synonym);
    if (
      !wordAnswers.has(word) ||
      !answer ||
      chineseAnswers.has(answer) && wordAnswers.has(answer) ||
      seenSynonymWords.has(word) ||
      seenSynonymAnswers.has(answer)
    ) {
      removedCount += 1;
      continue;
    }
    seenSynonymWords.add(word);
    seenSynonymAnswers.add(answer);
    const forbidden = new Set(chineseAnswers);
    forbidden.add(word);
    forbidden.add(answer);
    const safe = uniqueValues(result.distractors, forbidden);
    removedCount += result.distractors.length - safe.length;
    if (safe.length) synonym.push({ ...result, distractors: safe });
    else removedCount += 1;
  }

  const promptAnswers = [
    ...wordAnswers.values(),
    ...synonym.map((result) => result.synonym),
  ];
  const cloze: GeneratedClozeResult[] = [];
  const seenClozeWords = new Set<string>();
  const seenClozePrompts = new Set<string>();
  for (const result of generated.cloze) {
    const word = normalizeQuizExposure(result.word);
    const target = wordAnswers.get(word);
    const prompt = target
      ? normalizeQuizExposure(result.sentence.replace(target, "____"))
      : "";
    const otherAnswers = promptAnswers.filter(
      (answer) => normalizeQuizExposure(answer) !== word,
    );
    if (
      !target ||
      !prompt ||
      result.sentence.split(target).length !== 2 ||
      containsAnyAnswer(result.sentence.replace(target, "____"), otherAnswers) ||
      seenClozeWords.has(word) ||
      seenClozePrompts.has(prompt)
    ) {
      removedCount += 1;
      continue;
    }
    seenClozeWords.add(word);
    seenClozePrompts.add(prompt);
    const forbidden = new Set(chineseAnswers);
    forbidden.add(word);
    const safe = uniqueValues(result.distractors, forbidden).filter(
      (value) => !visibleTextContainsAnswer(result.sentence, value),
    );
    removedCount += result.distractors.length - safe.length;
    if (safe.length) cloze.push({ ...result, distractors: safe });
    else removedCount += 1;
  }

  return { distractors, cloze, synonym, removedCount };
}
