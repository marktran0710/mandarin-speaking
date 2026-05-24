import { useEffect, useRef } from "react";
import Chart from "chart.js/auto";

interface PitchChartProps {
  pitchContour: Array<[number, number]>;
  detectedTone: number;
}

const TONE_COLORS: Record<number, string> = {
  1: "rgba(255, 107, 107, 0.85)",
  2: "rgba(34, 197, 94, 0.85)",
  3: "rgba(245, 158, 11, 0.85)",
  4: "rgba(59, 130, 246, 0.85)",
};

const TONE_NAMES: Record<number, string> = {
  1: "Tone 1: High Level (媽 ma1)",
  2: "Tone 2: Rising (麻 ma2)",
  3: "Tone 3: Falling-Rising (馬 ma3)",
  4: "Tone 4: Falling (罵 ma4)",
};

export default function PitchChart({
  pitchContour,
  detectedTone,
}: PitchChartProps) {
  const chartRef = useRef<HTMLCanvasElement>(null);
  const chartInstanceRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!chartRef.current || pitchContour.length === 0) {
      return;
    }

    chartInstanceRef.current?.destroy();

    const times = pitchContour.map((point) => point[0].toFixed(2));
    const frequencies = pitchContour.map((point) => point[1]);
    const toneColor = TONE_COLORS[detectedTone] || "rgba(99, 102, 241, 0.85)";
    const ctx = chartRef.current.getContext("2d");
    if (!ctx) return;

    chartInstanceRef.current = new Chart(ctx, {
      type: "line",
      data: {
        labels: times,
        datasets: [
          {
            label: "Your pitch from Praat",
            data: frequencies,
            borderColor: toneColor,
            backgroundColor: toneColor.replace("0.85", "0.14"),
            borderWidth: 3,
            tension: 0.35,
            fill: true,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "top",
          },
          title: {
            display: true,
            text: `Praat Pitch Contour - ${
              TONE_NAMES[detectedTone] || "Tone not detected"
            }`,
            font: { size: 14, weight: "bold" },
          },
        },
        scales: {
          y: {
            beginAtZero: false,
            title: {
              display: true,
              text: "Frequency (Hz)",
            },
          },
          x: {
            title: {
              display: true,
              text: "Time (seconds)",
            },
          },
        },
      },
    });

    return () => {
      chartInstanceRef.current?.destroy();
    };
  }, [pitchContour, detectedTone]);

  return (
    <div className="pitch-chart-container">
      <canvas ref={chartRef}></canvas>
    </div>
  );
}
