import { useRef, useState } from "react";
import Icon from "../../shared/ui/Icon";
import {
  confirmMaterialsImport,
  downloadMaterialsTemplate,
  previewMaterialsImport,
  type MaterialsImportChange,
  type MaterialsImportKind,
  type MaterialsImportPreview,
} from "../../services/api/materials";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function changeLabel(change: MaterialsImportChange) {
  if (change.scene != null) return `${change.storyKey ?? `${change.lesson}-${change.story}`} · scene ${change.scene}`;
  return change.storyKey ?? change.storyTitle;
}

export default function MaterialsImportDialog({
  kind,
  onClose,
  onConfirmed,
}: {
  kind: MaterialsImportKind;
  onClose: () => void;
  onConfirmed: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<MaterialsImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const chooseFiles = (selected: File[]) => {
    setFiles(kind === "scripts" ? selected.slice(0, 1) : selected);
    setPreview(null);
    setError("");
  };

  const runPreview = async () => {
    if (!files.length) return;
    setBusy(true);
    setError("");
    try {
      setPreview(await previewMaterialsImport(kind, files));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not preview this import.");
    } finally {
      setBusy(false);
    }
  };

  const runConfirm = async () => {
    if (!files.length || !preview?.valid) return;
    setBusy(true);
    setError("");
    try {
      const result = await confirmMaterialsImport(kind, files);
      const count = result.updated.length;
      onConfirmed(kind === "images"
        ? `Updated images for ${count} ${count === 1 ? "story" : "stories"}.`
        : `Updated ${count} ${count === 1 ? "scene" : "scenes"}; Conversation now uses the shared scene scripts.`);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not confirm this import.");
    } finally {
      setBusy(false);
    }
  };

  const template = async () => {
    setError("");
    try {
      const blob = await downloadMaterialsTemplate(kind);
      downloadBlob(blob, kind === "scripts" ? "lessons-5-8.csv" : "lesson-5-8-images-template.zip");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not download the template.");
    }
  };

  return (
    <div className="materials-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="materials-dialog" role="dialog" aria-modal="true" aria-labelledby="materials-dialog-title">
        <div className="materials-dialog-head">
          <div>
            <span className="admin-eyebrow">Step {preview ? "2 of 2" : "1 of 2"}</span>
            <h2 id="materials-dialog-title">Upload {kind}</h2>
          </div>
          <button type="button" className="materials-dialog-close" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <p className="materials-dialog-note">
          {kind === "images"
            ? "Choose one complete image per story (5-1.png through 8-3.png), or a ZIP containing them."
            : "Choose one UTF-8 CSV. Each row maps lesson, story, and scene to the shared script."}
        </p>
        <div className="materials-dialog-actions">
          <label className="admin-upload-button">
            <Icon name="upload" size={17} />
            Choose {kind === "images" ? "images or ZIP" : "CSV"}
            <input
              ref={inputRef}
              type="file"
              hidden
              multiple={kind === "images"}
              accept={kind === "images" ? "image/png,image/jpeg,image/webp,.zip,application/zip" : ".csv,text/csv"}
              onChange={(event) => { chooseFiles(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ""; }}
            />
          </label>
          <button type="button" className="admin-template-button" onClick={() => void template()}>Download sample</button>
          {files.length > 0 && <span className="materials-file-count">{files.length} file{files.length === 1 ? "" : "s"} selected</span>}
        </div>
        {files.length > 0 && !preview && (
          <button type="button" className="admin-primary-button" disabled={busy} onClick={() => void runPreview()}>
            {busy ? "Checking…" : "Preview changes"}
          </button>
        )}
        {preview && (
          <div className="materials-preview" aria-live="polite">
            <div className="materials-preview-summary">
              <strong>{preview.changes.length} change{preview.changes.length === 1 ? "" : "s"} found</strong>
              <span>{preview.valid ? "Ready to confirm" : "Fix the issues below before confirming"}</span>
            </div>
            {preview.changes.length > 0 && (
              <div className="materials-change-list">
                {preview.changes.map((change, index) => (
                  <div className="materials-change" key={`${change.storyId}-${change.scene ?? index}`}>
                    <strong>{changeLabel(change)}</strong>
                    <span>{change.before || "(empty)"} → {change.after}</span>
                  </div>
                ))}
              </div>
            )}
            {preview.issues.length > 0 && <div className="materials-issues" role="alert"><strong>Cannot confirm yet</strong><ul>{preview.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}
            <div className="materials-dialog-footer">
              <button type="button" className="admin-template-button" disabled={busy} onClick={() => { setPreview(null); setError(""); }}>Choose different files</button>
              <button type="button" className="admin-primary-button" disabled={busy || !preview.valid} onClick={() => void runConfirm()}>
                {busy ? "Saving…" : "Confirm import"}
              </button>
            </div>
          </div>
        )}
        {error && <p className="materials-import-error" role="alert">{error}</p>}
      </section>
    </div>
  );
}
