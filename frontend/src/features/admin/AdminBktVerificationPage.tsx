import { useEffect, useMemo, useState } from "react";
import {
  getBktVerificationBootstrap,
  getBktVerificationTrace,
  type BktVerificationBootstrap,
  type BktVerificationTraceResponse,
} from "../../services/api/bkt-verification";
import { GoldenSection, LiveSection, StatusBadge, formatProbability } from "./AdminBktVerificationPanels";
import "./AdminBktVerificationPage.css";

function ParameterList({ data }: { data: BktVerificationBootstrap["model"] }) {
  const values: Array<[string, string]> = [
    ["P(L0)", formatProbability(data.parameters.pL0)],
    ["P(T)", formatProbability(data.parameters.pT)],
    ["MCQ Guess", formatProbability(data.parameters.mcqGuess)],
    ["MCQ Slip", formatProbability(data.parameters.mcqSlip)],
    ["Typed Guess", formatProbability(data.parameters.typedGuess)],
    ["Typed Slip", formatProbability(data.parameters.typedSlip)],
    ["Mastery threshold", formatProbability(data.parameters.masteryThreshold)],
    ["Minimum observations", String(data.parameters.minimumObservations)],
  ];
  return <dl className="bkt-verification-parameters">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function HowToTest({ model, liveTrace }: { model: BktVerificationBootstrap["model"] | null; liveTrace: BktVerificationTraceResponse["trace"] }) {
  const priorInstruction = liveTrace?.coldStart.source === "Placement Chapter Prior"
    ? "the student's Placement Chapter Prior"
    : `${formatProbability(model?.parameters.pL0 ?? 0.2)} global BKT prior`;
  return (
    <details className="bkt-verification-how-to">
      <summary>How to verify BKT</summary>
      <div className="bkt-verification-how-to-grid">
        <article><h3>Test 1 · Golden math check</h3><ol><li>Open Golden BKT Checks.</li><li>Confirm every baseline scenario shows PASS.</li><li>If any scenario fails, do not trust downstream mastery results.</li></ol></article>
        <article><h3>Test 2 · Placement correct answer</h3><ol><li>Select a synthetic student such as SIM001.</li><li>Choose a placement word answered correctly and inspect its first trace step.</li><li>Check the prior, guess/slip and learning rate against the selected parameter table.</li><li>Expected and Actual should show PASS across all recorded responses.</li></ol></article>
        <article><h3>Test 3 · Placement incorrect answer</h3><ol><li>Choose a placement word answered incorrectly and inspect its first trace step.</li><li>Confirm it uses the global prior followed by the learning transition. Later responses should continue from that result.</li></ol></article>
        <article><h3>Test 4 · Unseen word</h3><ol><li>Choose known vocabulary the student has never answered.</li><li>Confirm evidence is 0, P(L) is {priorInstruction}, BKT status is UNASSESSED, and Review status is NOT_ASSESSED.</li></ol></article>
        <article><h3>Test 5 · Three observations</h3><ol><li>Select a word with at least three responses.</li><li>Inspect the trace.</li><li>Verify each step uses the previous output as the next prior.</li><li>Confirm the model never resets to P(L0) between observations.</li></ol></article>
        <article><h3>Test 6 · Synthetic isolation</h3><ol><li>Select a SIM student.</li><li>Confirm evidence is marked SYNTHETIC.</li><li>Synthetic responses must not be presented as real research or calibration evidence.</li></ol></article>
      </div>
    </details>
  );
}

export default function AdminBktVerificationPage({ refreshKey = 0, modelVersion }: { refreshKey?: number; modelVersion?: string }) {
  const [data, setData] = useState<BktVerificationBootstrap | null>(null);
  const [traceData, setTraceData] = useState<BktVerificationTraceResponse | null>(null);
  const [studentId, setStudentId] = useState("");
  const [studentQuery, setStudentQuery] = useState("");
  const [wordId, setWordId] = useState("");
  const [wordQuery, setWordQuery] = useState("");
  const [error, setError] = useState("");
  const [traceLoading, setTraceLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (modelVersion ? getBktVerificationBootstrap(modelVersion) : getBktVerificationBootstrap())
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setTraceData(null);
        setStudentId(result.students[0]?.studentId ?? "");
      })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load BKT verification metadata."); });
    return () => { cancelled = true; };
  }, [refreshKey, modelVersion]);

  useEffect(() => {
    if (!studentId) {
      setTraceData(null);
      return undefined;
    }
    let cancelled = false;
    setTraceLoading(true);
    void (modelVersion ? getBktVerificationTrace(studentId, wordId || undefined, modelVersion) : getBktVerificationTrace(studentId, wordId || undefined))
      .then((result) => {
        if (cancelled) return;
        setError("");
        setTraceData(result);
        if (result.selectedWordId && result.selectedWordId !== wordId) setWordId(result.selectedWordId);
      })
      .catch((reason) => { if (!cancelled) { setTraceData(null); setError(reason instanceof Error ? reason.message : "Could not load the BKT trace."); } })
      .finally(() => { if (!cancelled) setTraceLoading(false); });
    return () => { cancelled = true; };
  }, [studentId, wordId, refreshKey, modelVersion]);

  const testStudents = useMemo(() => (data?.students ?? []).filter((student) => student.isTestAccount), [data]);
  const liveStatus = traceData?.trace?.verification ?? "NOT TESTED";
  const dataSource = traceData?.trace?.syntheticTestData ? "SYNTHETIC" : traceData?.trace?.provenance ?? "NOT TESTED";

  const selectStudent = (value: string) => {
    setStudentId(value);
    setStudentQuery("");
    setWordId("");
    setWordQuery("");
    setTraceData(null);
    setError("");
  };

  const selectWord = (value: string) => {
    setWordId(value);
    setError("");
  };

  if (error && !data) return <section className="bkt-verification bkt-verification-state"><p className="admin-error" role="alert">{error}</p><p>Refresh the page to retry the read-only verification service.</p></section>;
  if (!data) return <section className="bkt-verification bkt-verification-state"><p>Loading BKT verification metadata…</p></section>;

  return (
    <section className="bkt-verification" aria-label="BKT Verification">
      <div className="bkt-verification-intro">
        <div><span className="admin-eyebrow">Research / Learning Engine</span><h2>BKT Verification</h2><p>Use known test cases to compare expected BKT behavior with the current system.</p><p className="bkt-verification-read-only">This page is read-only. It does not modify student responses, BKT parameters, SM-2 schedules, or research data.</p></div>
        <div className="bkt-verification-health" aria-label="BKT verification health summary"><div><span>Golden checks</span><strong>{data.golden.summary.passed} / {data.golden.summary.total} PASS</strong></div><div><span>Live selected trace</span><StatusBadge status={liveStatus} /></div><div><span>Model</span><code>{data.model.version}</code></div><div><span>Data source</span><strong>{dataSource}</strong></div></div>
      </div>
      {data.model.contractStatus !== "MATCH" && <div className="bkt-verification-contract-warning" role="alert"><strong>{modelVersion ? "CANDIDATE PREVIEW" : "MODEL CONTRACT CHANGED"}</strong><span>{modelVersion ? "The selected candidate has fitted parameters. Golden checks retain their fixed engineering defaults; live traces below use the selected candidate." : "The current runtime model or parameter fingerprint differs from the versioned golden fixture. Expected values were not rewritten."}</span></div>}
      <section className="bkt-verification-model" aria-labelledby="bkt-model-title"><div><span className="admin-eyebrow">{modelVersion ? "Candidate preview" : "Runtime contract"}</span><h3 id="bkt-model-title">{modelVersion ? "Selected candidate and parameters" : "Current model and parameters"}</h3><p>{modelVersion ? "Read from the stored candidate for this preview." : "Read from the backend configuration used by production BKT replay."}</p></div><div className="bkt-verification-model-meta"><div><span>Model version</span><code>{modelVersion ?? data.model.version}</code></div><div><span>Parameter fingerprint</span><code>{data.model.parameterFingerprint}</code></div></div><ParameterList data={data.model} /></section>
      <GoldenSection checks={data.golden.checks} summary={data.golden.summary} contractStatus={data.golden.contractStatus} />
      <section className="bkt-verification-section bkt-verification-live-section" aria-label="Live student trace controls">
        {testStudents.length > 0 && <div className="bkt-verification-test-students"><span>Recommended test students</span>{testStudents.map((student) => <button type="button" key={student.studentId} className="bkt-verification-link-button" onClick={() => selectStudent(student.studentId)}>{student.studentId}</button>)}</div>}
        <LiveSection students={data.students} selectedStudentId={studentId} selectedWordId={wordId} studentQuery={studentQuery} wordQuery={wordQuery} traceData={traceData} onStudentChange={selectStudent} onStudentQueryChange={setStudentQuery} onWordChange={selectWord} onWordQueryChange={setWordQuery} onPreset={selectWord} />
      </section>
      {traceLoading && <p className="bkt-verification-loading" role="status">Loading the selected trace…</p>}
      {error && <p className="admin-error" role="alert">{error}</p>}
      <HowToTest model={data.model} liveTrace={traceData?.trace ?? null} />
    </section>
  );
}
