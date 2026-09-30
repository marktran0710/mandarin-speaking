import { useEffect, useMemo, useRef } from "react";
import Chart from "chart.js/auto";
import type { ChartConfiguration, TooltipItem } from "chart.js";
import { ROUND_DEFINITIONS, type RoundScoreRow } from "./model";

const SERIES_COLORS = [
  { fill: "rgba(39, 105, 148, 0.78)", border: "#276994" },
  { fill: "rgba(20, 139, 111, 0.78)", border: "#148b6f" },
  { fill: "rgba(205, 139, 29, 0.82)", border: "#a96c0b" },
] as const;

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
  const round = ROUND_DEFINITIONS[datasetIndex];
  if (!round) return "";
  const cell = rows[dataIndex]?.rounds[round.mode];
  if (!cell) return `${round.label}: Not completed`;
  return `${round.label}: ${cell.score}% · ${cell.correctCount}/${cell.totalQuestions} · ${formatCompletedAt(cell.completedAt)}`;
}

export function createRoundScoresChartConfig(
  rows: RoundScoreRow[],
  reduceMotion = false,
): ChartConfiguration<"bar", Array<number | null>, string> {
  return {
    type: "bar",
    data: {
      labels: rows.map((row) => row.studentName),
      datasets: ROUND_DEFINITIONS.map((round, index) => ({
        label: round.label,
        data: rows.map((row) => row.rounds[round.mode]?.score ?? null),
        backgroundColor: SERIES_COLORS[index].fill,
        borderColor: SERIES_COLORS[index].border,
        borderWidth: 1,
        borderRadius: 4,
        borderSkipped: false,
        maxBarThickness: 22,
        categoryPercentage: 0.78,
        barPercentage: 0.86,
      })),
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
            label: (item: TooltipItem<"bar">) => {
              return formatRoundScoreTooltip(rows, item.datasetIndex, item.dataIndex);
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          min: 0,
          max: 100,
          title: { display: true, text: "Quiz accuracy" },
          ticks: { callback: (value) => `${value}%` },
          grid: { color: "rgba(111, 98, 72, 0.13)" },
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
  const chartRef = useRef<Chart<"bar", Array<number | null>, string> | null>(null);
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
      </ul>
      <div className="round-scores-chart-scroll" tabIndex={0} aria-label="Scrollable round scores chart">
        <div className="round-scores-chart-canvas" style={{ minWidth: chartMinWidth }}>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Vertical grouped column chart comparing ${rows.length} students across the three quiz rounds.`}
          />
        </div>
      </div>
    </div>
  );
}
