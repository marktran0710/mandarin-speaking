import { useEffect, useMemo, useState } from "react";
import AdminBktVerificationPage from "./AdminBktVerificationPage";
import {
  getAlgorithmVerifierBootstrap,
  getIntegrationState,
  resetIntegration,
  runBktVerification,
  runIntegration,
  runSm2Verification,
  type AlgorithmVerifierBootstrap,
  type IntegrationReport,
  type IntegrationState,
} from "../../services/api/algorithm-verifier";
import "./AdminAlgorithmVerifierPage.css";

type VerifierTab = "bkt" | "sm2" | "integration";

const bktPresets: Array<[string, Record<string, unknown>]> = [
  ["MCQ correct", { prior: 0.2, correct: true, questionFormat: "mcq" }],
  ["MCQ wrong", { prior: 0.2, correct: false, questionFormat: "mcq" }],
  ["Typed correct", { prior: 0.2, correct: true, questionFormat: "typed" }],
  ["Typed wrong", { prior: 0.2, correct: false, questionFormat: "typed" }],
  ["3 MCQ successes", { observations: [{ correct: true, questionFormat: "mcq" }, { correct: true, questionFormat: "mcq" }, { correct: true, questionFormat: "mcq" }] }],
  ["3 typed successes", { observations: [{ correct: true, questionFormat: "typed" }, { correct: true, questionFormat: "typed" }, { correct: true, questionFormat: "typed" }] }],
  ["Correct / correct / wrong", { observations: [{ correct: true, questionFormat: "mcq" }, { correct: true, questionFormat: "mcq" }, { correct: false, questionFormat: "mcq" }] }],
  ["Correct / wrong / correct", { observations: [{ correct: true, questionFormat: "mcq" }, { correct: false, questionFormat: "mcq" }, { correct: true, questionFormat: "mcq" }] }],
  ["High mastery failure", { prior: 0.999999, correct: false, questionFormat: "mcq" }],
  ["Recovery", { observations: [{ correct: false, questionFormat: "mcq" }, { correct: true, questionFormat: "typed" }, { correct: true, questionFormat: "mcq" }] }],
];

const sm2Presets: Array<[string, Record<string, unknown>]> = [
  ["Enroll STRONG word (create first schedule)", { operation: "enroll", repetitions: 0, intervalDays: 0, ease: 2.5, quality: 4 }],
  ["1st correct review after enrollment", { operation: "review", repetitions: 1, intervalDays: 1, ease: 2.5, quality: 4 }],
  ["2nd correct review after enrollment", { operation: "review", repetitions: 2, intervalDays: 6, ease: 2.5, quality: 4 }],
  ["3rd correct review after enrollment", { operation: "review", repetitions: 3, intervalDays: 15, ease: 2.5, quality: 4 }],
  ["Correct review after failure (rep 0)", { operation: "review", repetitions: 0, intervalDays: 1, ease: 2.18, quality: 4 }],
  ["Failed due review", { operation: "review", repetitions: 3, intervalDays: 15, ease: 2.5, quality: 2 }],
  ["Quality 3", { operation: "review", repetitions: 2, intervalDays: 6, ease: 2.5, quality: 3 }],
  ["Quality 5", { operation: "review", repetitions: 2, intervalDays: 6, ease: 2.5, quality: 5 }],
  ["Minimum ease", { operation: "review", repetitions: 2, intervalDays: 6, ease: 1.3, quality: 2 }],
  ["Rounding 2.5 -> 2", { operation: "review", repetitions: 2, intervalDays: 1, ease: 2.5, quality: 4 }],
  ["Rounding 7.5 -> 8", { operation: "review", repetitions: 2, intervalDays: 3, ease: 2.5, quality: 4 }],
];

function displayNumber(value: unknown, digits = 6): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "-";
}

function ResultBadge({ result }: { result: string }) {
  const className = result.toLowerCase().replace(/\s+/g, "-");
  return <span className={`algorithm-verifier-badge algorithm-verifier-badge--${className}`}>{result}</span>;
}

function StatusSummary({ bootstrap, bktStatus, sm2Status, integrationStatus }: { bootstrap: AlgorithmVerifierBootstrap; bktStatus: string; sm2Status: string; integrationStatus: string }) {
  return <div className="algorithm-verifier-summary">
    <div><span>BKT baseline</span><strong><ResultBadge result={bktStatus} /></strong><small>{bootstrap.golden.summary.passed}/{bootstrap.golden.summary.total} golden checks</small></div>
    <div><span>SM-2 baseline</span><strong><ResultBadge result={sm2Status} /></strong><small>Independent transitions</small></div>
    <div><span>Integration</span><strong><ResultBadge result={integrationStatus} /></strong><small>Development-only writes</small></div>
  </div>;
}

function BktWorkbench({ bootstrap, refreshKey, onStatus }: { bootstrap: AlgorithmVerifierBootstrap; refreshKey?: number; onStatus: (status: string) => void }) {
  const model = bootstrap.model as { parameters?: Record<string, { value?: number }> };
  const parameters = model.parameters ?? {};
  const value = (key: string, fallback: number) => parameters[key]?.value ?? fallback;
  const [input, setInput] = useState<Record<string, unknown>>({ prior: value("P_L0_initial_mastery", 0.2), correct: true, questionFormat: "mcq", learnRate: value("P_T_learn_rate", 0.15), guess: value("P_G_guess_mcq", 0.2), slip: value("P_S_slip_mcq", 0.1) });
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const applyPreset = (preset: Record<string, unknown>) => { const format = preset.questionFormat === "typed" ? "typed" : "mcq"; setInput((current) => ({ ...current, ...preset, guess: format === "typed" ? value("P_G_guess_typed", 0.05) : value("P_G_guess_mcq", 0.2), slip: format === "typed" ? value("P_S_slip_typed", 0.15) : value("P_S_slip_mcq", 0.1) })); };
  const run = () => { setError(""); void runBktVerification(input).then((next) => { setResult(next); onStatus(String(next.result)); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Could not run BKT.")); };
  const production = result?.production as Record<string, unknown> | undefined;
  const reference = result?.reference as Record<string, unknown> | undefined;
  const productionTrace = production?.trace as Array<Record<string, unknown>> | undefined;
  return <div className="algorithm-verifier-stack">
    <section className="algorithm-verifier-panel"><div className="algorithm-verifier-panel-heading"><div><span className="admin-eyebrow">Independent equation check</span><h2>Manual BKT step or sequence</h2><p>Defaults are loaded from production metadata. Edit the values to inspect a custom calculation.</p></div><ResultBadge result={result ? String(result.result) : "NOT RUN"} /></div>
      <div className="algorithm-verifier-form-grid"><label>Previous P(L)<input type="number" min="0" max="1" step="0.000001" value={String(input.prior ?? 0.2)} onChange={(event) => setInput({ ...input, prior: Number(event.target.value), observations: undefined })} /></label><label>Format<select value={String(input.questionFormat ?? "mcq")} onChange={(event) => applyPreset({ questionFormat: event.target.value, observations: undefined })}><option value="mcq">MCQ</option><option value="typed">Typed</option></select></label><label>Answer<select value={input.correct ? "correct" : "wrong"} onChange={(event) => setInput({ ...input, correct: event.target.value === "correct", observations: undefined })}><option value="correct">Correct</option><option value="wrong">Wrong</option></select></label><label>P(T)<input type="number" min="0" max="1" step="0.000001" value={String(input.learnRate ?? 0.15)} onChange={(event) => setInput({ ...input, learnRate: Number(event.target.value) })} /></label><label>Guess<input type="number" min="0" max="1" step="0.000001" value={String(input.guess ?? 0.2)} onChange={(event) => setInput({ ...input, guess: Number(event.target.value) })} /></label><label>Slip<input type="number" min="0" max="1" step="0.000001" value={String(input.slip ?? 0.1)} onChange={(event) => setInput({ ...input, slip: Number(event.target.value) })} /></label></div>
      <div className="algorithm-verifier-actions"><button type="button" className="admin-primary-button" onClick={run}>Run BKT update</button><div className="algorithm-verifier-presets"><span>Presets</span>{bktPresets.map(([label, preset]) => <button type="button" key={label} onClick={() => applyPreset(preset)}>{label}</button>)}</div></div>{error && <p className="admin-error" role="alert">{error}</p>}
    </section>
    {result && <section className="algorithm-verifier-panel algorithm-verifier-results"><div className="algorithm-verifier-results-grid"><article><h3>Production</h3><dl><div><dt>Posterior</dt><dd>{displayNumber(production?.posterior)}</dd></div><div><dt>P(L) new</dt><dd>{displayNumber(production?.resultingMastery)}</dd></div></dl></article><article><h3>Independent reference</h3><dl><div><dt>Posterior</dt><dd>{displayNumber(reference?.posterior)}</dd></div><div><dt>P(L) new</dt><dd>{displayNumber(reference?.resultingMastery)}</dd></div></dl></article><article><h3>Difference / tolerance</h3><dl><div><dt>Absolute</dt><dd>{displayNumber(result.difference)}</dd></div><div><dt>Tolerance</dt><dd>{displayNumber(result.tolerance)}</dd></div></dl></article></div>{productionTrace && <div className="algorithm-verifier-history"><strong>Independent sequence progression</strong>{productionTrace.map((step, index) => <div key={index} className="algorithm-verifier-trace-row"><span>Step {index + 1}</span><span>{step.correct ? "correct" : "wrong"}</span><span>prior {displayNumber(step.prior)}</span><span>posterior {displayNumber(step.posterior)}</span><span>final {displayNumber(step.resultingMastery)}</span></div>)}</div>}<pre className="algorithm-verifier-formula">{JSON.stringify(result.formula, null, 2)}</pre><p className="algorithm-verifier-note">The effective prior is clamped to [0.000001, 0.999999] before the observation update and the final probability is clamped after the learning transition.</p></section>}
    <AdminBktVerificationPage refreshKey={refreshKey} />
  </div>;
}

function Sm2Workbench({ onStatus }: { onStatus: (status: string) => void }) {
  const [input, setInput] = useState<Record<string, unknown>>({ operation: "review", repetitions: 1, intervalDays: 1, ease: 2.5, quality: 4, now: "2026-08-02T00:00:00Z", daySeconds: 86400 });
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const enrolling = input.operation === "enroll";
  const changeInput = (changes: Record<string, unknown>) => {
    setInput((current) => ({ ...current, ...changes }));
    setResult(null);
    setError("");
    onStatus("NOT RUN");
  };
  const run = () => { setError(""); void runSm2Verification(input).then((next) => { setResult(next); onStatus(String(next.result)); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Could not run SM-2.")); };
  const production = result?.production as Record<string, unknown> | undefined;
  const reference = result?.reference as Record<string, unknown> | undefined;
  const completedInputs = result?.inputs as Record<string, unknown> | undefined;
  const enrolled = completedInputs?.operation === "enroll";
  return <div className="algorithm-verifier-stack">
    <section className="algorithm-verifier-panel">
      <div className="algorithm-verifier-panel-heading">
        <div><span className="admin-eyebrow">Modified SM-2 behavior</span><h2>Enrollment or due review</h2><p>Production enrollment creates the first schedule at rep=1, interval=1, ease=2.5, with no review quality. The first correct due review then moves to rep=2, interval=6.</p></div>
        <ResultBadge result={result ? String(result.result) : "NOT RUN"} />
      </div>
      <div className="algorithm-verifier-form-grid">
        <label>Operation<select value={String(input.operation)} onChange={(event) => changeInput({ operation: event.target.value })}><option value="review">Review an existing schedule</option><option value="enroll">Enroll STRONG word (create first schedule)</option></select></label>
        <label>Repetitions before review<input type="number" min="0" disabled={enrolling} value={String(input.repetitions ?? 0)} onChange={(event) => changeInput({ repetitions: Number(event.target.value) })} /></label>
        <label>Interval before review (scheduling days)<input type="number" min="0" disabled={enrolling} value={String(input.intervalDays ?? 0)} onChange={(event) => changeInput({ intervalDays: Number(event.target.value) })} /></label>
        <label>Ease before review<input type="number" min="1.3" step="0.01" disabled={enrolling} value={String(input.ease ?? 2.5)} onChange={(event) => changeInput({ ease: Number(event.target.value) })} /></label>
        <label>Review quality (0-5)<input type="number" min="0" max="5" disabled={enrolling} value={String(input.quality ?? 4)} onChange={(event) => changeInput({ quality: Number(event.target.value) })} /></label>
        <label>{enrolling ? "Enrollment timestamp (UTC)" : "Review timestamp (UTC)"}<input type="datetime-local" value={String(input.now).slice(0, 16)} onChange={(event) => changeInput({ now: `${event.target.value}:00Z` })} /></label>
        <label>Scheduling day seconds<input type="number" min="1" value={String(input.daySeconds ?? 86400)} onChange={(event) => changeInput({ daySeconds: Number(event.target.value) })} /></label>
      </div>
      <p className="algorithm-verifier-note">{enrolling
        ? "Enrollment requires no existing schedule. The disabled review fields are ignored; no answer is graded and no quality is used. The timestamp starts the one-day wait until the first due review."
        : "Inputs describe the state before the review; the resulting state appears below after Run. Repetitions include the initial schedule created at enrollment. Student grading maps correct to q=4 and wrong to q=2."}</p>
      <div className="algorithm-verifier-actions">
        <button type="button" className="admin-primary-button" onClick={run}>{enrolling ? "Calculate enrollment schedule" : "Calculate review result"}</button>
        <div className="algorithm-verifier-presets"><span>Presets</span>{sm2Presets.map(([label, preset]) => <button type="button" key={label} onClick={() => changeInput(preset)}>{label}</button>)}</div>
      </div>
      {error && <p className="admin-error" role="alert">{error}</p>}
    </section>
    {result && <section className="algorithm-verifier-panel algorithm-verifier-results" aria-label="SM-2 result after operation">
      <div className="algorithm-verifier-panel-heading"><div><h2>{enrolled ? "After enrollment: first schedule" : "After review: next schedule"}</h2><p>{enrolled ? "Before enrollment: no SRS record and no due date. Quality: none." : `Before review: rep=${String(completedInputs?.repetitions)}, interval=${String(completedInputs?.intervalDays)}, ease=${displayNumber(completedInputs?.ease)}. Quality: ${String(completedInputs?.quality)}.`}</p></div></div>
      <div className="algorithm-verifier-results-grid">
        <article><h3>Production output</h3><dl>
          <div><dt>Operation</dt><dd>{enrolled ? "Enrollment: create first schedule" : "Review: update existing schedule"}</dd></div>
          <div><dt>Repetitions after operation</dt><dd>{String(production?.repetitions)}</dd></div>
          <div><dt>Interval after operation</dt><dd>{String(production?.intervalDays)} scheduling days</dd></div>
          <div><dt>Ease</dt><dd>{displayNumber(production?.ease)}</dd></div>
          <div><dt>Operation timestamp (UTC)</dt><dd>{String(completedInputs?.now)}</dd></div>
          <div><dt>Next due</dt><dd>{String(production?.nextDue)}</dd></div>
        </dl></article>
        <article><h3>Independent reference output</h3><dl>
          <div><dt>Repetitions after operation</dt><dd>{String(reference?.repetitions)}</dd></div>
          <div><dt>Interval after operation</dt><dd>{String(reference?.intervalDays)} scheduling days</dd></div>
          <div><dt>Ease</dt><dd>{displayNumber(reference?.ease)}</dd></div>
          <div><dt>Next due</dt><dd>{String(reference?.nextDue)}</dd></div>
        </dl></article>
        <article><h3>Raw arithmetic</h3><dl>
          <div><dt>Raw interval product</dt><dd>{displayNumber(result.rawInterval)}</dd></div>
          <div><dt>Quality used</dt><dd>{enrolled ? "None (enrollment)" : String(completedInputs?.quality)}</dd></div>
          <div><dt>Minimum ease</dt><dd>1.300000</dd></div>
        </dl></article>
      </div>
      <p className="algorithm-verifier-note">Production timeline: enrollment at T0 schedules T0 + 1D; a correct review at that due time schedules T0 + 7D (6D after the review). Each preset is an independent calculation. These calculations do not write student data or enforce the production due-cycle guards. Production advances only an existing, due schedule, once per due cycle. Intervals use Python round() ties-to-even, including 2.5 -&gt; 2 and 7.5 -&gt; 8.</p>
    </section>}
  </div>;
}

function IntegrationWorkbench({ bootstrap, onStatus }: { bootstrap: AlgorithmVerifierBootstrap; onStatus: (status: string) => void }) {
  const [state, setState] = useState<IntegrationState | null>(null);
  const [report, setReport] = useState<IntegrationReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = () => void getIntegrationState().then((next) => { setState(next); setReport(next.report); onStatus(next.status === "COMPLETE" ? "PASS" : next.enabled ? "NOT RUN" : "BLOCKED"); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load integration state."));
  useEffect(load, []);
  const mutate = (action: () => Promise<unknown>) => { setBusy(true); setError(""); void action().then((value) => { if (value && typeof value === "object" && "steps" in value) { setReport(value as IntegrationReport); onStatus("PASS"); } return load(); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Integration action failed.")).finally(() => setBusy(false)); };
  const fixtureWords = state?.fixture.words ?? bootstrap.integration.fixture?.words ?? [];
  const focus = useMemo(() => fixtureWords.filter((word) => word.focus), [fixtureWords]);
  return <div className="algorithm-verifier-stack"><section className="algorithm-verifier-panel"><div className="algorithm-verifier-panel-heading"><div><span className="admin-eyebrow">Production wiring</span><h2>Integration scenario</h2><p>Real published questions are sent through the production resolver for a reserved synthetic student.</p></div><ResultBadge result={report?.completed ? "PASS" : state?.enabled ? "NOT RUN" : "BLOCKED"} /></div>{!bootstrap.integration.enabled && <div className="algorithm-verifier-blocked">Integration is blocked until development mode, the fixture, and both mathematical baseline suites are ready.</div>}{bootstrap.integration.fixtureError && <div className="algorithm-verifier-blocked">{bootstrap.integration.fixtureError}</div>}{error && <p className="admin-error" role="alert">{error}</p>}<div className="algorithm-verifier-actions"><button type="button" className="admin-primary-button" disabled={!bootstrap.integration.enabled || busy || !bootstrap.integration.fixture} onClick={() => mutate(runIntegration)}>{busy ? "Running..." : "Run complete integration scenario"}</button><button type="button" className="admin-secondary-button" disabled={!bootstrap.integration.enabled || busy} onClick={() => mutate(resetIntegration)}>Reset verifier data</button><span className="algorithm-verifier-mono">{bootstrap.integration.studentId}</span></div><div className="algorithm-verifier-fixture"><div><strong>Focus words</strong><span>{focus.map((word) => `${word.word} (${word.wordId})`).join(" | ")}</span></div><div><strong>Supporting diagnostics</strong><span>{fixtureWords.filter((word) => !word.focus).map((word) => word.word).join(" | ")}</span></div></div></section>{report && <section className="algorithm-verifier-panel"><div className="algorithm-verifier-panel-heading"><div><span className="admin-eyebrow">Persisted trace</span><h2>Integration history</h2><p>Each state is reread from committed BKT, application mastery, SRS, and queue data.</p></div><button type="button" className="admin-secondary-button" onClick={() => navigator.clipboard?.writeText(JSON.stringify(report, null, 2))}>Copy JSON</button></div><div className="algorithm-verifier-history">{report.steps.map((step) => <article key={step.id}><div><strong>{step.label}</strong><span>{step.state.timestamp}</span></div><div className="algorithm-verifier-mini-grid">{step.state.words.filter((word) => word.focus).map((word) => <div key={word.wordId}><strong>{word.word}</strong><span>P(L) {displayNumber(word.pLearned)}</span><span>{word.masteryStatus ?? "Not assessed"}</span><span>{word.schedule ? `SRS ${word.schedule.intervalDays}d / rep ${word.schedule.reps}` : "No SRS schedule"}</span><span>{word.queueReason ? `Queue: ${word.queueReason}` : "Not queued"}</span></div>)}</div></article>)}</div></section>}</div>;
}

export default function AdminAlgorithmVerifierPage({ initialTab = "bkt", refreshKey = 0 }: { initialTab?: VerifierTab; refreshKey?: number }) {
  const [tab, setTab] = useState<VerifierTab>(initialTab);
  const [bootstrap, setBootstrap] = useState<AlgorithmVerifierBootstrap | null>(null);
  const [error, setError] = useState("");
  const [bktStatus, setBktStatus] = useState<string>("NOT RUN");
  const [sm2Status, setSm2Status] = useState<string>("NOT RUN");
  const [integrationStatus, setIntegrationStatus] = useState<string>("NOT RUN");
  useEffect(() => { void getAlgorithmVerifierBootstrap().then((next) => { setBootstrap(next); setBktStatus(next.baselineSuites?.bkt ?? "NOT RUN"); setSm2Status(next.baselineSuites?.sm2 ?? "NOT RUN"); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load Algorithm Verifier.")); }, []);
  if (error) return <section className="algorithm-verifier algorithm-verifier-state"><p className="admin-error" role="alert">{error}</p></section>;
  if (!bootstrap) return <section className="algorithm-verifier algorithm-verifier-state"><p>Loading Algorithm Verifier...</p></section>;
  return <section className="algorithm-verifier" aria-label="Algorithm Verifier"><header className="algorithm-verifier-hero"><div><span className="admin-eyebrow">Research / Learning Engine</span><h1>Algorithm Verifier</h1><p>Compare production behavior with independent equations, then inspect how the two models are wired together.</p></div><StatusSummary bootstrap={bootstrap} bktStatus={bktStatus} sm2Status={sm2Status} integrationStatus={integrationStatus} /></header><nav className="algorithm-verifier-tabs" role="tablist" aria-label="Algorithm verifier tabs">{(["bkt", "sm2", "integration"] as const).map((value) => <button type="button" role="tab" aria-selected={tab === value} className={tab === value ? "is-active" : ""} key={value} onClick={() => setTab(value)}>{value === "sm2" ? "SM-2" : value === "bkt" ? "BKT" : "Integration"}</button>)}</nav>{tab === "bkt" && <BktWorkbench bootstrap={bootstrap} refreshKey={refreshKey} onStatus={setBktStatus} />}{tab === "sm2" && <Sm2Workbench onStatus={setSm2Status} />}{tab === "integration" && <IntegrationWorkbench bootstrap={bootstrap} onStatus={setIntegrationStatus} />}</section>;
}
