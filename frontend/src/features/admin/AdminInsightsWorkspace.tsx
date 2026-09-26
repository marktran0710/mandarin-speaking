import { useState } from "react";
import AdminIrtStudentPanel from "../../components/analytics/AdminIrtStudentPanel";
import MeasurementAnalyticsPanel from "../../components/analytics/MeasurementAnalyticsPanel";
import KnowledgeModelPilotPanel from "../../components/analytics/KnowledgeModelPilotPanel";
import type { MeasurementEvent } from "../../utils/measurement";
import type { AudioRecord } from "@entities/audio";
import type { Student, VocabQuizAttempt } from "../../services/database";
import "./AdminInsightsWorkspace.css";

type InsightsTab = "students" | "measurement";

interface AdminInsightsWorkspaceProps {
  students: Student[];
  attempts: VocabQuizAttempt[];
  records: AudioRecord[];
  events: MeasurementEvent[];
  initialTab?: InsightsTab;
}

export default function AdminInsightsWorkspace({
  students,
  attempts,
  records,
  events,
  initialTab = "students",
}: AdminInsightsWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<InsightsTab>(initialTab);

  return (
    <section className="admin-insights-workspace" aria-label="Student insights">
      <nav className="admin-insight-tabs" aria-label="Student insight views" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "students"}
          className={activeTab === "students" ? "is-active" : ""}
          onClick={() => setActiveTab("students")}
        >
          Student analytics
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "measurement"}
          className={activeTab === "measurement" ? "is-active" : ""}
          onClick={() => setActiveTab("measurement")}
        >
          Measurement health
        </button>
      </nav>

      {activeTab === "students" ? (
        <>
          <AdminIrtStudentPanel students={students} attempts={attempts} />
          <KnowledgeModelPilotPanel />
        </>
      ) : (
        <MeasurementAnalyticsPanel records={records} events={events} />
      )}
    </section>
  );
}
