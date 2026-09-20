// @ts-nocheck
import { findLiveWordOccurrence } from "./model-core";

/** Minimal CSV parser: handles quoted fields, embedded commas, "" escapes,
 * and \r\n or \n line endings. No external dependency needed for a file
 * this small and fully teacher-controlled. */
function parseCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  let i = 0;
  while (i < text.length) {
    const char = text[i];
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i += 1;
        continue;
      }
      field += char;
      i += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = true;
      i += 1;
      continue;
    }
    if (char === ",") {
      row.push(field);
      field = "";
      i += 1;
      continue;
    }
    if (char === "\r") {
      i += 1;
      continue;
    }
    if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      i += 1;
      continue;
    }
    field += char;
    i += 1;
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((cells) => cells.some((cell) => cell.trim() !== ""));
}

export interface SkippedCsvRow {
  /** 1-based, matching the file's own line numbers (the header is line 1). */
  row: number;
  word: string;
  kind: string;
  reason: string;
}

export interface QuizMaterialUploadResult {
  distractorUpdates: Array<{ frameIndex: number; wordIndex: number; distractors: string[] }>;
  clozeUpdates: Array<{ frameIndex: number; wordIndex: number; candidates: Array<{ sentence: string; distractors: string[] }> }>;
  synonymUpdates: Array<{ frameIndex: number; wordIndex: number; candidates: Array<{ synonym: string; distractors: string[] }> }>;
  addedCounts: { distractors: number; cloze: number; synonym: number };
  notFoundWords: string[];
  skipped: SkippedCsvRow[];
}

/** Parses a teacher-authored CSV of quiz material and resolves each row
 * against the story's current vocabulary — no AI involved, this is purely
 * a bulk version of the existing "Add question" form. Expected columns:
 * word, kind, text, distractors.
 *   - kind: "distractors" | "cloze" | "synonym"
 *   - text: blank for "distractors"; the cloze sentence (must contain the
 *     word); the synonym word
 *   - distractors: semicolon-separated wrong options (up to 3 kept)
 * One file can mix every kind and every word already used in the story. */
export function parseQuizMaterialCsv(text: string, topic: ReviewTopic): QuizMaterialUploadResult {
  const rows = parseCsvRows(text);
  const [header, ...body] = rows;
  const columns = (header ?? []).map((cell) => cell.trim().toLowerCase());
  const columnIndex = (name: string) => columns.indexOf(name);
  const wordColumn = columnIndex("word");
  const kindColumn = columnIndex("kind");
  const textColumn = columnIndex("text");
  const distractorsColumn = columnIndex("distractors");
  if (wordColumn === -1 || kindColumn === -1) {
    throw new Error('CSV must have "word" and "kind" columns (word,kind,text,distractors).');
  }

  const distractorUpdates: QuizMaterialUploadResult["distractorUpdates"] = [];
  const clozeUpdates: QuizMaterialUploadResult["clozeUpdates"] = [];
  const synonymUpdates: QuizMaterialUploadResult["synonymUpdates"] = [];
  const notFoundWords: string[] = [];
  const addedCounts = { distractors: 0, cloze: 0, synonym: 0 };
  const skipped: SkippedCsvRow[] = [];

  body.forEach((cells, bodyIndex) => {
    const csvLine = bodyIndex + 2; // +1 for the header row, +1 for 1-based counting
    const word = (cells[wordColumn] ?? "").trim();
    const kind = (cells[kindColumn] ?? "").trim().toLowerCase();
    const skip = (reason: string) => skipped.push({ row: csvLine, word, kind, reason });
    if (!word || !kind) {
      skip(!word ? "missing word" : "missing kind");
      return;
    }
    const occurrence = findLiveWordOccurrence(topic, word);
    if (!occurrence) {
      if (!notFoundWords.includes(word)) notFoundWords.push(word);
      return;
    }
    const { frameIndex, wordIndex } = occurrence;
    const text = textColumn === -1 ? "" : (cells[textColumn] ?? "").trim();
    const distractors = (distractorsColumn === -1 ? "" : cells[distractorsColumn] ?? "")
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 3);

    if (kind === "distractors") {
      if (distractors.length === 0) {
        skip("no distractors given");
        return;
      }
      distractorUpdates.push({ frameIndex, wordIndex, distractors });
      addedCounts.distractors += 1;
    } else if (kind === "cloze") {
      if (!text) {
        skip("missing cloze sentence");
        return;
      }
      if (!text.includes(word)) {
        skip("cloze sentence doesn't contain the word");
        return;
      }
      clozeUpdates.push({ frameIndex, wordIndex, candidates: [{ sentence: text, distractors }] });
      addedCounts.cloze += 1;
    } else if (kind === "synonym") {
      if (!text) {
        skip("missing synonym text");
        return;
      }
      if (text === word) {
        skip("synonym is identical to the word");
        return;
      }
      synonymUpdates.push({ frameIndex, wordIndex, candidates: [{ synonym: text, distractors }] });
      addedCounts.synonym += 1;
    } else {
      skip(`unknown kind "${kind}" (expected distractors, cloze, or synonym)`);
    }
  });

  return { distractorUpdates, clozeUpdates, synonymUpdates, addedCounts, notFoundWords, skipped };
}

function poolLengths(topic: ReviewTopic, frameIndex: number, wordIndex: number) {
  return {
    distractors: (topic.vocabularyDistractors?.[frameIndex]?.[wordIndex] ?? []).length,
    cloze: (topic.vocabularyCloze?.[frameIndex]?.[wordIndex] ?? []).length,
    synonym: (topic.vocabularySynonym?.[frameIndex]?.[wordIndex] ?? []).length,
  };
}

/** Compares each uploaded word's pool size before/after the PATCH calls
 * against how many items the upload attempted to add for it. A smaller
 * increase than attempted means the server's per-word merge (top-up +
 * dedupe + cap, see updateVocabularyDistractors/Cloze/Synonym) silently
 * dropped some of them — either because they duplicated an existing entry
 * or because the pool was already at its cap. Either way the teacher's
 * file said more should be there than actually landed, worth a note. */
export function fewerThanAttempted(
  beforeTopic: ReviewTopic,
  afterTopic: ReviewTopic,
  result: QuizMaterialUploadResult,
): string[] {
  const attempted = new Map<string, { word: string; distractors: number; cloze: number; synonym: number }>();
  const touch = (frameIndex: number, wordIndex: number, field: "distractors" | "cloze" | "synonym", amount: number) => {
    const key = `${frameIndex}:${wordIndex}`;
    const entry = attempted.get(key) ?? {
      word: beforeTopic.vocabulary?.[frameIndex]?.[wordIndex] ?? "",
      distractors: 0,
      cloze: 0,
      synonym: 0,
    };
    entry[field] += amount;
    attempted.set(key, entry);
  };
  result.distractorUpdates.forEach((u) => touch(u.frameIndex, u.wordIndex, "distractors", u.distractors.length));
  result.clozeUpdates.forEach((u) => touch(u.frameIndex, u.wordIndex, "cloze", u.candidates.length));
  result.synonymUpdates.forEach((u) => touch(u.frameIndex, u.wordIndex, "synonym", u.candidates.length));

  const underfilled: string[] = [];
  for (const [key, entry] of attempted) {
    const [frameIndex, wordIndex] = key.split(":").map(Number);
    const before = poolLengths(beforeTopic, frameIndex, wordIndex);
    const after = poolLengths(afterTopic, frameIndex, wordIndex);
    const short =
      after.distractors - before.distractors < entry.distractors ||
      after.cloze - before.cloze < entry.cloze ||
      after.synonym - before.synonym < entry.synonym;
    if (short && entry.word && !underfilled.includes(entry.word)) underfilled.push(entry.word);
  }
  return underfilled;
}
