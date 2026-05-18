import { useEffect, useRef } from "react";
import Chart from "chart.js/auto";

interface PitchChartProps {
  pitchContour: Array<[number, number]>;
  detectedTone: number;
}

const TONE_COLORS = {
  1: "rgba(255, 107, 107, 0.8)", // Red - High level
  2: "rgba(76, 175, 80, 0.8)", // Green - Rising
  3: "rgba(255, 193, 7, 0.8)", // Orange - Falling-rising
  4: "rgba(33, 150, 243, 0.8)", // Blue - Falling
};

const TONE_NAMES = {
  1: "Tone 1: High Level (妈 mā)",
  2: "Tone 2: Rising (麻 má)",
  3: "Tone 3: Falling-Rising (马 mǎ)",
  4: "Tone 4: Falling (骂 mà)",
};

export default function PitchChart({
  pitchContour,
  detectedTone,
}: PitchChartProps) {
  const chartRef = useRef<HTMLCanvasElement>(null);
  const chartInstanceRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!chartRef.current || !pitchContour || pitchContour.length === 0) {
      return;
    }

    // Destroy previous chart instance
    if (chartInstanceRef.current) {
      chartInstanceRef.current.destroy();
    }

    // Prepare data
    const times = pitchContour.map((p) => p[0].toFixed(2));
    const frequencies = pitchContour.map((p) => p[1]);

    // Create chart
    const ctx = chartRef.current.getContext("2d");
    if (!ctx) return;

    chartInstanceRef.current = new Chart(ctx, {
      type: "line",
      data: {
        labels: times,
        datasets: [
          {
            label: "Your Pitch",
            data: frequencies,
            borderColor: TONE_COLORS[detectedTone as keyof typeof TONE_COLORS],
            backgroundColor:
              `${TONE_COLORS[detectedTone as keyof typeof TONE_COLORS]}`.replace(
                "0.8",
                "0.1",
              ),
            borderWidth: 2,
            tension: 0.4,
            fill: true,
            pointRadius: 1,
            pointHoverRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            display: true,
            position: "top",
          },
          title: {
            display: true,
            text: `Pitch Contour - ${TONE_NAMES[detectedTone as keyof typeof TONE_NAMES]}`,
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
            min: 50,
            max: 400,
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
      if (chartInstanceRef.current) {
        chartInstanceRef.current.destroy();
      }
    };
  }, [pitchContour, detectedTone]);

  return (
    <div className="pitch-chart-container">
      <canvas ref={chartRef}></canvas>
    </div>
  );
}
