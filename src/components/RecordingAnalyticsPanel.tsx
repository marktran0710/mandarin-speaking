import { useState } from "react";
import type { AudioRecord } from "../pages/MyStoriesPage";
import DashboardStat from "./DashboardStat";
import {
  AI_FEEDBACK_CATEGORIES,
  AiFeedbackCategoryChart,
  FluencyToneScatterChart,
  FluencyToneTimeChart,
  RecordingsPerTopicChart,
} from "./MyStoriesCharts";
import { DATE_RANGE_LABEL, filterByDateRange, getTopicLabel, type DateRangePreset } from "../utils/myStoriesUtils";

const DATE_RANGE_OPTIONS: DateRangePreset[] = ["all", "7d", "30d", "90d"];

/** Class-wide analytics over story-recording feedback (Praat + AI). Unlike
 * Quiz Analytics, recordings have no student-name field today, so this is
 * aggregate-only — a topic filter, not a student one. */
export default function RecordingAnalyticsPanel({ records }: { records: AudioRecord[] }) {
  const [dateRange, setDateRange] = useState<DateRangePreset>("all");
  const [topicFilter, setTopicFilter] = useState("all");

  if (records.length === 0) {
    return (
      <section className="teacher-panel teacher-recording-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Recording feedback analytics</p>
            <h2>Recording Analytics</h2>
          </div>
        </div>
        <div className="teacher-empty-panel">
          <strong>No recordings yet</strong>
          <p>Fluency, tone accuracy, and AI feedback trends will appear here once students submit recordings.</p>
        </div>
      </section>
    );
  }

  const topicIds = Array.from(
    new Set(records.map((r) => r.topicId).filter((id): id is string => Boolean(id))),
  );

  const dateFiltered = filterByDateRange(records, (r) => r.timestamp, dateRange);
  const filtered = topicFilter === "all" ? dateFiltered : dateFiltered.filter((r) => r.topicId === topicFilter);
  const withMetrics = filtered.filter((r) => r.praatMetrics);
  const withAiFeedback = filtered.filter((r) => r.praatMetrics?.ai_feedback);

  const avgFluency = withMetrics.length > 0
    ? Math.round(withMetrics.reduce((sum, r) => sum + (r.praatMetrics.fluency_score || 0), 0) / withMetrics.length)
    : null;
  const avgTone = withMetrics.length > 0
    ? Math.round(withMetrics.reduce((sum, r) => sum + (r.praatMetrics.tone_accuracy || 0), 0) / withMetrics.length)
    : null;

  const categoryData = AI_FEEDBACK_CATEGORIES.map((category) => {
    const scores = withAiFeedback
      .map((r) => r.praatMetrics.ai_feedback[category]?.score)
      .filter((s): s is number => typeof s === "number");
    return {
      category,
      avg: scores.length > 0 ? Math.round(scores.reduce((s, v) => s + v, 0) / scores.length) : 0,
      count: scores.length,
    };
  });
  const allAiScores = categoryData.flatMap((c) => (c.count > 0 ? [c.avg] : []));
  const avgAiScore = allAiScores.length > 0
    ? Math.round(allAiScores.reduce((s, v) => s + v, 0) / allAiScores.length)
    : null;

  const parsedByTime = withMetrics
    .map((r) => ({
      time: new Date(r.timestamp).getTime(),
      fluency: r.praatMetrics.fluency_score,
      tone: r.praatMetrics.tone_accuracy,
    }))
    .filter((r) => !Number.isNaN(r.time))
    .sort((a, b) => a.time - b.time);
  const byDay = new Map<string, { fluency: number[]; tone: number[] }>();
  parsedByTime.forEach((r) => {
    const day = new Date(r.time).toLocaleDateString();
    const entry = byDay.get(day) || { fluency: [], tone: [] };
    entry.fluency.push(r.fluency || 0);
    entry.tone.push(r.tone || 0);
    byDay.set(day, entry);
  });
  const timeSeries = Array.from(byDay.entries()).map(([day, v]) => ({
    label: day,
    fluency: Math.round(v.fluency.reduce((s, x) => s + x, 0) / v.fluency.length),
    tone: Math.round(v.tone.reduce((s, x) => s + x, 0) / v.tone.length),
  }));

  const perTopic = topicIds
    .map((id) => ({ topic: getTopicLabel(id), count: records.filter((r) => r.topicId === id).length }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  // One point per recording — fluency vs. tone accuracy — reveals whether
  // the two skills move together for the same recording, which the
  // per-day-averaged lines above can't show since they average each
  // metric separately rather than pairing them.
  const fluencyTonePoints = withMetrics
    .filter((r) => typeof r.praatMetrics.fluency_score === "number" && typeof r.praatMetrics.tone_accuracy === "number")
    .map((r) => ({ fluency: r.praatMetrics.fluency_score, tone: r.praatMetrics.tone_accuracy }));

  return (
    <>
      <section className="teacher-panel quiz-analytics-filters-panel">
        <div className="quiz-analytics-filters">
          <label>
            Date range
            <select value={dateRange} onChange={(e) => setDateRange(e.target.value as DateRangePreset)}>
              {DATE_RANGE_OPTIONS.map((preset) => (
                <option key={preset} value={preset}>{DATE_RANGE_LABEL[preset]}</option>
              ))}
            </select>
          </label>
          <label>
            Topic
            <select value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)}>
              <option value="all">All topics</option>
              {topicIds.map((id) => (
                <option key={id} value={id}>{getTopicLabel(id)}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {filtered.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No recordings match this filter</strong>
          <p>Try a different topic.</p>
        </div>
      ) : (
        <>
          <section className="teacher-stat-grid" aria-label="Recording analytics overview">
            <DashboardStat
              label="Recordings"
              value={String(filtered.length)}
              note="Total submitted recordings"
            />
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
            <DashboardStat
              label="Avg. AI feedback score"
              value={avgAiScore === null ? "--" : `${avgAiScore}/100`}
              note="Fluency + grammar + vocabulary"
            />
          </section>

          <section className="teacher-panel teacher-recording-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Visualized</p>
                <h2>Charts</h2>
              </div>
            </div>
            <div className="quiz-analytics-charts">
              <div className="quiz-analytics-chart-card quiz-analytics-chart-wide">
                <h3>Fluency &amp; tone accuracy over time</h3>
                {timeSeries.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No analyzed recordings in this filter yet.</p>
                ) : (
                  <FluencyToneTimeChart points={timeSeries} />
                )}
              </div>
              <div className="quiz-analytics-chart-card quiz-analytics-chart-wide">
                <h3>Fluency vs. tone accuracy, per recording</h3>
                {fluencyTonePoints.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No analyzed recordings in this filter yet.</p>
                ) : (
                  <FluencyToneScatterChart points={fluencyTonePoints} />
                )}
              </div>
              <div className="quiz-analytics-chart-card">
                <h3>AI feedback score by category</h3>
                {allAiScores.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No AI feedback in this filter yet.</p>
                ) : (
                  <AiFeedbackCategoryChart data={categoryData} />
                )}
              </div>
              <div className="quiz-analytics-chart-card">
                <h3>Recordings per topic</h3>
                {perTopic.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No topic data yet.</p>
                ) : (
                  <RecordingsPerTopicChart data={perTopic} />
                )}
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}
