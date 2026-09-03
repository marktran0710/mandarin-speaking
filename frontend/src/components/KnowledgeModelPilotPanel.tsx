import { useEffect, useMemo, useState } from "react";
import {
  canUseDatabase,
  getKnowledgeModelAnalytics,
  type KnowledgeAnalyticsResponse,
  type KnowledgeModelResult,
} from "../services/database";

function formatMetric(value: number | null): string {
  return value === null ? "--" : value.toFixed(3);
}

function modelLabel(model: "pfa" | "bkt"): string {
  return model === "pfa" ? "PFA" : "BKT";
}

function masteryLabel(result: KnowledgeModelResult): string {
  return result.masteryInterpretation === "latent_mastery_probability"
    ? "Latent mastery"
    : "Predicted correctness";
}

function ModelCard({ result }: { result: KnowledgeModelResult }) {
  const evaluation = result.evaluation;
  return (
    <article className="knowledge-model-card">
      <div className="knowledge-model-card-heading">
        <div>
          <span className="knowledge-model-eyebrow">Challenger model</span>
          <h3>{modelLabel(result.model)}</h3>
        </div>
        <span className={`knowledge-status is-${evaluation.status}`}>
          {evaluation.status === "ready" ? "Ready to compare" : "Insufficient data"}
        </span>
      </div>
      <div className="knowledge-model-metrics">
        <div><span>Log loss</span><strong>{formatMetric(evaluation.logLoss)}</strong></div>
        <div><span>Brier</span><strong>{formatMetric(evaluation.brierScore)}</strong></div>
        <div><span>Calibration</span><strong>{formatMetric(evaluation.calibrationError)}</strong></div>
      </div>
      <p>{evaluation.predictionCount} sequential predictions from {evaluation.responseCount} eligible responses. {masteryLabel(result)} is shown per skill.</p>
    </article>
  );
}

export default function KnowledgeModelPilotPanel() {
  const [data, setData] = useState<KnowledgeAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    if (!canUseDatabase()) {
      setLoading(false);
      setError("Backend is not configured.");
      return () => { active = false; };
    }
    void getKnowledgeModelAnalytics("compare")
      .then((result) => { if (active) setData(result); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load learning model analytics."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const topSkills = useMemo(() => {
    if (!data || data.model !== "compare") return [];
    return data.models.pfa.students
      .flatMap((student) => student.skills.map((skill) => ({ ...skill, studentId: student.studentId, studentName: student.studentName })))
      .sort((a, b) => a.mastery - b.mastery)
      .slice(0, 8);
  }, [data]);

  return (
    <section className="teacher-panel knowledge-model-pilot" aria-label="Learning model pilot">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Learning model pilot</p>
          <h2>PFA vs BKT</h2>
        </div>
        <span className="knowledge-provisional-badge">Admin-only · provisional</span>
      </div>
      <p className="knowledge-model-intro">Sequential predictions from vocabulary quiz history. This pilot does not change scoring, weak words, gating, or student feedback.</p>
      {loading && <p className="teacher-empty-panel">Calculating model comparison…</p>}
      {!loading && error && <p className="teacher-empty-panel">{error}</p>}
      {!loading && !error && data?.model === "compare" && (
        <>
          <div className="knowledge-model-cards">
            <ModelCard result={data.models.pfa} />
            <ModelCard result={data.models.bkt} />
          </div>
          <div className="knowledge-model-summary">
            <strong>Current recommendation:</strong>{" "}
            {data.recommendedModel ? modelLabel(data.recommendedModel) : "No winner yet"}
            <span>{data.dataQuality.eligibleResponses} eligible responses · {data.dataQuality.skillCount} vocabulary skills</span>
          </div>
          {topSkills.length > 0 && (
            <div className="knowledge-skill-table-wrap">
              <h3>Lowest current PFA predicted correctness</h3>
              <table className="measurement-table knowledge-skill-table">
                <thead><tr><th>Student</th><th>Word</th><th>Mastery</th><th>Exposure</th><th>Confidence</th></tr></thead>
                <tbody>{topSkills.map((skill) => (
                  <tr key={`${skill.studentId}:${skill.conceptId}`}>
                    <td>{skill.studentName ?? skill.studentId}</td>
                    <td>{skill.conceptId}</td>
                    <td>{Math.round(skill.mastery * 100)}%</td>
                    <td>{skill.exposures}</td>
                    <td>{skill.confidence}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
