import { useEffect, useRef } from "react";
import Chart from "chart.js/auto";

interface PitchChartProps {
  pitchContour: Array<[number, number]>;
  detectedTone: number;
}

// Chart.js can't read CSS custom properties, so these mirror the app's real
// tone→color tokens by hand (see ToneMark.tsx for the canonical mapping):
// tone1=--tone1 (blue), tone2=--jade (green), tone3=--gold (amber),
// tone4=--seal (violet). Keep these in sync if the tokens in index.css change.
const TONE_COLORS: Record<number, string> = {
  1: "rgba(30, 150, 255, 0.85)", // --tone1
  2: "rgba(28, 154, 91, 0.85)", // --jade
  3: "rgba(255, 167, 38, 0.85)", // --gold
  4: "rgba(124, 58, 237, 0.85)", // --seal
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
    <div className="pitch-chart-container" role="img" aria-label={`Pitch contour chart for ${TONE_NAMES[detectedTone] ?? "the recorded audio"}`}>
      <canvas ref={chartRef}></canvas>
    </div>
  );
}
