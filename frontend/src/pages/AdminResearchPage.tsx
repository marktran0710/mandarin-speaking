import { useState } from "react";
import { getResearchAdminSummary, type ResearchAdminSummary } from "../services/api/research-admin";
import "./AdminResearchPage.css";

const CONDITION_ORDER = ["C", "B", "S", "BS"] as const;

function pct(value: number | null, total: number): string {
  if (!total) return "—";
  return `${Math.round(((value ?? 0) / total) * 100)}%`;
}

/** Task 8.4: a compact standalone page rather than folding condition data
 * into the normal Teacher Dashboard (Task 8.5 - a teacher must never see
 * C/BKT/SRS/BS). Admin only: the backend endpoint this calls is the one
 * place in the whole app allowed to return condition labels at all. */
export default function AdminResearchPage() {
  const [studyIdInput, setStudyIdInput] = useState("");
  const [summary, setSummary] = useState<ResearchAdminSummary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const studyId = studyIdInput.trim();
    if (!studyId) return;
    setLoading(true);
    setError("");
    try {
      setSummary(await getResearchAdminSummary(studyId));
    } catch (err) {
      setSummary(null);
      setError(err instanceof Error ? err.message : "Could not load this study.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="admin-research" aria-label="Research study fidelity">
      <div className="admin-toolbar">
        <input
          placeholder="Study id"
          value={studyIdInput}
          onChange={(event) => setStudyIdInput(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void load(); }}
        />
        <button type="button" className="primary" onClick={() => void load()} disabled={loading || !studyIdInput.trim()}>
          {loading ? "Loading…" : "Load study"}
        </button>
      </div>
      {error && <p className="admin-error">{error}</p>}

      {summary && (
        <>
          <section className="admin-research-block" aria-labelledby="ar-status-title">
            <h2 id="ar-status-title">{summary.name}</h2>
            <p className="admin-research-status">{summary.status.toUpperCase()}</p>
          </section>

          <section className="admin-metrics" aria-label="Participants">
            <div><span>Participants (active / total)</span><strong>{summary.participants.active} / {summary.participants.total}</strong></div>
            <div><span>Total assignments</span><strong>{summary.totalAssignments}</strong></div>
            <div><span>Core rounds completed</span><strong>{summary.fidelity.coreCompletedCount}</strong></div>
          </section>

          <section className="admin-research-block" aria-labelledby="ar-balance-title">
            <h3 id="ar-balance-title">Assignment balance</h3>
            <ul className="admin-research-condition-list">
              {CONDITION_ORDER.map((condition) => (
                <li key={condition}>
                  <span>{condition}</span>
                  <strong>{pct(summary.assignmentBalance[condition] ?? 0, summary.totalAssignments)}</strong>
                  <small>{summary.assignmentBalance[condition] ?? 0}</small>
                </li>
              ))}
            </ul>
          </section>

          <section className="admin-research-block" aria-labelledby="ar-practice-title">
            <h3 id="ar-practice-title">Practice fidelity</h3>
            <p>
              BKT ON: <strong>{summary.fidelity.practice.bktOnCount}</strong> items selected · BKT OFF:{" "}
              <strong>{summary.fidelity.practice.bktOffCount}</strong> items selected across{" "}
              {summary.fidelity.practice.sessionsCreated} sessions.
            </p>
          </section>

          <section className="admin-research-block" aria-labelledby="ar-review-title">
            <h3 id="ar-review-title">Review fidelity</h3>
            <p>
              <strong>{summary.fidelity.retention.reviewsDelivered}</strong> reviews delivered
              {summary.fidelity.retention.averageDelayDays !== null && (
                <> · average delay <strong>{summary.fidelity.retention.averageDelayDays.toFixed(1)}</strong> days</>
              )}
            </p>
          </section>

          <section className="admin-research-block" aria-labelledby="ar-probes-title">
            <h3 id="ar-probes-title">Probe completion</h3>
            <p>
              <strong>{summary.fidelity.probes.completed}</strong> / {summary.fidelity.probes.assigned} completed
              {summary.fidelity.probes.completionRate !== null && (
                <> (<strong>{Math.round(summary.fidelity.probes.completionRate * 100)}%</strong>)</>
              )}
            </p>
          </section>

          <section className="admin-research-block" aria-labelledby="ar-violations-title">
            <h3 id="ar-violations-title">Policy violations</h3>
            <p className={summary.fidelity.policyViolations > 0 ? "admin-error" : undefined}>
              <strong>{summary.fidelity.policyViolations}</strong>{" "}
              {summary.fidelity.policyViolations === 1 ? "violation" : "violations"}
            </p>
          </section>
        </>
      )}
    </section>
  );
}
