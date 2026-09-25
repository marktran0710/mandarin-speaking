import { useEffect, useMemo, useState } from "react";
import {
  getAdminPlacementImportResults,
  type PlacementImportResults,
  type PlacementImportedStudent,
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

  if (error) return <section className="placement-data placement-data-state"><p className="admin-error" role="alert">{error}</p><button type="button" className="placement-data-button" onClick={load}>Try again</button></section>;
  if (!data) return <section className="placement-data placement-data-state"><p>Loading placement data…</p></section>;
  if (!data.available) return <section className="placement-data placement-data-state"><span className="admin-eyebrow">Synthetic import</span><h2>No imported placement data yet</h2><p>The admin view will show a batch after the workbook importer has completed successfully.</p></section>;

  const { summary } = data;
  return (
    <section className="placement-data" aria-label="Placement Data">
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
