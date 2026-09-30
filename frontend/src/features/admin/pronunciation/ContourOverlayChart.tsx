import { useEffect, useRef } from "react";
import Chart from "chart.js/auto";
import type { PronunciationFeatureSet } from "@shared/api/pronunciation";
import { contourSeries, syllableBoundaries } from "./model";

// Chart.js cannot read CSS custom properties, so these mirror --jade and --gold
// (see PitchChart.tsx for the same hand-kept mapping).
const REFERENCE_COLOR = "rgba(28, 154, 91, 0.9)";
const STUDENT_COLOR = "rgba(255, 167, 38, 0.95)";

/** Reference and student pitch on one axis. Time is scaled to the whole
 * utterance and pitch is in semitones against each speaker's own median, so
 * only the *shape* is compared - never the voice range or the speed. */
export default function ContourOverlayChart({
  reference,
  student,
}: {
  reference: PronunciationFeatureSet;
  student: PronunciationFeatureSet | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const marks = syllableBoundaries(reference);

    const chart = new Chart(context, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Teacher recording",
            data: contourSeries(reference),
            borderColor: REFERENCE_COLOR,
            showLine: true,
            pointRadius: 0,
            borderWidth: 3,
            tension: 0.25,
          },
          {
            label: "Student",
            data: contourSeries(student),
            borderColor: STUDENT_COLOR,
            showLine: true,
            pointRadius: 0,
            borderWidth: 3,
            tension: 0.25,
          },
        ],
      },
      options: {
        animation: false,
        maintainAspectRatio: false,
        scales: {
          x: { type: "linear", min: 0, max: 1, ticks: { display: false }, grid: { display: false } },
          y: { title: { display: true, text: "Pitch (semitones from own median)" } },
        },
        plugins: { legend: { position: "bottom" } },
      },
      plugins: [
        {
          id: "syllable-marks",
          afterDatasetsDraw(instance) {
            const { ctx, chartArea, scales } = instance;
            ctx.save();
            ctx.setLineDash([3, 4]);
            ctx.strokeStyle = "rgba(120, 120, 120, 0.35)";
            ctx.fillStyle = "rgba(90, 90, 90, 0.9)";
            ctx.font = "13px sans-serif";
            for (const mark of marks) {
              const x = scales.x.getPixelForValue(mark.x);
              ctx.beginPath();
              ctx.moveTo(x, chartArea.top);
              ctx.lineTo(x, chartArea.bottom);
              ctx.stroke();
              ctx.fillText(mark.label, x + 3, chartArea.top + 13);
            }
            ctx.restore();
          },
        },
      ],
    });
    return () => chart.destroy();
  }, [reference, student]);

  return (
    <div className="pron-chart">
      <canvas ref={canvasRef} role="img" aria-label="Teacher and student pitch contours overlaid" />
    </div>
  );
}
