import { useEffect, useMemo, useRef } from "react";
import Chart from "chart.js/auto";
import type { ChartConfiguration, TooltipItem } from "chart.js";
import { formatCompletedAt } from "./format";
import { ROUND_DEFINITIONS, cellSecondsPerQuestion, type StudentLessonRow } from "./model";

const STUDENT_COLOR = { fill: "rgba(20, 139, 111, 0.78)", border: "#148b6f" };
const CLASS_COLOR = { fill: "rgba(111, 98, 72, 0.32)", border: "#6f6248" };
const RESPONSE_TIME_COLOR = "#3f3528";
const CLASS_LABEL = "Class average";
const RESPONSE_TIME_LABEL = "Response time / question";
type StudentRoundChartType = "bar" | "line";

export function formatStudentRoundTooltip(
  studentName: string,
  lesson: StudentLessonRow,
  datasetIndex: number,
  dataIndex: number,
): string {
  const round = ROUND_DEFINITIONS[dataIndex];
  if (!round) return "";
  const cell = lesson.rounds[round.mode];

  if (datasetIndex === 0) {
    if (!cell) return `${studentName}: Not completed`;
    const seconds = cellSecondsPerQuestion(cell);
    const time = seconds === null ? "time unavailable" : `${seconds}s/question`;
    return `${studentName}: ${cell.score}% · ${cell.correctCount}/${cell.totalQuestions} · ${time} · ${formatCompletedAt(cell.completedAt)}`;
  }
  if (datasetIndex === 1) {
    const { average, completed } = lesson.classRounds[round.mode];
    if (average === null) return `${CLASS_LABEL}: No completed students`;
    return `${CLASS_LABEL}: ${average}% · ${completed} student${completed === 1 ? "" : "s"}`;
  }
  if (datasetIndex === 2) {
    const seconds = cell ? cellSecondsPerQuestion(cell) : null;
    return seconds === null ? `${RESPONSE_TIME_LABEL}: Not available` : `${RESPONSE_TIME_LABEL}: ${seconds}s`;
  }
  return "";
}

export function createStudentRoundChartConfig(
  studentName: string,
  lesson: StudentLessonRow,
  reduceMotion = false,
): ChartConfiguration<StudentRoundChartType, Array<number | null>, string> {
  return {
    type: "bar",
    data: {
      labels: ROUND_DEFINITIONS.map((round) => round.label),
      datasets: [
        {
          type: "bar" as const,
          label: studentName,
          data: ROUND_DEFINITIONS.map((round) => lesson.rounds[round.mode]?.score ?? null),
          yAxisID: "score",
          backgroundColor: STUDENT_COLOR.fill,
          borderColor: STUDENT_COLOR.border,
          borderWidth: 1,
          borderRadius: 4,
          borderSkipped: false as const,
          maxBarThickness: 44,
          categoryPercentage: 0.7,
          barPercentage: 0.9,
          order: 2,
        },
        {
          type: "bar" as const,
          label: CLASS_LABEL,
          data: ROUND_DEFINITIONS.map((round) => lesson.classRounds[round.mode].average),
          yAxisID: "score",
          backgroundColor: CLASS_COLOR.fill,
          borderColor: CLASS_COLOR.border,
          borderWidth: 1,
          borderRadius: 4,
          borderSkipped: false as const,
          maxBarThickness: 44,
          categoryPercentage: 0.7,
          barPercentage: 0.9,
          order: 2,
        },
        {
          type: "line" as const,
          label: RESPONSE_TIME_LABEL,
          data: ROUND_DEFINITIONS.map((round) => {
            const cell = lesson.rounds[round.mode];
            return cell ? cellSecondsPerQuestion(cell) : null;
          }),
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
            title: (items) => ROUND_DEFINITIONS[items[0]?.dataIndex ?? -1]?.label ?? "",
            label: (item: TooltipItem<StudentRoundChartType>) => (
              formatStudentRoundTooltip(studentName, lesson, item.datasetIndex, item.dataIndex)
            ),
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
          title: { display: true, text: "Response time / question (seconds)" },
          ticks: { callback: (value) => `${value}s` },
          grid: { drawOnChartArea: false },
        },
        x: {
          grid: { display: false },
          ticks: {
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0,
            callback: (_value, index) => {
              const round = ROUND_DEFINITIONS[index];
              return round ? [`Round ${round.number}`, round.dimension] : "";
            },
          },
        },
      },
    },
  };
}

export default function StudentRoundChart({ studentName, lesson }: { studentName: string; lesson: StudentLessonRow }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart<StudentRoundChartType, Array<number | null>, string> | null>(null);
  const reduceMotion = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  const config = useMemo(
    () => createStudentRoundChartConfig(studentName, lesson, reduceMotion),
    [lesson, reduceMotion, studentName],
  );

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
      <ul className="round-scores-legend" aria-label="Student round series">
        <li>
          <span style={{ backgroundColor: STUDENT_COLOR.border }} aria-hidden="true" />
          {studentName}
        </li>
        <li>
          <span style={{ backgroundColor: CLASS_COLOR.border }} aria-hidden="true" />
          {CLASS_LABEL}
        </li>
        <li>
          <span className="round-scores-legend-line" aria-hidden="true" />
          {RESPONSE_TIME_LABEL}
        </li>
      </ul>
      <div className="round-scores-chart-scroll" tabIndex={0} aria-label="Scrollable student round chart">
        <div className="round-scores-chart-canvas student-round-chart-canvas">
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Chart comparing ${studentName} with the class average on each of the three rounds of ${lesson.title}, plus response time per question.`}
          />
        </div>
      </div>
    </div>
  );
}
