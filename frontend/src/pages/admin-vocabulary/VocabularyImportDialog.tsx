import { useRef, useState } from "react";
import Modal from "../../shared/ui/Modal";
import Icon from "../../shared/ui/Icon";
import {
  confirmVocabularyImport,
  downloadVocabularyImportTemplate,
  previewVocabularyImport,
  type VocabularyImportPreview,
  type VocabularyImportResult,
} from "../../services/api/vocabulary";

/** Admin-only canonical vocabulary + quiz import.
 * The server owns the workbook schema and applies a replace-lesson strategy;
 * this component only coordinates upload, preview acknowledgement and confirm.
 */
export default function VocabularyImportDialog({ onClose, onImported }: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<VocabularyImportPreview | null>(null);
  const [result, setResult] = useState<VocabularyImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [acknowledgeReplacement, setAcknowledgeReplacement] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const pickFile = async (selected: File | null) => {
    setFile(selected);
    setPreview(null);
    setResult(null);
    setAcknowledgeReplacement(false);
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
  const requiresReplacementAcknowledgement = Boolean(preview?.removedWords);

  const confirm = async () => {
    if (!file || hasBlockingIssues || (requiresReplacementAcknowledgement && !acknowledgeReplacement)) return;
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
    setAcknowledgeReplacement(false);
    setError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const downloadTemplate = async () => {
    setTemplateLoading(true);
    setError("");
    try {
      const blob = await downloadVocabularyImportTemplate();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "vocabulary-import-template.xlsx";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not download the import template.");
    } finally {
      setTemplateLoading(false);
    }
  };

  return (
    <Modal open title="Import vocabulary + questions" onClose={onClose}>
      <div className="av-import">
        <p className="av-editor-help">
          Upload the canonical vocabulary + question XLSX or CSV. The standard XLSX has
          <strong> Instructions</strong> and <strong>Questions</strong> sheets. Each Word Key needs
          exactly three rounds. The file replaces the canonical quiz bank for every Section it contains;
          frame/story vocabulary is not changed.
        </p>
        <div className="av-audio-import-rule" role="note">
          <Icon name="info" size={18} />
          <span>Audio is imported separately. Existing audio is preserved for matching Word Keys; missing audio remains visible and does not block publish.</span>
        </div>

        <details className="av-import-template">
          <summary>Download the standard XLSX template</summary>
          <p className="av-import-template-copy">
            The template documents the required columns, round rules, exact Word Key format and audio ZIP naming.
            Book source, Source Type, Tier, Skill Label, context and page-reference columns are not required.
          </p>
          <button
            type="button"
            className="av-button av-template-download"
            onClick={() => void downloadTemplate()}
            disabled={templateLoading}
          >
            <Icon name="download" size={18} />
            {templateLoading ? "Preparing template..." : "Download XLSX template"}
          </button>
        </details>

        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Question bank CSV or XLSX file"
          onChange={(event) => void pickFile(event.target.files?.[0] ?? null)}
          disabled={loading || confirming}
        />

        {loading && <p role="status">Validating file...</p>}
        {error && <p className="av-error" role="alert">{error}</p>}

        {preview && !result && (
          <div className="av-import-preview">
            <p>{preview.rows} row{preview.rows === 1 ? "" : "s"} parsed. This is a <strong>replace lesson</strong> import.</p>
            {preview.rowIssues.length === 0 && (
              <dl className="av-import-summary">
                <div><dt>New words</dt><dd>{preview.newWords}</dd></div>
                <div><dt>Updated</dt><dd>{preview.updatedWords}</dd></div>
                <div className={preview.removedWords > 0 ? "is-warning" : undefined}><dt>Removed</dt><dd>{preview.removedWords}</dd></div>
                <div><dt>Audio preserved</dt><dd>{preview.preservedAudio}</dd></div>
                <div className={preview.missingAudio > 0 ? "is-warning" : undefined}><dt>Missing audio</dt><dd>{preview.missingAudio}</dd></div>
              </dl>
            )}
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
                        <span>{section.newWords} new · {section.updatedWords} updated · {section.removedWords} removed · {section.questionCount} question{section.questionCount === 1 ? "" : "s"}</span>
                        <span className={section.missingAudio > 0 ? "is-missing" : undefined}>
                          {section.missingAudio ? `${section.missingAudio} word${section.missingAudio === 1 ? "" : "s"} missing audio` : "All words have audio"}
                        </span>
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
            {requiresReplacementAcknowledgement && (
              <label className="av-import-replacement-warning">
                <input type="checkbox" checked={acknowledgeReplacement} onChange={(event) => setAcknowledgeReplacement(event.target.checked)} />
                <span>This will remove {preview.removedWords} old canonical word{preview.removedWords === 1 ? "" : "s"} from the affected quiz bank. I understand.</span>
              </label>
            )}
          </div>
        )}

        {result && (
          <div className="av-import-result" role="status">
            <p><strong>Imported.</strong></p>
            <p>{result.newWords} new · {result.updatedWords} updated · {result.removedWords} removed · {result.missingAudio} missing audio.</p>
            <ul>
              {result.published.map((section) => (
                <li key={section.section}>{section.storyTitle} ({section.section}): {section.questionCount} questions, {section.removedWords} removed, {section.missingAudio} missing audio</li>
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
              disabled={confirming || loading || hasBlockingIssues || (requiresReplacementAcknowledgement && !acknowledgeReplacement)}
            >
              <Icon name="check" size={18} />{confirming ? "Importing..." : "Confirm replace import"}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
