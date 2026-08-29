import { useEffect, useMemo, useRef } from "react";
import Chart from "chart.js/auto";

// ── Shared Chart.js look for the teacher analytics views ───────────────────
// A plainer, more neutral "data dashboard" register than the rest of the
// app's playful student-facing style: the app's own sans stack instead of
// the display/heading font, restrained gridlines, and a flat (non-bold)
// tick weight. Set once so every chart on Students and Recordings inherits
// it without repeating options per chart.
const CHART_FONT_FAMILY =
  '"Inter", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif';
Chart.defaults.font.family = CHART_FONT_FAMILY;
Chart.defaults.font.size = 12;
// The next three are resolved hex values for --clay-muted, --clay-hairline,
// and --clay-ink (Chart.js can't read CSS custom properties) — keep in sync
// with src/index.css.
Chart.defaults.color = "#6f6248";
Chart.defaults.borderColor = "#f0e3c4";
Chart.defaults.plugins.tooltip.backgroundColor = "#2a2318";
Chart.defaults.plugins.tooltip.titleFont = { family: CHART_FONT_FAMILY, weight: "bold" };
Chart.defaults.plugins.tooltip.bodyFont = { family: CHART_FONT_FAMILY };
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 6;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.legend.labels.boxHeight = 8;

/** Chart.js canvas that (re)builds its chart whenever `build` changes,
 * tearing down the previous instance first — same lifecycle as
 * components/PitchChart.tsx. */
export function QuizChartCanvas({
  build,
  height = 220,
  ariaLabel,
}: {
  build: (ctx: CanvasRenderingContext2D) => Chart;
  height?: number;
  /** Text alternative for screen readers — Chart.js renders to <canvas>,
   * which has no accessible content of its own. */
  ariaLabel?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    chartRef.current?.destroy();
    chartRef.current = build(ctx);
    return () => chartRef.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [build]);

  return (
    <div
      className="quiz-analytics-chart-canvas"
      style={{ height }}
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
    >
      <canvas ref={canvasRef} />
    </div>
  );
}

export function AccuracyTimeChart({ points }: { points: Array<{ label: string; value: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "line",
        data: {
          labels: points.map((p) => p.label),
          datasets: [{
            label: "Accuracy",
            data: points.map((p) => p.value),
            borderColor: "#e9a825",
            backgroundColor: "rgba(124, 58, 237, 0.14)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 6,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: (item) => `${item.parsed.y}% accuracy` } },
          },
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              title: { display: true, text: "Accuracy" },
              ticks: { callback: (v) => `${v}%` },
            },
            x: { grid: { display: false } },
          },
        },
      }),
    [points],
  );
  return <QuizChartCanvas build={build} ariaLabel="Line chart: quiz accuracy over time" />;
}

export function FluencyToneTimeChart({ points }: { points: Array<{ label: string; fluency: number; tone: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "line",
        data: {
          labels: points.map((p) => p.label),
          datasets: [
            {
              label: "Fluency",
              data: points.map((p) => p.fluency),
              borderColor: "#e9a825",
              backgroundColor: "rgba(124, 58, 237, 0.1)",
              borderWidth: 2,
              tension: 0.3,
              pointRadius: 4,
              pointHoverRadius: 6,
            },
            {
              label: "Tone accuracy",
              data: points.map((p) => p.tone),
              borderColor: "#1c9a5b",
              backgroundColor: "rgba(28, 154, 91, 0.1)",
              borderWidth: 2,
              tension: 0.3,
              pointRadius: 4,
              pointHoverRadius: 6,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: true, position: "top", align: "end" } },
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              title: { display: true, text: "Score" },
              ticks: { callback: (v) => `${v}` },
            },
            x: { grid: { display: false } },
          },
        },
      }),
    [points],
  );
  return <QuizChartCanvas build={build} ariaLabel="Line chart: fluency and tone scores over time" />;
}
