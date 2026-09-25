import { useEffect, useMemo, useRef, useState } from "react";
import {
  confirmPlacementResponseImport,
  downloadPlacementResponseSample,
  getAdminPlacementImportResults,
  previewPlacementResponseImport,
  replacePlacementResponseImport,
  type PlacementImportResults,
  type PlacementImportedStudent,
  type PlacementResponseImportPreview,
} from "../../shared/api/placement-test";
import "./AdminPlacementDataPage.css";

function percent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function duration(milliseconds: number): string {
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

function questionTypeLabel(value: string): string {
  if (value === "basic_meaning_mcq") return "Meaning";
  if (value === "context_cloze_mcq") return "Context";
  if (value === "character_to_pinyin_typing") return "Pinyin";
  return value;
}

function MetricBar({ label, metric }: { label: string; metric: { correctCount: number; responseCount: number; accuracy: number } }) {
  const width = metric.responseCount ? `${metric.accuracy}%` : "0%";
  return (
    <div className="placement-data-bar-row">
      <div className="placement-data-bar-label"><strong>{label}</strong><span>{metric.correctCount}/{metric.responseCount} correct</span></div>
      <div className="placement-data-bar-track" aria-label={`${label}: ${percent(metric.accuracy)}`}><span style={{ width }} /></div>
      <strong className="placement-data-bar-value">{percent(metric.accuracy)}</strong>
    </div>
  );
}

function StudentDetail({ student, onClose }: { student: PlacementImportedStudent; onClose: () => void }) {
  return (
    <section className="placement-data-card placement-data-detail" aria-labelledby="placement-data-detail-title">
      <header className="placement-data-section-heading">
        <div><span className="admin-eyebrow">Response ledger</span><h2 id="placement-data-detail-title">{student.studentId} · {student.name}</h2><p>{student.sessionId} · {student.correctCount}/{student.totalQuestions} correct · {percent(student.accuracy)}</p></div>
        <button type="button" className="placement-data-ghost-button" onClick={onClose}>Close detail</button>
      </header>
      <div className="placement-data-detail-meta">
        <span><strong>{student.mastery.rowCount}</strong> mastery rows</span>
        <span><strong>{student.mastery.statuses.UNASSESSED ?? 0}</strong> unassessed</span>
        <span><strong>{duration(student.totalTimeMs)}</strong> total response time</span>
      </div>
      <div className="placement-data-table-wrap" tabIndex={0} role="region" aria-label={`Responses for ${student.studentId}`}>
        <table className="placement-data-table placement-data-response-table">
          <caption className="placement-data-sr-only">Twenty-eight placement responses for {student.studentId}</caption>
          <thead><tr><th>#</th><th>Tier</th><th>Word</th><th>Question</th><th>Selected</th><th>Expected</th><th>Result</th><th>P(L)</th><th>Time</th></tr></thead>
          <tbody>
            {student.responses.map((response) => (
              <tr key={response.itemId}>
                <td>{response.order}</td>
                <td><span className={`placement-data-tier placement-data-tier--${response.tier}`}>{response.tier.replace("tier", "T")}</span></td>
                <td lang="zh-Hant" className="placement-data-word">{response.word}</td>
                <td>{questionTypeLabel(response.questionType)}</td>
                <td>{response.selectedAnswer}</td>
                <td>{response.correctAnswer}</td>
                <td><span className={`placement-data-result ${response.correct ? "is-correct" : "is-incorrect"}`}>{response.correct ? "Correct" : "Incorrect"}</span></td>
                <td>{response.pLearned === null ? "—" : response.pLearned.toFixed(3)}</td>
                <td>{duration(response.responseTimeMs)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PlacementResponseImportPanel({ onImported }: { onImported: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PlacementResponseImportPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const pickFile = async (selected: File | null) => {
    setFile(selected);
    setPreview(null);
    setError("");
    setMessage("");
    if (!selected) return;
    setLoading(true);
    try {
      setPreview(await previewPlacementResponseImport(selected));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not preview the placement response workbook.");
    } finally {
      setLoading(false);
      // Browsers don't fire onChange when the same file path is reselected
      // unless the input is cleared first, so a retry after fixing the
      // workbook would otherwise silently keep showing this stale preview.
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const downloadSample = async () => {
    setSampleLoading(true);
    setError("");
    try {
      const blob = await downloadPlacementResponseSample();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "placement-responses-sample.xlsx";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not download the placement response sample.");
    } finally {
      setSampleLoading(false);
    }
  };

  const confirmImport = async () => {
    if (!file || !preview?.valid) return;
    if (!window.confirm("Import these student placement responses? Existing compatible sessions will be skipped.")) return;
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await confirmPlacementResponseImport(file);
      setMessage(`Imported ${result.createdResponses.toLocaleString()} responses for ${result.createdStudents} students.`);
      setFile(null);
      setPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import the placement response workbook.");
    } finally {
      setLoading(false);
    }
  };

  const replaceImport = async () => {
    if (!file) return;
    if (
      !window.confirm(
        "This deletes every SIM001-SIM040 test student and their existing placement data, then imports this workbook fresh. " +
          "Only test accounts are touched. Continue?",
      )
    ) {
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await replacePlacementResponseImport(file);
      setMessage(
        `Replaced data for ${result.deletedStudents} student(s), then imported ${result.createdResponses.toLocaleString()} responses for ${result.createdStudents} students.`,
      );
      setFile(null);
      setPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not replace the placement response workbook.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="placement-data-card placement-data-import-card" aria-labelledby="placement-data-import-title">
      <header className="placement-data-section-heading">
        <div>
          <span className="admin-eyebrow">Response import</span>
          <h2 id="placement-data-import-title">Import student placement responses</h2>
          <p>Upload the completed XLSX workbook, preview server-side grading, then confirm to write the response ledger and BKT mastery.</p>
        </div>
      </header>
      <details className="placement-data-import-format">
        <summary>Download sample and view required format</summary>
        <p>The workbook must keep the exact 10-column <code>Responses</code> header. The sample contains 40 students × 28 questions using the active blueprint.</p>
        <code className="placement-data-import-headers">student_id, student_name, placement_session_id, source_story_id, item_id, mode, selected_answer, answered_at, time_ms</code>
        <button type="button" className="placement-data-button" onClick={() => void downloadSample()} disabled={sampleLoading || loading}>
          {sampleLoading ? "Preparing sample…" : "Download XLSX sample"}
        </button>
      </details>
      <label className="placement-data-import-file">
        <span>Choose completed placement response workbook</span>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Placement response XLSX file"
          onChange={(event) => void pickFile(event.target.files?.[0] ?? null)}
          disabled={loading || sampleLoading}
        />
      </label>
      {loading && <p role="status">Validating placement response workbook…</p>}
      {error && <p className="admin-error" role="alert">{error}</p>}
      {message && <p className="placement-data-import-success" role="status">{message}</p>}
      {preview && (
        <div className={`placement-data-import-preview${preview.valid ? " is-valid" : " is-invalid"}`}>
          <strong>{preview.valid ? `${preview.responseCount.toLocaleString()} responses ready` : "Import blocked"}</strong>
          {preview.valid ? (
            <p>{preview.studentCount} students × {preview.questionCount} questions · {preview.correctCount} correct · {preview.newSessions} new sessions · {preview.existingSessions} existing sessions will be skipped.</p>
          ) : (
            <>
              <ul>{preview.rowIssues.slice(0, 20).map((issue) => <li key={issue}>{issue}</li>)}</ul>
              <p>This usually means the SIM001-SIM040 test roster already holds data from an earlier blueprint. Deleting and re-importing replaces it with a fresh run against the current blueprint.</p>
            </>
          )}
          <button type="button" className="placement-data-button" onClick={() => void confirmImport()} disabled={!preview.valid || loading}>
            Confirm import
          </button>
          {!preview.valid && (
            <button type="button" className="placement-data-button placement-data-button-danger" onClick={() => void replaceImport()} disabled={loading}>
              Delete SIM test data &amp; re-import
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export default function AdminPlacementDataPage() {
  const [data, setData] = useState<PlacementImportResults | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    void getAdminPlacementImportResults()
      .then((result) => { setData(result); setSelectedId((current) => current || result.students[0]?.studentId || ""); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load placement data."));
  };

  useEffect(load, []);

  const filteredStudents = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return (data?.students ?? []).filter((student) => !normalized || `${student.studentId} ${student.name}`.toLowerCase().includes(normalized));
  }, [data, query]);
  const selectedStudent = data?.students.find((student) => student.studentId === selectedId) ?? null;

  if (error) return <section className="placement-data placement-data-state"><p className="admin-error" role="alert">{error}</p><button type="button" className="placement-data-button" onClick={load}>Try again</button><PlacementResponseImportPanel onImported={load} /></section>;
  if (!data) return <section className="placement-data placement-data-state"><p>Loading placement data…</p></section>;
  if (!data.available) return <section className="placement-data placement-data-state"><span className="admin-eyebrow">Synthetic import</span><h2>No imported placement data yet</h2><p>The admin view will show a batch after the workbook importer has completed successfully.</p><PlacementResponseImportPanel onImported={load} /></section>;

  const { summary } = data;
  return (
    <section className="placement-data" aria-label="Placement Data">
      <PlacementResponseImportPanel onImported={load} />
      <div className="placement-data-hero">
        <div><span className="admin-eyebrow">Synthetic placement batch</span><h2>40-student response view</h2><p>Read-only view of the workbook responses, server-graded against the active quiz bank and replayed through the current BKT configuration.</p></div>
        <div className="placement-data-hero-meta"><span><strong>{data.evidenceOrigin}</strong> evidence</span><span><strong>{data.resolverVersion}</strong> resolver</span><span>Imported {data.importedAt ? new Date(data.importedAt).toLocaleString() : "—"}</span></div>
      </div>

      <div className="placement-data-kpis" aria-label="Placement import totals">
        <div><span>Students</span><strong>{summary.studentCount}</strong><small>{summary.attemptCount} completed attempts</small></div>
        <div><span>Responses</span><strong>{summary.responseCount.toLocaleString()}</strong><small>{summary.correctCount} correct · {summary.incorrectCount} incorrect</small></div>
        <div><span>Overall accuracy</span><strong>{percent(summary.accuracy)}</strong><small>server-graded from quiz bank</small></div>
        <div><span>Mastery rows</span><strong>{summary.masteryRowCount.toLocaleString()}</strong><small>{summary.masteryStatuses.UNASSESSED ?? 0} currently unassessed</small></div>
      </div>

      <div className="placement-data-analysis-grid">
        <article className="placement-data-card"><div className="placement-data-section-heading"><div><span className="admin-eyebrow">Accuracy split</span><h2>Correctness by tier</h2></div><span className="placement-data-note">n = {summary.responseCount.toLocaleString()}</span></div><div className="placement-data-bars"><MetricBar label="Tier 1 · meaning" metric={summary.tier1} /><MetricBar label="Tier 3 · context" metric={summary.tier3} /></div></article>
        <article className="placement-data-card"><div className="placement-data-section-heading"><div><span className="admin-eyebrow">Audit contract</span><h2>Evidence provenance</h2></div></div><dl className="placement-data-contract"><div><dt>Origin</dt><dd>{data.evidenceOrigin}</dd></div><div><dt>BKT eligible</dt><dd>{summary.responseCount.toLocaleString()} / {summary.responseCount.toLocaleString()}</dd></div><div><dt>Model</dt><dd>{data.modelVersions.join(", ") || "—"}</dd></div><div><dt>Parameters</dt><dd>{data.parameterFingerprints.length ? "Current runtime fingerprint" : "—"}</dd></div></dl></article>
      </div>

      <section className="placement-data-card" aria-labelledby="placement-data-students-title">
        <header className="placement-data-section-heading"><div><span className="admin-eyebrow">Student comparison</span><h2 id="placement-data-students-title">All imported students</h2></div><label className="placement-data-search"><span>Filter students</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="SIM001 or name" /></label></header>
        <div className="placement-data-student-browser-meta" aria-live="polite">
          <span><strong>{filteredStudents.length}</strong> of {summary.studentCount} students visible</span>
          <span>Scroll to browse · select a row to inspect 28 responses</span>
        </div>
        <div className="placement-data-table-wrap placement-data-student-table-wrap" tabIndex={0} role="region" aria-label="Imported student comparison">
          <table className="placement-data-table"><caption className="placement-data-sr-only">Scrollable comparison of imported placement students</caption><thead><tr><th>Student</th><th>Score</th><th>Tier 1</th><th>Tier 3</th><th>Mastery</th><th>Session</th></tr></thead><tbody>
            {filteredStudents.map((student) => <tr key={student.studentId} className={selectedId === student.studentId ? "is-selected" : ""}><td><button type="button" className="placement-data-student-button" onClick={() => setSelectedId(student.studentId)}><strong>{student.studentId}</strong><span>{student.name}</span></button></td><td><strong>{student.correctCount}/{student.totalQuestions}</strong><span>{percent(student.accuracy)}</span></td><td>{student.tier1.correctCount}/{student.tier1.responseCount}<span>{percent(student.tier1.accuracy)}</span></td><td>{student.tier3.correctCount}/{student.tier3.responseCount}<span>{percent(student.tier3.accuracy)}</span></td><td>{student.mastery.rowCount} rows<span>{student.mastery.statuses.UNASSESSED ?? 0} unassessed</span></td><td><code>{student.sessionId}</code></td></tr>)}
          </tbody></table>
        </div>
        {filteredStudents.length === 0 && <p className="placement-data-empty">No students match this filter.</p>}
      </section>

      {selectedStudent && <StudentDetail student={selectedStudent} onClose={() => setSelectedId("")} />}
    </section>
  );
}
