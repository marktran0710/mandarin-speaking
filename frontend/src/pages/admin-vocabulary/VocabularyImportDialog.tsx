import { useRef, useState } from "react";
import Modal from "../../shared/ui/Modal";
import Icon from "../../shared/ui/Icon";
import {
  confirmVocabularyImport,
  previewVocabularyImport,
  type VocabularyImportPreview,
  type VocabularyImportResult,
} from "../../services/api/vocabulary";

/** Admin quiz-vocabulary CSV import: upload -> server-side preview (nothing
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

  return (
    <Modal open title="Import quiz vocabulary" onClose={onClose}>
      <div className="av-import">
        <p className="av-editor-help">
          Upload a question-bank CSV (same columns as the workbook export: Word Key, Traditional
          Chinese, Pinyin, POS, English Meaning, Round, Question Type, Options, Correct Answer,
          Accepted Answers, Section, …). Nothing is written until you confirm below - imported
          words are upserted by Word Key into the story matched by Section (e.g. "5-1"); existing
          words that story already has and the file doesn't mention are left untouched.
        </p>

        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          aria-label="Question bank CSV file"
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
