import { useState } from "react";
import { buildPhraseRows, type PhraseRow } from "../utils/myStoriesUtils";

/** Per-scene "handy phrases" table — easy-to-learn, practice, and remember
 * chunks students can reuse (replaces the old single whole-story grammar
 * pattern/example fields). Same comma-joined-column convention as
 * VocabularyTable above, just with fewer columns. */
export default function PhraseTable({
  phrases,
  phrasesTranslation,
  onChangeColumn,
}: {
  phrases: string;
  phrasesTranslation: string;
  onChangeColumn: (field: "phrases" | "phrasesTranslation", value: string) => void;
}) {
  const [rows, setRows] = useState<PhraseRow[]>(() =>
    buildPhraseRows(phrases, phrasesTranslation),
  );

  const commitRows = (nextRows: PhraseRow[]) => {
    setRows(nextRows);
    onChangeColumn("phrases", nextRows.map((r) => r.phrase).join(", "));
    onChangeColumn("phrasesTranslation", nextRows.map((r) => r.translation).join(", "));
  };

  const updateCell = (rowIndex: number, field: keyof PhraseRow, value: string) => {
    commitRows(rows.map((row, i) => (i === rowIndex ? { ...row, [field]: value } : row)));
  };

  const addRow = () => {
    commitRows([...rows, { phrase: "", translation: "" }]);
  };

  const removeRow = (rowIndex: number) => {
    commitRows(rows.filter((_, i) => i !== rowIndex));
  };

  return (
    <div className="vocab-table phrase-table" role="table" aria-label="Phrases">
      <div className="vocab-table-header" role="row">
        <span role="columnheader">Phrase (Chinese)</span>
        <span role="columnheader">English translation</span>
        <span role="columnheader" aria-hidden="true" />
      </div>
      {rows.map((row, index) => (
        <div className="vocab-table-row phrase-table-row" role="row" key={index}>
          <input
            aria-label="Phrase"
            value={row.phrase}
            onChange={(event) => updateCell(index, "phrase", event.target.value)}
            placeholder="我想要…"
          />
          <input
            aria-label="English translation"
            value={row.translation}
            onChange={(event) => updateCell(index, "translation", event.target.value)}
            placeholder="I would like…"
          />
          <button
            type="button"
            className="vocab-table-remove"
            aria-label={`Remove phrase ${index + 1}`}
            onClick={() => removeRow(index)}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="vocab-table-add-btn" onClick={addRow}>
        + Add phrase
      </button>
    </div>
  );
}
