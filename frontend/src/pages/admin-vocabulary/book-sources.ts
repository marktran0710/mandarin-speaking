import references from "./book-references.json";
import type { VocabularyEntry } from "./model";

const kinds: Record<string, string> = {
  "Bảng từ mới": "Vocabulary list", "Hội thoại / bài đọc": "Dialogue / reading",
  "Mục Phrase": "Phrase list", "Từ mở rộng trong bảng": "Related vocabulary",
};
const index = new Map(references.references.map(item => [`${item.lesson}:${item.word}`, item]));

export function vocabularyBookSource(entry: Pick<VocabularyEntry, "lessonNumber" | "word">) {
  const reference = index.get(`${entry.lessonNumber}:${entry.word}`);
  return reference ? { ...reference, kind: kinds[reference.kind] || reference.kind, book: references.book } : null;
}
