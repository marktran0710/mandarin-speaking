import { useMemo } from "react";
import DashboardStat from "./DashboardStat";
import { summarizeMeasurements, type MeasurementEvent } from "../utils/measurement";
import { calibrateItems, type IrtItem, type IrtResponse } from "../utils/irt";
import type { AudioRecord } from "../pages/MyStoriesPage";
import "./MeasurementAnalyticsPanel.css";

export default function MeasurementAnalyticsPanel({
  records,
  events = [],
}: {
  records: AudioRecord[];
  events?: MeasurementEvent[];
}) {
  const summary = useMemo(() => summarizeMeasurements(records), [records]);
  const eventCounts = useMemo(() => {
    const counts = new Map<string, number>();
    events.forEach((event) => counts.set(event.name, (counts.get(event.name) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [events]);
  const calibration = useMemo(() => {
    const items: IrtItem[] = records
      .map((record) => record.praatMetrics?.irt_item as IrtItem | undefined)
      .filter((item): item is IrtItem => Boolean(item?.itemId));
    const responses: IrtResponse[] = records
      .map((record) => {
        const item = record.praatMetrics?.irt_item as IrtItem | undefined;
        const passed = record.praatMetrics?.pronunciation_mastery?.passed;
        return item?.itemId && typeof passed === "boolean"
          ? { studentId: record.studentId ?? "anonymous", itemId: item.itemId, correct: passed }
          : null;
      })
      .filter((response): response is IrtResponse => response !== null);
    return calibrateItems([...new Map(items.map((item) => [item.itemId, item])).values()], responses);
  }, [records]);
  const irtStudents = useMemo(() => new Set(records.map((record) => record.studentId).filter(Boolean)).size, [records]);
  const calibrationSummary = useMemo(() => ({
    insufficient: calibration.filter((item) => item.n < 30).length,
    warning: calibration.filter((item) => item.n >= 30 && item.flags.length > 0).length,
    pass: calibration.filter((item) => item.usable).length,
  }), [calibration]);

  return (
    <div className="measurement-dashboard" aria-label="Learning measurement dashboard">
      <section className="teacher-stat-grid" aria-label="Measurement overview">
        <DashboardStat label="Analyzed attempts" value={String(summary.analyzed)} note={`${summary.attempts} total attempts`} />
        <DashboardStat label="Mastery pass rate" value={summary.passRate === null ? "--" : `${summary.passRate}%`} note="Only judged attempts" />
        <DashboardStat label="Avg. tone accuracy" value={summary.averageTone === null ? "--" : `${summary.averageTone}`} note="Backend pronunciation metric" />
        <DashboardStat label="Not enough evidence" value={summary.notEnoughEvidenceRate === null ? "--" : `${summary.notEnoughEvidenceRate}%`} note="Needs audio-quality review" />
      </section>

      <section className="teacher-panel measurement-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Instrumented learning data</p>
            <h2>Measurement health</h2>
          </div>
          <span className="queue-count">{irtStudents} students</span>
        </div>
        <p className="measurement-panel-intro">Separate learning outcomes from ASR/audio failures before making a teaching decision.</p>
        {eventCounts.length === 0 ? (
          <p className="teacher-empty-panel">No client events recorded yet. Student practice events will appear here.</p>
        ) : (
          <div className="measurement-event-list">
            {eventCounts.map(([name, count]) => <span key={name}><strong>{count}</strong> {name.split("_").join(" ")}</span>)}
          </div>
        )}
      </section>

      <section className="teacher-panel measurement-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Question calibration</p>
            <h2>IRT readiness</h2>
          </div>
        </div>
        {calibration.length > 0 && (
          <div className="irt-summary-grid" aria-label="IRT readiness summary">
            <div><strong>{calibration.length}</strong><span>Items</span></div>
            <div><strong>{calibration.reduce((sum, item) => sum + item.n, 0)}</strong><span>Responses</span></div>
            <div><strong>{calibrationSummary.pass}</strong><span>Pass</span></div>
            <div><strong>{calibrationSummary.insufficient}</strong><span>Insufficient data</span></div>
          </div>
        )}
        {calibration.length === 0 ? (
          <p className="teacher-empty-panel">No item-linked responses yet. Add an itemId to practice records to begin calibration.</p>
        ) : (
          <table className="measurement-table irt-table">
            <thead><tr><th>Item</th><th>Responses</th><th>Difficulty</th><th>Correct</th><th>Status</th></tr></thead>
            <tbody>{calibration.map((item) => {
              const status = item.n < 30 ? "insufficient_data" : item.usable ? "pass" : "warning";
              return <tr key={item.itemId}><td>{item.itemId}</td><td>{item.n}</td><td>{item.difficulty}</td><td>{Math.round(item.proportionCorrect * 100)}%</td><td><span className={`irt-status is-${status}`}>{status === "insufficient_data" ? "Insufficient data" : status === "pass" ? "Pass" : item.flags.join(", ")}</span></td></tr>;
            })}</tbody>
          </table>
        )}
      </section>
    </div>
  );
}
