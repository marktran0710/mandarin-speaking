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

function formatParameter(value: number | undefined): string {
  return value === undefined ? "--" : value.toFixed(3);
}

const PFA_DEFAULTS = { intercept: 0, success_weight: 0.35, failure_weight: -0.55, l2: 1 };
const BKT_DEFAULTS = { prior: 0.2, learn: 0.15, guess: 0.2, slip: 0.1 };

function MethodologyCard({ model, parameters }: { model: "pfa" | "bkt"; parameters?: Record<string, number> }) {
  if (model === "pfa") {
    const values = { ...PFA_DEFAULTS, ...parameters };
    return (
      <article className="knowledge-methodology-card">
        <div className="knowledge-methodology-card-heading">
          <div>
            <span className="knowledge-model-eyebrow">Performance Factors Analysis</span>
            <h4>PFA</h4>
          </div>
          <span className="knowledge-methodology-tag">Count-based</span>
        </div>
        <p>Tracks prior correct and incorrect responses for each student × vocabulary skill.</p>
        <code className="knowledge-formula">p(correct) = σ(β₀ + βs·successes + βf·failures){"\n"}σ(z) = 1 / (1 + e⁻ᶻ)</code>
        <dl className="knowledge-parameter-list">
          <div><dt>β₀ intercept</dt><dd>{formatParameter(values.intercept)}</dd></div>
          <div><dt>βs success weight</dt><dd>{formatParameter(values.success_weight)}</dd></div>
          <div><dt>βf failure weight</dt><dd>{formatParameter(values.failure_weight)}</dd></div>
          <div><dt>λ L2 regularization</dt><dd>{formatParameter(values.l2)}</dd></div>
        </dl>
        <a className="knowledge-paper-link" href="https://doi.org/10.3233/978-1-60750-028-5-531" target="_blank" rel="noreferrer">
          Pavlik, Cen &amp; Koedinger (2009) · Performance Factors Analysis – A New Alternative to Knowledge Tracing
        </a>
      </article>
    );
  }

  const values = { ...BKT_DEFAULTS, ...parameters };
  return (
    <article className="knowledge-methodology-card">
      <div className="knowledge-methodology-card-heading">
        <div>
          <span className="knowledge-model-eyebrow">Bayesian Knowledge Tracing</span>
          <h4>BKT</h4>
        </div>
        <span className="knowledge-methodology-tag">State model</span>
      </div>
      <p>Maintains a latent mastery probability for each student × vocabulary skill.</p>
      <code className="knowledge-formula">p(correct) = L·(1 − slip) + (1 − L)·guess{"\n"}Lposterior(correct) = L·(1 − slip) / p(correct){"\n"}Lposterior(incorrect) = L·slip / (1 − p(correct)){"\n"}Lnext = Lposterior + (1 − Lposterior)·learn</code>
      <dl className="knowledge-parameter-list">
        <div><dt>Prior mastery</dt><dd>{formatParameter(values.prior)}</dd></div>
        <div><dt>Learn transition</dt><dd>{formatParameter(values.learn)}</dd></div>
        <div><dt>Guess</dt><dd>{formatParameter(values.guess)}</dd></div>
        <div><dt>Slip</dt><dd>{formatParameter(values.slip)}</dd></div>
      </dl>
      <p className="knowledge-methodology-note">After each response, the posterior uses Bayes’ rule; a correct answer uses 1 − slip, and an incorrect answer uses slip.</p>
      <a className="knowledge-paper-link" href="https://doi.org/10.1007/BF01099821" target="_blank" rel="noreferrer">
        Corbett &amp; Anderson (1994) · Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge
      </a>
    </article>
  );
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
      <details className="knowledge-methodology" open>
        <summary>Papers &amp; formulas used in this pilot</summary>
        <p className="knowledge-methodology-intro">The formulas below mirror <code>backend/analytics/knowledge_tracing.py</code>. Parameters are fitted or defaulted for this comparison run; they are not a permanent production policy. Evaluation uses a chronological 50/50 split: the first half establishes the model, then each later response is predicted before the model updates.</p>
        <div className="knowledge-methodology-grid">
          <MethodologyCard model="pfa" parameters={data?.model === "compare" ? data.models.pfa.parameters : undefined} />
          <MethodologyCard model="bkt" parameters={data?.model === "compare" ? data.models.bkt.parameters : undefined} />
        </div>
      </details>
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
