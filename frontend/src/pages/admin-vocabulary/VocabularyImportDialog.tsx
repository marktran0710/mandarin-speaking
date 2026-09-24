import { useRef, useState } from "react";
import Modal from "../../shared/ui/Modal";
import Icon from "../../shared/ui/Icon";
import {
  confirmVocabularyImport,
  previewVocabularyImport,
  type VocabularyImportPreview,
  type VocabularyImportResult,
} from "../../services/api/vocabulary";

const TEMPLATE_HEADERS = [
  "Question ID", "Word Key", "Source Type", "Chapter", "Section", "Item",
  "Traditional Chinese", "Pinyin", "POS", "English Meaning", "Round",
  "Question Type", "Input Mode", "Prompt", "Option A", "Option B", "Option C",
  "Option D", "Correct Option", "Correct Answer", "Accepted Answers",
] as const;

const TEMPLATE_ROWS = [
  ["Q-DEMO-001", "DEMO-W001", "Vocabulary", "5", "5-1", "1", "錢包", "qiánbāo", "N", "wallet; purse", "1", "basic_meaning_mcq", "mcq", "Choose the correct English meaning of 錢包.", "wallet; purse", "kitchen", "music", "chair", "A", "wallet; purse", "wallet; purse"],
  ["Q-DEMO-002", "DEMO-W001", "Vocabulary", "5", "5-1", "1", "錢包", "qiánbāo", "N", "wallet; purse", "2", "character_to_pinyin_typing", "free_text", "Type the pinyin for 錢包.", "", "", "", "", "", "qiánbāo", "qiánbāo | qian2bao1"],
  ["Q-DEMO-003", "DEMO-W001", "Vocabulary", "5", "5-1", "1", "錢包", "qiánbāo", "N", "wallet; purse", "3", "context_cloze_mcq", "mcq", "Choose the correct word: 李小姐的____是紅色的。", "錢包", "音樂", "房間", "椅子", "A", "錢包", "錢包"],
] as const;

function csvCell(value: string) {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** Admin quiz-vocabulary CSV/XLSX import: upload -> server-side preview (nothing
 * written yet) -> explicit confirm. Reuses the same column format and
 * validation as backend/scripts/import_question_bank_workbook.py, just
 * generalized to any section/story instead of hardcoded to Chapters 5-8.
 * Import only ever upserts by wordId within each matched story - words
 * already in that story's bank that the file doesn't mention are kept. */
export default function VocabularyImportDialog({ onClose, onImported }: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<VocabularyImportPreview | null>(null);
  const [result, setResult] = useState<VocabularyImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const pickFile = async (selected: File | null) => {
    setFile(selected);
    setPreview(null);
    setResult(null);
    setError("");
    if (!selected) return;
    setLoading(true);
    try {
      setPreview(await previewVocabularyImport(selected));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not validate the file.");
    } finally {
      setLoading(false);
    }
  };

  const hasBlockingIssues = Boolean(
    !preview
    || preview.rowIssues.length > 0
    || preview.sections.some((section) => !section.found || section.issues.length > 0),
  );

  const confirm = async () => {
    if (!file || hasBlockingIssues) return;
    setConfirming(true);
    setError("");
    try {
      setResult(await confirmVocabularyImport(file));
      onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import the file.");
    } finally {
      setConfirming(false);
    }
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const downloadTemplate = () => {
    const csv = [TEMPLATE_HEADERS, ...TEMPLATE_ROWS]
      .map(row => row.map(value => csvCell(value)).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}\r\n`], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "vocabulary-import-template.csv";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <Modal open title="Import vocabulary + questions" onClose={onClose}>
      <div className="av-import">
        <p className="av-editor-help">
          Upload the canonical vocabulary + question CSV or XLSX with the core columns: Word Key, Traditional Chinese,
          Pinyin, POS, English Meaning, Round, Question Type, Options, Correct Answer, Accepted
          Answers, and Section. The sample below contains the complete data shape; no Tier, Skill
          Label, context/source, or page-reference columns are needed. For XLSX, a sheet named
          "Questions" is used if present, otherwise the first sheet. Nothing is written until you
          confirm below. Imported words and their questions are upserted by Word Key into the story matched by Section
          (e.g. "5-1"); existing words that story already has and the file doesn't mention are left
          untouched.
        </p>

        <details className="av-import-template">
          <summary>View and download the standard template</summary>
          <p className="av-import-template-copy">Use exactly three rows per Word Key: Round <strong>1</strong> checks meaning, Round <strong>2</strong> checks pinyin, and Round <strong>3</strong> checks contextual use. Use <strong>mcq</strong> for choice questions and <strong>free_text</strong> for typed answers. The server rejects missing, duplicated, or inconsistent round data before anything is written.</p>
          <div className="av-template-table-wrap" tabIndex={0} role="region" aria-label="Vocabulary import template">
            <table className="av-template-table">
              <thead><tr>{TEMPLATE_HEADERS.map(header => <th key={header}>{header}</th>)}</tr></thead>
              <tbody>{TEMPLATE_ROWS.map((row, rowIndex) => <tr key={rowIndex}>{row.map((value, columnIndex) => <td key={`${rowIndex}-${columnIndex}`}>{value || "—"}</td>)}</tr>)}</tbody>
            </table>
          </div>
          <button type="button" className="av-button av-template-download" onClick={downloadTemplate}><Icon name="download" size={18} />Download sample CSV</button>
        </details>

        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Question bank CSV or XLSX file"
          onChange={(event) => void pickFile(event.target.files?.[0] ?? null)}
          disabled={loading || confirming}
        />

        {loading && <p role="status">Validating…</p>}
        {error && <p className="av-error" role="alert">{error}</p>}

        {preview && !result && (
          <div className="av-import-preview">
            <p>{preview.rows} row{preview.rows === 1 ? "" : "s"} parsed.</p>
            {preview.rowIssues.length > 0 && (
              <div className="av-error" role="alert">
                <strong>File failed validation - fix and re-upload:</strong>
                <ul>{preview.rowIssues.slice(0, 20).map((issue, index) => <li key={index}>{issue}</li>)}</ul>
              </div>
            )}
            {preview.sections.length > 0 && (
              <ul className="av-import-sections">
                {preview.sections.map((section) => (
                  <li key={section.section} className={!section.found || section.issues.length > 0 ? "is-error" : undefined}>
                    <strong>{section.section}</strong>
                    {section.found ? (
                      <>
                        <span>{section.storyTitle}</span>
                        <span>{section.newWords} new · {section.updatedWords} updated · {section.questionCount} question{section.questionCount === 1 ? "" : "s"}</span>
                      </>
                    ) : (
                      <span role="alert">{section.error}</span>
                    )}
                    {section.issues.length > 0 && (
                      <ul>{section.issues.slice(0, 10).map((issue, index) => <li key={index}>{issue}</li>)}</ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {result && (
          <div className="av-import-result" role="status">
            <p><strong>Imported.</strong></p>
            <ul>
              {result.published.map((section) => (
                <li key={section.section}>{section.storyTitle} ({section.section}): {section.questionCount} questions</li>
              ))}
            </ul>
          </div>
        )}

        <div className="av-editor-actions">
          <button type="button" className="av-button" onClick={onClose}>Close</button>
          {result ? (
            <button type="button" className="av-button" onClick={reset}>Import another file</button>
          ) : (
            <button
              type="button"
              className="av-button av-primary"
              onClick={() => void confirm()}
              disabled={confirming || loading || hasBlockingIssues}
            >
              <Icon name="check" size={18} />{confirming ? "Importing…" : "Confirm import"}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
