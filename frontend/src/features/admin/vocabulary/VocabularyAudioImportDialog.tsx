import { useRef, useState } from "react";
import Modal from "../../../shared/ui/Modal";
import Icon from "../../../shared/ui/Icon";
import {
  confirmVocabularyAudioImport,
  downloadVocabularyAudioSample,
  previewVocabularyAudioImport,
  type VocabularyAudioImportPreview,
  type VocabularyAudioImportResult,
} from "../../../services/api/vocabulary";

export default function VocabularyAudioImportDialog({ onClose, onImported }: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<VocabularyAudioImportPreview | null>(null);
  const [result, setResult] = useState<VocabularyAudioImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sampleLoading, setSampleLoading] = useState(false);
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
      setPreview(await previewVocabularyAudioImport(selected));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not validate the audio ZIP.");
    } finally {
      setLoading(false);
    }
  };

  const canConfirm = Boolean(preview && preview.issues.length === 0 && preview.matched.length > 0);

  const confirm = async () => {
    if (!file || !canConfirm) return;
    setConfirming(true);
    setError("");
    try {
      setResult(await confirmVocabularyAudioImport(file));
      onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import the audio ZIP.");
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

  const downloadSample = async () => {
    setSampleLoading(true);
    setError("");
    try {
      const blob = await downloadVocabularyAudioSample();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "vocabulary-audio-sample.zip";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not download the audio sample ZIP.");
    } finally {
      setSampleLoading(false);
    }
  };

  return (
    <Modal open title="Import vocabulary audio" onClose={onClose}>
      <div className="av-import av-audio-import">
        <p className="av-editor-help">
          Upload a ZIP with one audio file per canonical <strong>Word Key</strong>. Name each file exactly like its Word Key,
          for example <code>C5-5-1-I1-W001.mp3</code>. Supported formats: MP3, WAV, M4A, WEBM and OGG. This attaches the
          same model audio to all three question rounds for that word; it does not import student recordings. Re-uploading
          a Word Key replaces its old model audio and removes the old stored file.
        </p>
        <div className="av-audio-import-rule" role="note">
          <Icon name="info" size={18} />
          <span>Unmatched files are left out and shown in the preview. Nothing is written until you confirm.</span>
        </div>

        <details className="av-import-template av-audio-sample">
          <summary>Download the sample audio ZIP</summary>
          <p className="av-import-template-copy">
            This is a mapping-only sample, not a production Mandarin recording. The filename is the contract:
            <code>C5-5-1-I1-W001.mp3</code> maps to the same <strong>Word Key</strong> in all three question rounds.
            Do not use Question ID, Chinese text, pinyin, lesson names or round suffixes such as <code>_r1</code>.
          </p>
          <pre className="av-audio-sample-tree" aria-label="Sample audio ZIP contents">vocabulary-audio-sample.zip{`\n`}└── C5-5-1-I1-W001.mp3</pre>
          <button
            type="button"
            className="av-button av-template-download"
            onClick={() => void downloadSample()}
            disabled={sampleLoading}
          >
            <Icon name="download" size={18} />
            {sampleLoading ? "Preparing sample..." : "Download sample audio ZIP"}
          </button>
        </details>

        <input
          ref={fileInputRef}
          type="file"
          accept=".zip,application/zip,application/x-zip-compressed"
          aria-label="Vocabulary audio ZIP file"
          onChange={(event) => void pickFile(event.target.files?.[0] ?? null)}
          disabled={loading || confirming}
        />

        {loading && <p role="status">Checking audio filenames...</p>}
        {error && <p className="av-error" role="alert">{error}</p>}

        {preview && !result && (
          <div className="av-import-preview">
            <p><strong>{preview.matched.length}</strong> matched of {preview.files} audio files.</p>
            {preview.issues.length > 0 && (
              <div className="av-error" role="alert">
                <strong>Fix these ZIP issues before importing:</strong>
                <ul>{preview.issues.slice(0, 20).map((issue) => <li key={issue}>{issue}</li>)}</ul>
              </div>
            )}
            {preview.unmatched.length > 0 && (
              <div className="av-import-warning" role="status">
                <strong>{preview.unmatched.length} unmatched file{preview.unmatched.length === 1 ? "" : "s"}:</strong>
                <ul>{preview.unmatched.slice(0, 20).map((filename) => <li key={filename}>{filename}</li>)}</ul>
              </div>
            )}
            {preview.matched.length > 0 && (
              <ul className="av-audio-match-list">
                {preview.matched.slice(0, 12).map((match) => (
                  <li key={match.filename}><strong>{match.wordKey}</strong><span>{match.storyTitle}</span></li>
                ))}
                {preview.matched.length > 12 && <li>and {preview.matched.length - 12} more...</li>}
              </ul>
            )}
          </div>
        )}

        {result && (
          <div className="av-import-result" role="status">
            <p><strong>Audio imported.</strong> {result.updated} vocabulary word{result.updated === 1 ? "" : "s"} updated.</p>
            {result.unmatchedAudio.length > 0 && <p>{result.unmatchedAudio.length} unmatched file{result.unmatchedAudio.length === 1 ? "" : "s"} were skipped.</p>}
          </div>
        )}

        <div className="av-editor-actions">
          <button type="button" className="av-button" onClick={onClose}>Close</button>
          {result ? (
            <button type="button" className="av-button" onClick={reset}>Import another ZIP</button>
          ) : (
            <button type="button" className="av-button av-primary" onClick={() => void confirm()} disabled={confirming || loading || !canConfirm}>
              <Icon name="check" size={18} />{confirming ? "Importing..." : "Confirm audio import"}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
