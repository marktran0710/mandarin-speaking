import type { HelpRequest } from "../services/database";
import DashboardStat from "./DashboardStat";
import TeacherHelpQueue from "./TeacherHelpQueue";

export default function TeacherOverviewView({
  totalRecords,
  feedbackReadyCount,
  averageFluency,
  averageToneAccuracy,
  helpRequests,
  onResolveHelpRequest,
}: {
  totalRecords: number;
  feedbackReadyCount: number;
  averageFluency: number | null;
  averageToneAccuracy: number | null;
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
}) {
  return (
    <>
      <section className="teacher-stat-grid" aria-label="Class overview">
        <DashboardStat
          label="Submissions"
          value={String(totalRecords)}
          note="Total saved student attempts"
        />
        <DashboardStat
          label="Feedback ready"
          value={String(feedbackReadyCount)}
          note="Gemini/Praat results available"
        />
        <DashboardStat
          label="Avg. fluency"
          value={averageFluency === null ? "--" : `${averageFluency}/100`}
          note="Based on analyzed recordings"
        />
        <DashboardStat
          label="Tone accuracy"
          value={
            averageToneAccuracy === null ? "--" : `${averageToneAccuracy}%`
          }
          note="Class pronunciation trend"
        />
      </section>

      <section className="teacher-dashboard-grid">
        <TeacherHelpQueue
          helpRequests={helpRequests}
          onResolveHelpRequest={onResolveHelpRequest}
          compact
        />
      </section>
    </>
  );
}
