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

export interface QuizMaterialUploadResult {
  distractorUpdates: Array<{ frameIndex: number; wordIndex: number; distractors: string[] }>;
  clozeUpdates: Array<{ frameIndex: number; wordIndex: number; candidates: Array<{ sentence: string; distractors: string[] }> }>;
  synonymUpdates: Array<{ frameIndex: number; wordIndex: number; candidates: Array<{ synonym: string; distractors: string[] }> }>;
  addedCounts: { distractors: number; cloze: number; synonym: number };
  notFoundWords: string[];
  skippedRows: number;
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
  let skippedRows = 0;

  for (const cells of body) {
    const word = (cells[wordColumn] ?? "").trim();
    const kind = (cells[kindColumn] ?? "").trim().toLowerCase();
    if (!word || !kind) continue;
    const occurrence = findLiveWordOccurrence(topic, word);
    if (!occurrence) {
      if (!notFoundWords.includes(word)) notFoundWords.push(word);
      continue;
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
        skippedRows += 1;
        continue;
      }
      distractorUpdates.push({ frameIndex, wordIndex, distractors });
      addedCounts.distractors += 1;
    } else if (kind === "cloze") {
      if (!text || !text.includes(word)) {
        skippedRows += 1;
        continue;
      }
      clozeUpdates.push({ frameIndex, wordIndex, candidates: [{ sentence: text, distractors }] });
      addedCounts.cloze += 1;
    } else if (kind === "synonym") {
      if (!text || text === word) {
        skippedRows += 1;
        continue;
      }
      synonymUpdates.push({ frameIndex, wordIndex, candidates: [{ synonym: text, distractors }] });
      addedCounts.synonym += 1;
    } else {
      skippedRows += 1;
    }
  }

  return { distractorUpdates, clozeUpdates, synonymUpdates, addedCounts, notFoundWords, skippedRows };
}
