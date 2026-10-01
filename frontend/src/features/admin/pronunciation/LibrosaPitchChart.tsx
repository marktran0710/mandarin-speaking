import { useEffect, useRef } from "react";
import Chart from "chart.js/auto";

type Point = [number, number | null];
type ChartPoint = { x: number; y: number };

const REFERENCE_COLOR = "rgba(28, 154, 91, 0.9)";
const STUDENT_COLOR = "rgba(255, 167, 38, 0.95)";

function normalized(points: Point[]): ChartPoint[] {
  const end = points[points.length - 1]?.[0] ?? 0;
  const scale = end > 0 ? end : 1;
  return points.map(([x, y]) => ({ x: x / scale, y: y ?? Number.NaN }));
}

export default function LibrosaPitchChart({
  reference,
  student,
  alignment,
}: {
  reference: Point[];
  student: Point[];
  alignment?: Array<[number, number]>;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    let referenceData = normalized(reference);
    let studentData = normalized(student);
    if (alignment?.length) {
      const end = reference[reference.length - 1]?.[0] ?? 1;
      referenceData = [];
      studentData = [];
      for (const [studentIndex, referenceIndex] of alignment) {
        const teacher = reference[referenceIndex];
        const learner = student[studentIndex];
        if (!teacher || !learner) continue;
        const x = teacher[0] / (end > 0 ? end : 1);
        referenceData.push({ x, y: teacher[1] ?? Number.NaN });
        studentData.push({ x, y: learner[1] ?? Number.NaN });
      }
    }
    const chart = new Chart(context, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Teacher (librosa)",
            data: referenceData,
            borderColor: REFERENCE_COLOR,
            showLine: true,
            pointRadius: 0,
            borderWidth: 2,
            tension: 0,
          },
          {
            label: "Student (librosa)",
            data: studentData,
            borderColor: STUDENT_COLOR,
            showLine: true,
            pointRadius: 0,
            borderWidth: 2,
            tension: 0,
          },
        ],
      },
      options: {
        animation: false,
        maintainAspectRatio: false,
        scales: {
          x: { type: "linear", min: 0, max: 1, title: { display: true, text: alignment?.length ? "Teacher relative time (DTW aligned)" : "Relative time" } },
          y: { title: { display: true, text: "Relative pitch (semitones)" } },
        },
        plugins: { legend: { position: "bottom" } },
      },
    });
    return () => chart.destroy();
  }, [reference, student, alignment]);

  return <div className="pron-chart"><canvas ref={canvasRef} role="img" aria-label="Librosa teacher and student pitch contours" /></div>;
}
