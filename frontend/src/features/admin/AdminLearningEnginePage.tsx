import { useEffect, useState } from "react";
import {
  getLearningEngineMetadata,
  type LearningEngineMetadata,
  type LearningEngineParameter,
  type LearningEngineThreshold,
} from "../../services/api/learning-engine";
import "./AdminLearningEnginePage.css";

function ProvenanceTag({ provenance }: { provenance: string }) {
  return <span className="learning-engine-provenance">{provenance.replace(/_/g, " ").toLowerCase()}</span>;
}

function ParameterTable({ parameters }: { parameters: Record<string, LearningEngineParameter> }) {
  return (
    <table className="learning-engine-table">
      <thead>
        <tr><th>Parameter</th><th>Value</th><th>Provenance</th></tr>
      </thead>
      <tbody>
        {Object.entries(parameters).map(([name, param]) => (
          <tr key={name}>
            <td><code>{name}</code></td>
            <td className="learning-engine-value">{param.value}</td>
            <td><ProvenanceTag provenance={param.provenance} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ThresholdTable({ thresholds }: { thresholds: Record<string, LearningEngineThreshold> }) {
  return (
    <table className="learning-engine-table">
      <thead>
        <tr><th>Threshold</th><th>Value</th><th>Gates progression?</th><th>Purpose</th></tr>
      </thead>
      <tbody>
        {Object.entries(thresholds).map(([name, threshold]) => (
          <tr key={name}>
            <td><code>{name}</code></td>
            <td className="learning-engine-value">{threshold.value}</td>
            <td>
              <span className={`learning-engine-gate ${threshold.controlsProgression ? "is-gating" : ""}`}>
                {threshold.controlsProgression ? "Yes" : "No — diagnostic only"}
              </span>
            </td>
            <td className="learning-engine-purpose">{threshold.purpose}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CalibrationBanner({ text }: { text: string }) {
  return <p className="learning-engine-calibration">{text}</p>;
}

export default function AdminLearningEnginePage() {
  const [data, setData] = useState<LearningEngineMetadata | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void getLearningEngineMetadata()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load Learning Engine metadata."));
  }, []);

  if (error) return <p className="admin-error">{error}</p>;
  if (!data) return <p className="learning-engine-loading">Loading…</p>;

  const { bkt, retention, voice } = data;

  return (
    <section className="learning-engine" aria-label="Learning Engine">
      <p className="learning-engine-overview">
        Three engines run production: <strong>Bayesian Knowledge Tracing</strong> estimates vocabulary mastery,
        <strong> Modified SM-2</strong> schedules retention review, and a Praat-based acoustic pipeline plus
        deterministic scoring produces pronunciation feedback. Every value below is read live from the code
        that actually runs — nothing here is hand-copied documentation that can drift from production.
      </p>

      <article className="learning-engine-card">
        <header>
          <h2>{bkt.name}</h2>
          <span className="learning-engine-version">{bkt.version}</span>
        </header>
        <p className="learning-engine-purpose-text">{bkt.purpose}</p>
        <CalibrationBanner text={bkt.calibrationStatus} />
        <div className="learning-engine-formula">
          <p>Correct: P(L|correct) = L(1−S) / [L(1−S) + (1−L)G]</p>
          <p>Incorrect: P(L|incorrect) = LS / [LS + (1−L)(1−G)]</p>
          <p>Transition: P(L_next) = P(L|obs) + [1 − P(L|obs)] × T</p>
        </div>
        <ParameterTable parameters={bkt.parameters} />
        <ol className="learning-engine-pipeline">
          {bkt.pipeline.map((step) => <li key={step}>{step}</li>)}
        </ol>
        <p className="learning-engine-reference">{bkt.reference.citation} {bkt.reference.doi && <>(DOI: {bkt.reference.doi})</>}</p>
        <p className="learning-engine-reference-note">{bkt.reference.note}</p>
      </article>

      <article className="learning-engine-card">
        <header>
          <h2>{retention.name}</h2>
          <span className="learning-engine-version">{retention.version}</span>
        </header>
        <p className="learning-engine-purpose-text">{retention.purpose}</p>
        <CalibrationBanner text={retention.calibrationStatus} />
        <div className="learning-engine-formula">
          <p>Ease update: {retention.easeFormula}</p>
          <p>Interval sequence: {retention.intervalSequence}</p>
        </div>
        <ParameterTable parameters={retention.parameters} />
        <p className="learning-engine-note">{retention.conceptualSeparation}</p>
        <p className="learning-engine-reference">{retention.reference.citation}</p>
        <p className="learning-engine-reference-note">{retention.reference.note}</p>
      </article>

      <article className="learning-engine-card">
        <header>
          <h2>Voice Feedback Engine</h2>
        </header>
        <ol className="learning-engine-pipeline">
          {voice.pipeline.map((step) => <li key={step}>{step}</li>)}
        </ol>
        <CalibrationBanner text={voice.calibrationStatus} />

        <h3>Acoustic analysis</h3>
        <p className="learning-engine-purpose-text">
          {voice.acousticEngine.technology} — {voice.acousticEngine.purpose}.
        </p>
        <p className="learning-engine-reference">{voice.acousticEngine.reference.citation}</p>
        <p className="learning-engine-reference-note">{voice.acousticEngine.reference.note}</p>

        <h3>Tone scoring</h3>
        <p className="learning-engine-note">{voice.toneScoring.note}</p>

        <h3>Recording quality gate</h3>
        <p className="learning-engine-purpose-text">{voice.qualityGate.principle}</p>
        <ul className="learning-engine-reasons">
          {voice.qualityGate.reasons.map((reason) => <li key={reason}><code>{reason}</code></li>)}
        </ul>

        <h3>Runtime thresholds</h3>
        <ThresholdTable thresholds={voice.thresholds} />

        <h3>Speech recognition</h3>
        <table className="learning-engine-table">
          <thead><tr><th>Provider</th><th>Role</th><th>Configured</th></tr></thead>
          <tbody>
            {voice.asrProviders.map((provider) => (
              <tr key={provider.provider}>
                <td>{provider.provider}</td>
                <td>{provider.role}</td>
                <td>{provider.configured ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3>AI coaching feedback</h3>
        <p className="learning-engine-note">Default provider: <code>{voice.feedbackProviders.defaultProvider}</code>. {voice.feedbackProviders.fallbackBehavior}</p>
        <table className="learning-engine-table">
          <thead><tr><th>Provider</th><th>Role</th><th>Configured</th></tr></thead>
          <tbody>
            {voice.feedbackProviders.providers.map((provider) => (
              <tr key={provider.provider}>
                <td>{provider.provider}</td>
                <td>{provider.role}</td>
                <td>{provider.configured ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}
