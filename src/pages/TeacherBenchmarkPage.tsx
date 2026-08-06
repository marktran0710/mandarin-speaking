import { useCallback, useEffect, useRef, useState } from "react";
import { getBackendUrl } from "../utils/storyRecorderFeedback";
import "./TeacherBenchmarkPage.css";

type JsonObject = Record<string, any>;

const POLL_INTERVAL_MS = 1000;

interface BenchmarkStatus {
  corpus: { downloaded: boolean; wav_count: number; citation: string };
  job: {
    phase: string;
    running: boolean;
    done: number;
    total: number;
    message: string;
    error: string | null;
    downloaded_bytes: number;
    download_total_bytes: number;
    elapsed_seconds: number | null;
    failed: number;
  };
  scored_count: number;
  has_results: boolean;
  production_threshold: number;
}

function percentage(value: unknown, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(digits)}%`
    : "—";
}

function decimal(value: unknown, digits = 3) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "—";
}

function megabytes(bytes: number) {
  return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
}

/** Bars are drawn from kappa, which runs -1..1; clamp to the drawable range. */
function kappaWidth(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value)) * 100;
}

function MetricCard({
  label, value, hint,
}: { label: string; value: string; hint?: string }) {
  return (
    <article className="tbench-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </article>
  );
}

/** Scatter of system score against mean teacher rating, drawn as inline SVG.
 * A chart earns its place here: it shows whether a correlation is a real
 * relationship or the product of a few outliers, which a single number hides. */
function CorrelationNote({ label, data }: { label: string; data: JsonObject }) {
  return (
    <div className="tbench-corr">
      <span>{label}</span>
      <strong>{decimal(data?.spearman_correlation)}</strong>
      <small>Spearman · n={data?.n ?? 0}</small>
    </div>
  );
}

export default function TeacherBenchmarkPage() {
  const [status, setStatus] = useState<BenchmarkStatus | null>(null);
  const [report, setReport] = useState<JsonObject | null>(null);
  const [threshold, setThreshold] = useState(58);
  const [error, setError] = useState("");
  const [loadingReport, setLoadingReport] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${getBackendUrl()}/api/benchmark/ompal/status`);
      if (!response.ok) throw new Error("Could not read benchmark status.");
      setStatus(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the backend.");
    }
  }, []);

  const fetchReport = useCallback(async (nextThreshold: number) => {
    setLoadingReport(true);
    try {
      const response = await fetch(
        `${getBackendUrl()}/api/benchmark/ompal/report?threshold=${nextThreshold}`,
      );
      if (response.status === 404) {
        setReport(null);
        return;
      }
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Could not build the report.");
      }
      setReport(await response.json());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build the report.");
    } finally {
      setLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  // Poll only while a job is in flight. Polling rather than a long-lived
  // stream is deliberate: this run takes minutes and the teacher is expected
  // to close the tab and come back to it.
  useEffect(() => {
    const running = status?.job.running;
    if (!running) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    pollRef.current = setInterval(() => void fetchStatus(), POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [status?.job.running, fetchStatus]);

  const justFinished = status?.job.phase === "complete";
  useEffect(() => {
    if (justFinished || status?.has_results) void fetchReport(threshold);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [justFinished, status?.has_results]);

  const startRun = async () => {
    setError("");
    try {
      const response = await fetch(`${getBackendUrl()}/api/benchmark/ompal/run`, {
        method: "POST",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Could not start the benchmark.");
      }
      await fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the benchmark.");
    }
  };

  const cancelRun = async () => {
    await fetch(`${getBackendUrl()}/api/benchmark/ompal/cancel`, { method: "POST" });
    await fetchStatus();
  };

  const job = status?.job;
  const verdict = report?.verdict as JsonObject | undefined;
  const overall = report?.pass_fail_agreement as JsonObject | undefined;
  const ceiling = report?.human_ceiling as JsonObject | undefined;
  const protocol = report?.benchmark_protocol as JsonObject | undefined;
  const gate = report?.release_gate as JsonObject | undefined;
  const exclusions = (report?.exclusions ?? {}) as JsonObject;

  return (
    <section className="tbench" aria-label="External benchmark">
      <header className="tbench-head">
        <div>
          <p className="tdash-view-kicker">External validation</p>
          <h2>Compare our scores against expert teacher ratings</h2>
          <p>
            Scores the OMPAL corpus with the same analyzer students use, then
            measures how well it agrees with the expert panel — and how well
            those experts agree with each other.
          </p>
        </div>
      </header>

      {error && <p className="tbench-error" role="alert">{error}</p>}

      {status && !status.corpus.downloaded && !job?.running && (
        <section className="tbench-setup">
          <h3>Corpus not downloaded yet</h3>
          <p>{status.corpus.citation}</p>
          <p className="tbench-muted">
            Downloads ~330 MB of audio and expert ratings, then scores 1,850
            utterances. Expect several minutes; you can close this tab and come
            back.
          </p>
          <button type="button" className="tbench-primary" onClick={startRun}>
            Download corpus &amp; run benchmark
          </button>
        </section>
      )}

      {job?.running && (
        <section className="tbench-progress" aria-live="polite">
          <div className="tbench-progress-head">
            <strong>{job.message || "Working…"}</strong>
            <button type="button" className="tbench-cancel" onClick={cancelRun}>
              Cancel
            </button>
          </div>
          {job.phase === "downloading" && (
            <>
              {/* GitHub serves the zipball chunked with no content-length, so
                  the total is often unknown. Show an indeterminate bar and the
                  bytes received rather than a bar implying a known fraction. */}
              {job.download_total_bytes > 0 ? (
                <progress value={job.downloaded_bytes} max={job.download_total_bytes} />
              ) : (
                <progress />
              )}
              <small>
                {megabytes(job.downloaded_bytes)}
                {job.download_total_bytes > 0
                  ? ` of ${megabytes(job.download_total_bytes)}`
                  : " downloaded (total size not reported by the server)"}
              </small>
            </>
          )}
          {job.phase === "scoring" && (
            <>
              <progress value={job.done} max={Math.max(job.total, 1)} />
              <small>
                {job.done} / {job.total} utterances
                {job.failed > 0 && ` · ${job.failed} unscorable`}
                {job.elapsed_seconds !== null && ` · ${job.elapsed_seconds}s elapsed`}
              </small>
            </>
          )}
        </section>
      )}

      {job && !job.running && job.phase !== "idle" && (
        <p className={`tbench-jobnote is-${job.phase}`}>
          {job.error || job.message}
          {status?.corpus.downloaded && (
            <button type="button" className="tbench-secondary" onClick={startRun}>
              {status.has_results ? "Resume / re-run" : "Run benchmark"}
            </button>
          )}
        </p>
      )}

      {report && verdict && (
        <>
          <section className={`tbench-verdict is-${verdict.level}`}>
            <p className="tbench-verdict-kicker">Verdict</p>
            <h3>{verdict.summary}</h3>
            <div className="tbench-verdict-bars">
              <div>
                <span>Our system vs one teacher</span>
                <div className="tbench-bar">
                  <i style={{ width: `${kappaWidth(verdict.system_kappa)}%` }} />
                </div>
                <strong>κ {decimal(verdict.system_kappa)}</strong>
              </div>
              <div>
                <span>Target</span>
                <div className="tbench-bar is-target">
                  <i style={{ width: `${kappaWidth(verdict.target)}%` }} />
                </div>
                <strong>κ {decimal(verdict.target)}</strong>
              </div>
              <div>
                <span>Teachers vs each other</span>
                <div className="tbench-bar is-ceiling">
                  <i style={{ width: `${kappaWidth(verdict.human_ceiling_kappa)}%` }} />
                </div>
                <strong>κ {decimal(verdict.human_ceiling_kappa)}</strong>
              </div>
              <div>
                <span>Best a perfect system could do</span>
                <div className="tbench-bar is-oracle">
                  <i style={{ width: `${kappaWidth(verdict.attainable_max_high)}%` }} />
                </div>
                <strong>
                  κ {decimal(verdict.attainable_max_low, 2)}–{decimal(verdict.attainable_max_high, 2)}
                </strong>
              </div>
            </div>
            {/* Per-rater spread matters: the headline is their mean, and a wide
                spread means the system suits some teachers far better than others. */}
            {report.per_rater_agreement?.per_rater?.length > 0 && (
              <p className="tbench-muted tbench-perrater">
                Per rater:{" "}
                {(report.per_rater_agreement.per_rater as JsonObject[])
                  .map((r) => `rater ${r.rater} κ ${decimal(r.cohen_kappa)}`)
                  .join(" · ")}
              </p>
            )}
          </section>

          <div className="tbench-metrics">
            <MetricCard
              label="Rated words compared"
              value={String(protocol?.rated_word_count ?? 0)}
              hint={`${protocol?.recording_count ?? 0} utterances · ${protocol?.speaker_count ?? 0} speakers`}
            />
            <MetricCard
              label="Raw agreement"
              value={percentage(overall?.accuracy)}
              hint="Gameable — a pass-everything scorer scores ~87%"
            />
            <MetricCard
              label="κ vs majority"
              value={decimal(overall?.cohen_kappa)}
              hint="Context only — easier target than one rater"
            />
            <MetricCard
              label="Rater unanimity"
              value={percentage(ceiling?.unanimous_rate)}
              hint={`${ceiling?.rater_count ?? 0} raters · Fleiss κ ${decimal(ceiling?.fleiss_kappa)}`}
            />
          </div>

          <section className="tbench-panel">
            <h3>Pass threshold</h3>
            <div className="tbench-threshold">
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={threshold}
                aria-label="Pass threshold"
                onChange={(event) => setThreshold(Number(event.target.value))}
                onMouseUp={() => void fetchReport(threshold)}
                onTouchEnd={() => void fetchReport(threshold)}
                onKeyUp={() => void fetchReport(threshold)}
              />
              <output>{threshold}</output>
              {threshold !== status?.production_threshold && (
                <button
                  type="button"
                  className="tbench-secondary"
                  onClick={() => {
                    setThreshold(status?.production_threshold ?? 58);
                    void fetchReport(status?.production_threshold ?? 58);
                  }}
                >
                  Reset to shipped ({status?.production_threshold})
                </button>
              )}
            </div>
            <p className="tbench-warn">{protocol?.threshold_warning}</p>
            {loadingReport && <small className="tbench-muted">Recomputing…</small>}
          </section>

          <section className="tbench-panel">
            <h3>Agreement by expected tone</h3>
            <table className="tbench-table">
              <thead>
                <tr><th>Tone</th><th>n</th><th>Agreement</th><th>F1</th><th>κ</th></tr>
              </thead>
              <tbody>
                {["1", "2", "3", "4"].map((tone) => {
                  const row = (report.by_expected_tone as JsonObject)?.[tone] ?? {};
                  return (
                    <tr key={tone}>
                      <td>Tone {tone}</td>
                      <td>{row.n ?? 0}</td>
                      <td>{percentage(row.accuracy)}</td>
                      <td>{percentage(row.f1)}</td>
                      <td>{decimal(row.cohen_kappa)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          <div className="tbench-split">
            <section className="tbench-panel">
              <h3>By population</h3>
              <table className="tbench-table">
                <thead><tr><th>Group</th><th>n</th><th>Agreement</th><th>κ</th></tr></thead>
                <tbody>
                  <tr>
                    <td>Learners</td>
                    <td>{(report.by_population as JsonObject)?.learners?.n ?? 0}</td>
                    <td>{percentage((report.by_population as JsonObject)?.learners?.accuracy)}</td>
                    <td>{decimal((report.by_population as JsonObject)?.learners?.cohen_kappa)}</td>
                  </tr>
                  <tr>
                    <td>Native speakers</td>
                    <td>{(report.by_population as JsonObject)?.natives?.n ?? 0}</td>
                    <td>{percentage((report.by_population as JsonObject)?.natives?.accuracy)}</td>
                    <td>{decimal((report.by_population as JsonObject)?.natives?.cohen_kappa)}</td>
                  </tr>
                </tbody>
              </table>
              <p className="tbench-muted">
                Natives are the sanity check: a scorer that fails them is broken.
              </p>
            </section>

            <section className="tbench-panel">
              <h3>Sentence-level correlation</h3>
              <div className="tbench-corrs">
                <CorrelationNote
                  label="Tone accuracy vs teacher accuracy"
                  data={(report.score_agreement as JsonObject)?.accuracy ?? {}}
                />
                <CorrelationNote
                  label="Fluency vs teacher fluency"
                  data={(report.score_agreement as JsonObject)?.fluency ?? {}}
                />
              </div>
              <p className="tbench-muted">
                {(report.score_agreement as JsonObject)?.note}
              </p>
            </section>
          </div>

          {gate && (
            <section className="tbench-panel">
              <h3>Student-release gate</h3>
              <p className="tbench-muted">{gate.note}</p>
              <table className="tbench-table">
                <thead><tr><th>Criterion</th><th>Actual</th><th>Required</th><th>Result</th></tr></thead>
                <tbody>
                  {(gate.checks as JsonObject[]).map((check) => (
                    <tr key={check.name} data-applicable={check.applicable}>
                      <td>{check.name.replace(/_/g, " ")}</td>
                      <td>{check.applicable ? decimal(check.actual) : "—"}</td>
                      <td>{check.applicable ? `${check.operator} ${check.threshold}` : "—"}</td>
                      <td>
                        {check.applicable
                          ? (check.passed ? "Pass" : "Fail")
                          : "Not applicable"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section className="tbench-panel">
            <h3>Disagreements ({(report.audit as JsonObject)?.disagreement_count ?? 0})</h3>
            <table className="tbench-table">
              <thead>
                <tr><th>Utterance</th><th>Speaker</th><th>Word</th><th>Tone</th><th>System</th><th>Teachers</th></tr>
              </thead>
              <tbody>
                {((report.audit as JsonObject)?.disagreements ?? []).map(
                  (row: JsonObject, index: number) => (
                    <tr key={`${row.utterance_id}-${row.word}-${index}`}>
                      <td>{row.utterance_id}</td>
                      <td>{row.speaker_id}</td>
                      <td lang="zh-Hant">{row.word}</td>
                      <td>{row.expected_tone ?? "—"}</td>
                      <td>{row.system_passed ? "Pass" : "Fail"}</td>
                      <td>{row.teacher_passed ? "Pass" : "Fail"}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
            {(report.audit as JsonObject)?.truncated && (
              <p className="tbench-muted">List truncated.</p>
            )}
          </section>

          <section className="tbench-panel tbench-provenance">
            <h3>What this does and does not show</h3>
            <p>{protocol?.population_caveat}</p>
            <p className="tbench-muted">{protocol?.citation}</p>
            {Object.keys(exclusions).length > 0 && (
              <p className="tbench-muted">
                Excluded:{" "}
                {Object.entries(exclusions)
                  .map(([reason, count]) => `${reason.replace(/_/g, " ")} (${count})`)
                  .join(", ")}
                .
              </p>
            )}
          </section>
        </>
      )}
    </section>
  );
}
