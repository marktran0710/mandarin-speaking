import { useEffect, useState } from "react";
import Icon from "../../shared/ui/Icon";
import {
  confirmPlacementImport,
  getAdminPlacementBlueprint,
  previewPlacementImport,
  type PlacementBlueprint,
  type PlacementPreview,
  type PlacementQuestion,
} from "../../shared/api/placement-test";
import "./AdminPlacementTestPage.css";

const SAMPLE_ROWS = [
  ["C5-5-1-I1-W001", "1"],
  ["C5-5-1-I1-W001", "2"],
  ["C5-5-1-I1-W001", "3"],
  ["C5-6-1-I2-W004", "1"],
];

function questionLabel(question: PlacementQuestion): string {
  if (question.questionType === "basic_meaning_mcq") return "Meaning MCQ";
  if (question.questionType === "character_to_pinyin_typing") return "Pinyin typing";
  return "Context cloze MCQ";
}

export default function AdminPlacementTestPage() {
  const [current, setCurrent] = useState<PlacementBlueprint | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PlacementPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = () => {
    setLoading(true);
    void getAdminPlacementBlueprint()
      .then(setCurrent)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load the placement blueprint."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const previewFile = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setPreview(await previewPlacementImport(file));
    } catch (reason) {
      setPreview(null);
      setError(reason instanceof Error ? reason.message : "Could not preview the placement file.");
    } finally {
      setBusy(false);
    }
  };

  const confirmImport = async () => {
    if (!file || !preview?.valid) return;
    if (!window.confirm("Overwrite the active placement test with this question list? Students already in progress keep their snapshot.")) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await confirmPlacementImport(file);
      setCurrent(result);
      setPreview(null);
      setFile(null);
      setMessage(`Placement test updated with ${result.questionCount} questions.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import the placement blueprint.");
    } finally {
      setBusy(false);
    }
  };

  const downloadSample = () => {
    const csv = [["Word Key", "Round"], ...SAMPLE_ROWS].map((row) => row.join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([`${csv}\n`], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "placement-test-sample.csv";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <section className="admin-placement" aria-label="Placement Test">
      <div className="admin-placement__intro">
        <div>
          <span className="admin-eyebrow">Diagnostic assessment</span>
          <h2>Import question codes</h2>
          <p>
            Upload two columns — <code>Word Key</code> and <code>Round</code> — from the canonical <code>vocabAssessment</code> bank.
            Use round <code>1</code>, <code>2</code>, or <code>3</code>. The backend resolves the question ID across every published story.
          </p>
        </div>
        <div className="admin-placement__rules">
          <span>CSV / XLSX</span><span>Published banks only</span><span>Preview before overwrite</span>
        </div>
      </div>

      <section className="admin-placement__card" aria-labelledby="placement-upload-title">
        <div className="admin-placement__card-heading">
          <div><span className="admin-eyebrow">Step 1</span><h3 id="placement-upload-title">Choose a Word Key + Round file</h3></div>
          <Icon name="upload" size={22} />
        </div>
        <p className="admin-placement__hint">Use exactly <code>Word Key,Round</code> with round values <code>1</code>, <code>2</code>, <code>3</code>. You may also use <code>Word Key,Question Type</code>.</p>
        <div className="admin-placement__upload-row">
          <label className="admin-placement__file">
            <span>{file?.name ?? "Choose CSV or XLSX"}</span>
            <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setPreview(null); setError(""); setMessage(""); }} />
          </label>
          <button type="button" className="admin-placement__button admin-placement__button--primary" disabled={!file || busy} onClick={() => void previewFile()}>
            <Icon name="eye" size={17} />{busy ? "Checking…" : "Preview file"}
          </button>
        </div>
      </section>

      <section className="admin-placement__sample" aria-labelledby="placement-sample-title">
        <div className="admin-placement__sample-copy">
          <span className="admin-eyebrow">Reference</span>
          <h3 id="placement-sample-title">Sample placement test file</h3>
          <p>Two columns are required. The row order becomes the default test order. No Story ID or Question ID is required.</p>
        </div>
        <div className="admin-placement__sample-file" aria-label="Sample CSV contents">
          <div className="admin-placement__sample-row admin-placement__sample-row--header"><code>Word Key</code><code>Round</code></div>
          {SAMPLE_ROWS.map(([wordKey, round]) => <div className="admin-placement__sample-row" key={`${wordKey}-${round}`}><code>{wordKey}</code><code>{round}</code></div>)}
        </div>
        <button type="button" className="admin-placement__button" onClick={downloadSample}><Icon name="download" size={17} />Download sample CSV</button>
      </section>

      {preview && (
        <section className={`admin-placement__card admin-placement__preview${preview.valid ? " is-valid" : " is-invalid"}`} aria-labelledby="placement-preview-title">
          <div className="admin-placement__card-heading">
            <div><span className="admin-eyebrow">Step 2</span><h3 id="placement-preview-title">Preview import</h3></div>
            <strong>{preview.valid ? `${preview.questionCount} questions ready` : "Import blocked"}</strong>
          </div>
          {preview.rowIssues.length > 0 && (
            <div className="admin-placement__issues" role="alert"><strong>Fix these issues before confirming:</strong><ul>{preview.rowIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>
          )}
          {preview.valid && <>
            <p className="admin-placement__hint">This will replace the active blueprint. In-progress student attempts keep the question snapshot they started with.</p>
            <div className="admin-placement__table-wrap" tabIndex={0} role="region" aria-label="Placement question preview">
              <table className="admin-placement__table"><caption className="admin-placement__sr-only">Placement questions in imported order</caption><thead><tr><th>Order</th><th>Word Key</th><th>Round</th><th>Source story</th><th>Word</th><th>Type</th></tr></thead><tbody>
                {preview.questions.map((question) => <tr key={question.questionId}><td>{question.position}</td><td><code>{question.sourceWordId}</code></td><td>{question.round}</td><td>{question.sourceStoryTitle}</td><td lang="zh-Hant">{question.targetWord}</td><td>{questionLabel(question)}</td></tr>)}
              </tbody></table>
            </div>
            <div className="admin-placement__confirm-row"><span>Current active revision: {preview.currentRevision ?? "none"}</span><button type="button" className="admin-placement__button admin-placement__button--primary" disabled={busy} onClick={() => void confirmImport()}><Icon name="check" size={17} />Confirm overwrite</button></div>
          </>}
        </section>
      )}

      {message && <p className="admin-placement__success" role="status">{message}</p>}
      {error && <p className="admin-placement__error" role="alert">{error}</p>}

      <section className="admin-placement__card" aria-labelledby="active-placement-title">
        <div className="admin-placement__card-heading"><div><span className="admin-eyebrow">Active blueprint</span><h3 id="active-placement-title">Current placement test</h3></div><span className="admin-placement__revision">Revision {current?.revision ?? "—"}</span></div>
        {loading ? <p>Loading active blueprint…</p> : !current?.configured ? <p className="admin-placement__empty">Placement test chưa được cấu hình.</p> : <div className="admin-placement__active-summary"><strong>{current.questionCount} questions</strong><span>Resolved from published vocabulary banks. Student attempts use a start-time snapshot.</span></div>}
      </section>
    </section>
  );
}
