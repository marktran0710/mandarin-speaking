import { useState } from "react";
import { buildVocabRows, type VocabRow } from "../utils/myStoriesUtils";

const VOCAB_POS_OPTIONS = ["N", "V", "Adj", "Adv", "MW", "Particle", "Phrase", "Other"];

export default function VocabularyTable({
  vocabulary,
  vocabularyPinyin,
  vocabularyPos,
  vocabularyTranslation,
  onChangeColumn,
}: {
  vocabulary: string;
  vocabularyPinyin: string;
  vocabularyPos: string;
  vocabularyTranslation: string;
  onChangeColumn: (
    field: "vocabulary" | "vocabularyPinyin" | "vocabularyPos" | "vocabularyTranslation",
    value: string,
  ) => void;
}) {
  const [rows, setRows] = useState<VocabRow[]>(() =>
    buildVocabRows(vocabulary, vocabularyPinyin, vocabularyPos, vocabularyTranslation),
  );

  const commitRows = (nextRows: VocabRow[]) => {
    setRows(nextRows);
    onChangeColumn("vocabulary", nextRows.map((r) => r.word).join(", "));
    onChangeColumn("vocabularyPinyin", nextRows.map((r) => r.pinyin).join(", "));
    onChangeColumn("vocabularyPos", nextRows.map((r) => r.pos).join(", "));
    onChangeColumn("vocabularyTranslation", nextRows.map((r) => r.translation).join(", "));
  };

  const updateCell = (rowIndex: number, field: keyof VocabRow, value: string) => {
    commitRows(rows.map((row, i) => (i === rowIndex ? { ...row, [field]: value } : row)));
  };

  const addRow = () => {
    commitRows([...rows, { word: "", pinyin: "", pos: "", translation: "" }]);
  };

  const removeRow = (rowIndex: number) => {
    commitRows(rows.filter((_, i) => i !== rowIndex));
  };

  return (
    <div className="vocab-table" role="table" aria-label="Vocabulary">
      <div className="vocab-table-header" role="row">
        <span role="columnheader">Chinese word</span>
        <span role="columnheader">Pinyin</span>
        <span role="columnheader">Part of speech</span>
        <span role="columnheader">English translation</span>
        <span role="columnheader" aria-hidden="true" />
      </div>
      {rows.map((row, index) => (
        <div className="vocab-table-row" role="row" key={index}>
          <input
            aria-label="Chinese word"
            value={row.word}
            onChange={(event) => updateCell(index, "word", event.target.value)}
            placeholder="餐廳"
          />
          <input
            aria-label="Pinyin"
            value={row.pinyin}
            onChange={(event) => updateCell(index, "pinyin", event.target.value)}
            placeholder="cāntīng"
          />
          <select
            aria-label="Part of speech"
            value={row.pos}
            onChange={(event) => updateCell(index, "pos", event.target.value)}
          >
            <option value="">--</option>
            {VOCAB_POS_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <input
            aria-label="English translation"
            value={row.translation}
            onChange={(event) => updateCell(index, "translation", event.target.value)}
            placeholder="restaurant"
          />
          <button
            type="button"
            className="vocab-table-remove"
            aria-label={`Remove word ${index + 1}`}
            onClick={() => removeRow(index)}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="vocab-table-add-btn" onClick={addRow}>
        + Add word
      </button>
    </div>
  );
}
