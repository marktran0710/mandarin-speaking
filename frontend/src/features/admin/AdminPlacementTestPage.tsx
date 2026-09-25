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

function parseQuestionIds(value: string): string[] {
  const trimmed = value.trim();
  if (!trimmed) return [];
  if (trimmed.startsWith("[")) {
    const parsed: unknown = JSON.parse(trimmed);
    if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === "string")) {
      throw new Error("Use a JSON array of question IDs.");
    }
    return parsed.map((item) => item.trim()).filter(Boolean);
  }
  return trimmed.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
}

function questionLabel(question: PlacementQuestion): string {
  if (question.questionType === "basic_meaning_mcq") return "Meaning MCQ";
  if (question.questionType === "character_to_pinyin_typing") return "Pinyin typing";
  return "Context cloze MCQ";
}

export default function AdminPlacementTestPage() {
  const [current, setCurrent] = useState<PlacementBlueprint | null>(null);
  const [questionIdsText, setQuestionIdsText] = useState("");
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

  const previewQuestions = async () => {
    let questionIds: string[];
    try {
      questionIds = parseQuestionIds(questionIdsText);
    } catch (reason) {
      setPreview(null);
      setError(reason instanceof Error ? reason.message : "Could not read the question IDs.");
      return;
    }
    if (!questionIds.length) {
      setPreview(null);
      setError("Enter at least one question ID.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setPreview(await previewPlacementImport(questionIds));
    } catch (reason) {
      setPreview(null);
      setError(reason instanceof Error ? reason.message : "Could not preview the placement questions.");
    } finally {
      setBusy(false);
    }
  };

  const confirmImport = async () => {
    if (!preview?.valid) return;
    let questionIds: string[];
    try {
      questionIds = parseQuestionIds(questionIdsText);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not read the question IDs.");
      return;
    }
    if (!window.confirm("Overwrite the active placement test with this question list? Students already in progress keep their snapshot.")) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await confirmPlacementImport(questionIds);
      setCurrent(result);
      setPreview(null);
      setQuestionIdsText("");
      setMessage(`Placement test updated with ${result.questionCount} questions.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the placement blueprint.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="admin-placement" aria-label="Placement Test">
      <div className="admin-placement__intro">
        <div>
          <span className="admin-eyebrow">Diagnostic assessment</span>
          <h2>Set placement question IDs</h2>
          <p>
            Enter the canonical <code>questionId</code> values in the order students should answer them.
            The IDs must belong to published vocabulary banks.
          </p>
        </div>
        <div className="admin-placement__rules">
          <span>Question IDs only</span><span>One per line or JSON array</span><span>Preview before overwrite</span>
        </div>
      </div>

      <section className="admin-placement__card" aria-labelledby="placement-input-title">
        <div className="admin-placement__card-heading">
          <div><span className="admin-eyebrow">Step 1</span><h3 id="placement-input-title">Enter question IDs</h3></div>
          <Icon name="quiz" size={22} />
        </div>
        <p className="admin-placement__hint">
          Paste one ID per line, separated by commas, or use a JSON array such as <code>["Q0001", "Q0002"]</code>.
        </p>
        <label className="admin-placement__question-input">
          <span>Placement question IDs</span>
          <textarea
            rows={8}
            value={questionIdsText}
            placeholder={'Q0001\nQ0002\nQ0003'}
            onChange={(event) => { setQuestionIdsText(event.target.value); setPreview(null); setError(""); setMessage(""); }}
          />
        </label>
        <div className="admin-placement__upload-row">
          <span className="admin-placement__hint">The order you provide becomes the default test order.</span>
          <button type="button" className="admin-placement__button admin-placement__button--primary" disabled={!questionIdsText.trim() || busy} onClick={() => void previewQuestions()}>
            <Icon name="eye" size={17} />{busy ? "Checking…" : "Preview questions"}
          </button>
        </div>
      </section>

      {preview && (
        <section className={`admin-placement__card admin-placement__preview${preview.valid ? " is-valid" : " is-invalid"}`} aria-labelledby="placement-preview-title">
          <div className="admin-placement__card-heading">
            <div><span className="admin-eyebrow">Step 2</span><h3 id="placement-preview-title">Preview placement test</h3></div>
            <strong>{preview.valid ? `${preview.questionCount} questions ready` : "Import blocked"}</strong>
          </div>
          {preview.rowIssues.length > 0 && (
            <div className="admin-placement__issues" role="alert"><strong>Fix these issues before confirming:</strong><ul>{preview.rowIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>
          )}
          {preview.valid && <>
            <p className="admin-placement__hint">This will replace the active blueprint. In-progress student attempts keep the question snapshot they started with.</p>
            <div className="admin-placement__table-wrap" tabIndex={0} role="region" aria-label="Placement question preview">
              <table className="admin-placement__table"><caption className="admin-placement__sr-only">Placement questions in imported order</caption><thead><tr><th>Order</th><th>Question ID</th><th>Round</th><th>Source story</th><th>Word</th><th>Type</th></tr></thead><tbody>
                {preview.questions.map((question) => <tr key={question.questionId}><td>{question.position}</td><td><code>{question.questionId}</code></td><td>{question.round}</td><td>{question.sourceStoryTitle}</td><td lang="zh-Hant">{question.targetWord}</td><td>{questionLabel(question)}</td></tr>)}
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
