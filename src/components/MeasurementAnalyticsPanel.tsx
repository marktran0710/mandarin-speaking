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
          <span className="queue-count">v1</span>
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
        {calibration.length === 0 ? (
          <p className="teacher-empty-panel">No item-linked responses yet. Add an itemId to practice records to begin calibration.</p>
        ) : (
          <table className="measurement-table">
            <thead><tr><th>Item</th><th>Responses</th><th>Difficulty</th><th>Status</th></tr></thead>
            <tbody>{calibration.map((item) => <tr key={item.itemId}><td>{item.itemId}</td><td>{item.n}</td><td>{item.difficulty}</td><td>{item.usable ? "Calibrated" : item.flags.join(", ")}</td></tr>)}</tbody>
          </table>
        )}
      </section>
    </div>
  );
}
