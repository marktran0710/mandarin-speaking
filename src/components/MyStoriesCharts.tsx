import { useEffect, useMemo, useRef } from "react";
import Chart from "chart.js/auto";
import { wordMissSeverity, type WordMissStats } from "../utils/myStoriesUtils";

// ── Shared Chart.js look for the teacher analytics tabs ────────────────────
// A plainer, more neutral "data dashboard" register than the rest of the
// app's playful student-facing style: the app's own sans stack instead of
// the display/heading font, restrained gridlines, and a flat (non-bold)
// tick weight. Set once so every chart on Quiz Analytics and Recording
// Analytics inherits it without repeating options per chart.
const CHART_FONT_FAMILY =
  '"Inter", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif';
Chart.defaults.font.family = CHART_FONT_FAMILY;
Chart.defaults.font.size = 12;
Chart.defaults.color = "#6f697c";
Chart.defaults.borderColor = "#efe6d3";
Chart.defaults.plugins.tooltip.backgroundColor = "#201d29";
Chart.defaults.plugins.tooltip.titleFont = { family: CHART_FONT_FAMILY, weight: "bold" };
Chart.defaults.plugins.tooltip.bodyFont = { family: CHART_FONT_FAMILY };
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 6;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.legend.labels.boxHeight = 8;

export const QUIZ_MODE_INFO: Record<"speed" | "strikes" | "free", { icon: string; label: string; color: string }> = {
  speed: { icon: "⏱️", label: "Speed", color: "#7c3aed" },
  strikes: { icon: "❌", label: "3 Strikes", color: "#1c9a5b" },
  free: { icon: "🎯", label: "Free Practice", color: "#8a5a12" },
};

export const AI_FEEDBACK_CATEGORIES = ["fluency", "grammar", "vocabulary"] as const;
export const AI_FEEDBACK_CATEGORY_INFO: Record<(typeof AI_FEEDBACK_CATEGORIES)[number], { label: string; color: string }> = {
  fluency: { label: "Fluency", color: "#7c3aed" },
  grammar: { label: "Grammar", color: "#1c9a5b" },
  vocabulary: { label: "Vocabulary", color: "#8a5a12" },
};

/** Chart.js canvas that (re)builds its chart whenever `build` changes,
 * tearing down the previous instance first — same lifecycle as
 * components/PitchChart.tsx. */
export function QuizChartCanvas({ build, height = 220 }: { build: (ctx: CanvasRenderingContext2D) => Chart; height?: number }) {
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
    <div className="quiz-analytics-chart-canvas" style={{ height }}>
      <canvas ref={canvasRef} />
    </div>
  );
}

export function ModeAccuracyChart({ data }: { data: Array<{ mode: "speed" | "strikes" | "free"; avg: number; count: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((m) => `${QUIZ_MODE_INFO[m.mode].icon} ${QUIZ_MODE_INFO[m.mode].label}`),
          datasets: [{
            label: "Average accuracy",
            data: data.map((m) => m.avg),
            backgroundColor: data.map((m) => QUIZ_MODE_INFO[m.mode].color),
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => {
                  const m = data[item.dataIndex];
                  return `${item.parsed.y}% avg accuracy (${m.count} attempt${m.count === 1 ? "" : "s"})`;
                },
              },
            },
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
    [data],
  );
  return <QuizChartCanvas build={build} />;
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
            borderColor: "#7c3aed",
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
  return <QuizChartCanvas build={build} />;
}

export function WordMissChart({ data }: { data: WordMissStats[] }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) => {
      // Draws "N× (P%)" past the end of each bar. Chart.js has no built-in
      // data-label support without a paid/extra plugin, so this is a small
      // inline plugin closing over `data` rather than a new dependency.
      const barEndLabels = {
        id: "wordMissBarLabels",
        afterDatasetsDraw(chart: Chart) {
          const meta = chart.getDatasetMeta(0);
          chart.ctx.save();
          chart.ctx.font = `600 12px ${CHART_FONT_FAMILY}`;
          chart.ctx.fillStyle = "#4a4556";
          chart.ctx.textBaseline = "middle";
          chart.ctx.textAlign = "left";
          meta.data.forEach((bar, i) => {
            const w = data[i];
            const { x, y } = bar.getProps(["x", "y"], true);
            chart.ctx.fillText(`${w.timesMissed}× (${w.missRatePct}%)`, x + 6, y);
          });
          chart.ctx.restore();
        },
      };

      return new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((w) => w.word),
          datasets: [{
            label: "Times missed",
            data: data.map((w) => w.timesMissed),
            backgroundColor: data.map((w) =>
              wordMissSeverity(w.missRatePct) === "critical"
                ? "#c81e3a"
                : wordMissSeverity(w.missRatePct) === "watch"
                  ? "#ffa726"
                  : "#8a5a12",
            ),
            borderRadius: 4,
          }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { right: 64 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => {
                  const w = data[item.dataIndex];
                  return [
                    `Missed ${w.timesMissed} of ${w.timesAsked} time${w.timesAsked === 1 ? "" : "s"} (${w.missRatePct}%)`,
                    `Avg. ${(w.avgTimeMs / 1000).toFixed(1)}s to answer`,
                  ];
                },
              },
            },
          },
          scales: {
            x: {
              beginAtZero: true,
              ticks: { precision: 0 },
              title: { display: true, text: "Times missed (most to least common)" },
            },
            y: { grid: { display: false } },
          },
        },
        plugins: [barEndLabels],
      });
    },
    [data],
  );
  return <QuizChartCanvas build={build} height={Math.max(180, data.length * 32)} />;
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
              borderColor: "#7c3aed",
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
  return <QuizChartCanvas build={build} />;
}

export function AiFeedbackCategoryChart({ data }: { data: Array<{ category: (typeof AI_FEEDBACK_CATEGORIES)[number]; avg: number; count: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((c) => AI_FEEDBACK_CATEGORY_INFO[c.category].label),
          datasets: [{
            label: "Average score",
            data: data.map((c) => c.avg),
            backgroundColor: data.map((c) => AI_FEEDBACK_CATEGORY_INFO[c.category].color),
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => {
                  const c = data[item.dataIndex];
                  return `${item.parsed.y}/100 avg (${c.count} score${c.count === 1 ? "" : "s"})`;
                },
              },
            },
          },
          scales: {
            y: { beginAtZero: true, max: 100, title: { display: true, text: "Score" } },
            x: { grid: { display: false } },
          },
        },
      }),
    [data],
  );
  return <QuizChartCanvas build={build} />;
}

export function RecordingsPerTopicChart({ data }: { data: Array<{ topic: string; count: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((t) => t.topic),
          datasets: [{
            label: "Recordings",
            data: data.map((t) => t.count),
            backgroundColor: "#0b5fa8",
            borderRadius: 4,
          }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { beginAtZero: true, title: { display: true, text: "Recordings" }, ticks: { precision: 0 } },
            y: { grid: { display: false } },
          },
        },
      }),
    [data],
  );
  return <QuizChartCanvas build={build} height={Math.max(160, data.length * 32)} />;
}
