import { useEffect, useMemo, useRef } from "react";
import Chart from "chart.js/auto";
import type { ChartConfiguration, TooltipItem } from "chart.js";
import { ROUND_DEFINITIONS, summarizeResponseTime, type RoundScoreRow } from "./model";

const SERIES_COLORS = [
  { fill: "rgba(39, 105, 148, 0.78)", border: "#276994" },
  { fill: "rgba(20, 139, 111, 0.78)", border: "#148b6f" },
  { fill: "rgba(205, 139, 29, 0.82)", border: "#a96c0b" },
] as const;
const RESPONSE_TIME_COLOR = "#3f3528";
const RESPONSE_TIME_LABEL = "Avg response time / question";
type RoundScoresChartType = "bar" | "line";

const completedAtFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatCompletedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : completedAtFormatter.format(date);
}

function compactStudentLabel(value: unknown): string {
  const label = String(value ?? "");
  return label.length > 11 ? `${label.slice(0, 10)}…` : label;
}

export function formatRoundScoreTooltip(rows: RoundScoreRow[], datasetIndex: number, dataIndex: number): string {
  if (datasetIndex === ROUND_DEFINITIONS.length) {
    const responseTime = rows[dataIndex] ? summarizeResponseTime(rows[dataIndex]) : null;
    if (!responseTime || responseTime.secondsPerQuestion === null) return `${RESPONSE_TIME_LABEL}: Not available`;
    return `${RESPONSE_TIME_LABEL}: ${responseTime.secondsPerQuestion}s · ${responseTime.totalQuestions} questions · ${responseTime.completedRounds} rounds`;
  }
  const round = ROUND_DEFINITIONS[datasetIndex];
  if (!round) return "";
  const cell = rows[dataIndex]?.rounds[round.mode];
  if (!cell) return `${round.label}: Not completed`;
  const secondsPerQuestion = cell.totalTimeMs === null
    ? "time unavailable"
    : `${Math.round((cell.totalTimeMs / cell.totalQuestions / 1000) * 10) / 10}s/question`;
  return `${round.label}: ${cell.score}% · ${cell.correctCount}/${cell.totalQuestions} · ${secondsPerQuestion} · ${formatCompletedAt(cell.completedAt)}`;
}

export function createRoundScoresChartConfig(
  rows: RoundScoreRow[],
  reduceMotion = false,
): ChartConfiguration<RoundScoresChartType, Array<number | null>, string> {
  return {
    type: "bar",
    data: {
      labels: rows.map((row) => row.studentName),
      datasets: [
        ...ROUND_DEFINITIONS.map((round, index) => ({
          type: "bar" as const,
          label: round.label,
          data: rows.map((row) => row.rounds[round.mode]?.score ?? null),
          yAxisID: "score",
          backgroundColor: SERIES_COLORS[index].fill,
          borderColor: SERIES_COLORS[index].border,
          borderWidth: 1,
          borderRadius: 4,
          borderSkipped: false as const,
          maxBarThickness: 22,
          categoryPercentage: 0.78,
          barPercentage: 0.86,
          order: 2,
        })),
        {
          type: "line" as const,
          label: RESPONSE_TIME_LABEL,
          data: rows.map((row) => summarizeResponseTime(row).secondsPerQuestion),
          yAxisID: "responseTime",
          borderColor: RESPONSE_TIME_COLOR,
          backgroundColor: RESPONSE_TIME_COLOR,
          borderWidth: 2.5,
          borderDash: [7, 5],
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: "#fffaf0",
          pointBorderColor: RESPONSE_TIME_COLOR,
          pointBorderWidth: 2,
          tension: 0.25,
          spanGaps: false,
          order: 1,
        },
      ],
    },
    options: {
      indexAxis: "x",
      responsive: true,
      maintainAspectRatio: false,
      animation: reduceMotion ? false : { duration: 260 },
      interaction: { mode: "nearest", axis: "x", intersect: true },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => {
              const row = rows[items[0]?.dataIndex ?? -1];
              return row ? `${row.studentName} · ${row.studentId}` : "";
            },
            label: (item: TooltipItem<RoundScoresChartType>) => {
              return formatRoundScoreTooltip(rows, item.datasetIndex, item.dataIndex);
            },
          },
        },
      },
      scales: {
        score: {
          axis: "y",
          position: "left",
          beginAtZero: true,
          min: 0,
          max: 100,
          title: { display: true, text: "Quiz accuracy" },
          ticks: { callback: (value) => `${value}%` },
          grid: { color: "rgba(111, 98, 72, 0.13)" },
        },
        responseTime: {
          axis: "y",
          position: "right",
          beginAtZero: true,
          min: 0,
          title: { display: true, text: "Avg response time / question (seconds)" },
          ticks: { callback: (value) => `${value}s` },
          grid: { drawOnChartArea: false },
        },
        x: {
          grid: { display: false },
          ticks: {
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0,
            callback: function (_value, index) {
              return compactStudentLabel(this.getLabelForValue(index));
            },
          },
        },
      },
    },
  };
}

export default function RoundScoresChart({ rows }: { rows: RoundScoreRow[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart<RoundScoresChartType, Array<number | null>, string> | null>(null);
  const reduceMotion = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  const config = useMemo(() => createRoundScoresChartConfig(rows, reduceMotion), [reduceMotion, rows]);
  const chartMinWidth = Math.max(320, rows.length * 70);

  useEffect(() => {
    const context = canvasRef.current?.getContext("2d");
    if (!context) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(context, config);
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [config]);

  return (
    <div className="round-scores-chart">
      <ul className="round-scores-legend" aria-label="Round score series">
        {ROUND_DEFINITIONS.map((round, index) => (
          <li key={round.mode}>
            <span style={{ backgroundColor: SERIES_COLORS[index].border }} aria-hidden="true" />
            {round.label}
          </li>
        ))}
        <li>
          <span className="round-scores-legend-line" aria-hidden="true" />
          {RESPONSE_TIME_LABEL}
        </li>
      </ul>
      <div className="round-scores-chart-scroll" tabIndex={0} aria-label="Scrollable round scores chart">
        <div className="round-scores-chart-canvas" style={{ minWidth: chartMinWidth }}>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Combo chart comparing three round scores and average response time for ${rows.length} students.`}
          />
        </div>
      </div>
    </div>
  );
}
