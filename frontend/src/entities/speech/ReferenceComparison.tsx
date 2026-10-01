import { lazy, Suspense } from "react";
import type { PronunciationReferenceComparison } from "@shared/api/pronunciation";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import { studentUiCopy, type StudentUiCopyKey } from "../../i18n/student-ui-copy";
import "./ReferenceComparison.css";

const PitchChart = lazy(() => import("../../components/pitch/LibrosaPitchChart"));
const CHART_LABELS = {
  reference: studentUiCopy.teacherModel.zh,
  student: studentUiCopy.yourRecording.zh,
  time: studentUiCopy.comparisonTime.zh,
  pitch: studentUiCopy.comparisonPitchAxis.zh,
  description: studentUiCopy.voiceComparison.zh,
};
const SIMILARITIES: Array<[string, StudentUiCopyKey]> = [
  ["mfcc_similarity", "comparisonSound"],
  ["pitch_similarity", "comparisonPitch"],
  ["timing_similarity", "comparisonTiming"],
];

function percent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—";
}

export default function ReferenceComparison({ comparison }: { comparison: PronunciationReferenceComparison }) {
  const { reference, student } = comparison.contours;
  const hasPitch = comparison.measurements.pitch_similarity != null
    && reference.length > 1 && student.length > 1
    && reference.some(([, pitch]) => pitch !== null) && student.some(([, pitch]) => pitch !== null);

  return (
    <section className="sa-reference-comparison" aria-label={studentUiCopy.voiceComparison.zh}>
      <h3><StudentSystemText k="voiceComparison" /></h3>
      {comparison.status === "scored" ? (
        <>
          {hasPitch ? (
            <Suspense fallback={<p role="status"><StudentSystemText k="loading" /></p>}>
              <PitchChart reference={reference} student={student} labels={CHART_LABELS} className="sa-reference-comparison__chart" />
            </Suspense>
          ) : (
            <p><StudentSystemText k="comparisonPitchUnavailable" /></p>
          )}
          <dl>
            {SIMILARITIES.map(([metric, label]) => (
              <div key={metric}>
                <dt><StudentSystemText k={label} /></dt>
                <dd>{percent(comparison.measurements[metric])}</dd>
              </div>
            ))}
          </dl>
          <p><StudentSystemText k="comparisonSimilarityNote" /></p>
        </>
      ) : (
        <p><StudentSystemText k="comparisonUnavailable" /></p>
      )}
    </section>
  );
}
