import type { AudioRecord } from "../pages/MyStoriesPage";
import DashboardStat from "./DashboardStat";
import { FluencyToneTimeChart } from "./MyStoriesCharts";

/** Class-wide speaking trend under the recording list. It answers one
 * question — is the class getting better? — so it shows one line chart and
 * the two numbers that line plots. The date/topic/version filters and the
 * four other charts were cut: teachers never used them, and the version
 * switch exposed research plumbing (experimental V2 results now live in the
 * admin console only). Recordings are always read at stable_v1 here. */
export default function RecordingAnalyticsPanel({ records }: { records: AudioRecord[] }) {
  if (records.length === 0) {
    return (
      <section className="teacher-panel teacher-recording-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Speaking trend</p>
            <h2>Recording Analytics</h2>
          </div>
        </div>
        <div className="teacher-empty-panel">
          <strong>No recordings yet</strong>
          <p>Fluency and tone accuracy trends will appear here once students submit recordings.</p>
        </div>
      </section>
    );
  }

  const stable = records.filter(
    (record) => (record.praatMetrics?.analysis_version ?? "stable_v1") === "stable_v1",
  );
  const withMetrics = stable.filter((record) => record.praatMetrics);

  const average = (values: number[]) =>
    values.length > 0 ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length) : null;
  const avgFluency = average(withMetrics.map((record) => record.praatMetrics.fluency_score || 0));
  const avgTone = average(withMetrics.map((record) => record.praatMetrics.tone_accuracy || 0));

  const byDay = new Map<string, { fluency: number[]; tone: number[] }>();
  withMetrics
    .map((record) => ({
      time: new Date(record.timestamp).getTime(),
      fluency: record.praatMetrics.fluency_score,
      tone: record.praatMetrics.tone_accuracy,
    }))
    .filter((point) => !Number.isNaN(point.time))
    .sort((a, b) => a.time - b.time)
    .forEach((point) => {
      const day = new Date(point.time).toLocaleDateString();
      const entry = byDay.get(day) || { fluency: [], tone: [] };
      entry.fluency.push(point.fluency || 0);
      entry.tone.push(point.tone || 0);
      byDay.set(day, entry);
    });
  const timeSeries = Array.from(byDay.entries()).map(([day, value]) => ({
    label: day,
    fluency: Math.round(value.fluency.reduce((sum, x) => sum + x, 0) / value.fluency.length),
    tone: Math.round(value.tone.reduce((sum, x) => sum + x, 0) / value.tone.length),
  }));

  return (
    <>
      <section className="teacher-stat-grid" aria-label="Recording analytics overview">
        <DashboardStat
          label="Avg. fluency"
          value={avgFluency === null ? "--" : `${avgFluency}/100`}
          note="Praat fluency score"
        />
        <DashboardStat
          label="Avg. tone accuracy"
          value={avgTone === null ? "--" : `${avgTone}%`}
          note="Praat tone accuracy"
        />
      </section>

      <section className="teacher-panel teacher-recording-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Speaking trend</p>
            <h2>Fluency &amp; tone accuracy over time</h2>
          </div>
        </div>
        {timeSeries.length === 0 ? (
          <p className="quiz-analytics-empty-note">No analyzed recordings yet.</p>
        ) : (
          <FluencyToneTimeChart points={timeSeries} />
        )}
      </section>
    </>
  );
}
