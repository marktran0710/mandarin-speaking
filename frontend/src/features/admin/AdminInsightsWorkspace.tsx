import { lazy, Suspense, useRef, useState, type KeyboardEvent } from "react";
import AdminIrtStudentPanel from "../../components/analytics/AdminIrtStudentPanel";
import MeasurementAnalyticsPanel from "../../components/analytics/MeasurementAnalyticsPanel";
import KnowledgeModelPilotPanel from "../../components/analytics/KnowledgeModelPilotPanel";
import type { MeasurementEvent } from "../../utils/measurement";
import type { AudioRecord } from "@entities/audio";
import type { Student, VocabQuizAttempt } from "../../services/database";
import "./AdminInsightsWorkspace.css";

const RoundScoresPanel = lazy(() => import("./round-scores/RoundScoresPanel"));

export type InsightsTab = "students" | "round-scores" | "measurement";

const INSIGHT_TABS: Array<{ id: InsightsTab; label: string }> = [
  { id: "students", label: "Student analytics" },
  { id: "round-scores", label: "Round scores" },
  { id: "measurement", label: "Measurement health" },
];

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
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tabIndex: number) => {
    let nextIndex = tabIndex;
    if (event.key === "ArrowRight") nextIndex = (tabIndex + 1) % INSIGHT_TABS.length;
    else if (event.key === "ArrowLeft") nextIndex = (tabIndex - 1 + INSIGHT_TABS.length) % INSIGHT_TABS.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = INSIGHT_TABS.length - 1;
    else return;

    event.preventDefault();
    const nextTab = INSIGHT_TABS[nextIndex];
    setActiveTab(nextTab.id);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <section className="admin-insights-workspace" aria-label="Student insights">
      <nav className="admin-insight-tabs" aria-label="Student insight views" role="tablist">
        {INSIGHT_TABS.map((tab, index) => (
          <button
            key={tab.id}
            ref={(element) => { tabRefs.current[index] = element; }}
            id={`admin-insight-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-controls={`admin-insight-panel-${tab.id}`}
            aria-selected={activeTab === tab.id}
            tabIndex={activeTab === tab.id ? 0 : -1}
            className={activeTab === tab.id ? "is-active" : ""}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "students" ? (
        <div
          id="admin-insight-panel-students"
          className="admin-insight-tabpanel"
          role="tabpanel"
          aria-labelledby="admin-insight-tab-students"
        >
          <AdminIrtStudentPanel students={students} attempts={attempts} />
          <KnowledgeModelPilotPanel />
        </div>
      ) : null}
      {activeTab === "round-scores" ? (
        <div
          id="admin-insight-panel-round-scores"
          className="admin-insight-tabpanel"
          role="tabpanel"
          aria-labelledby="admin-insight-tab-round-scores"
        >
          <Suspense fallback={<p className="admin-insight-loading" role="status">Loading round scores…</p>}>
            <RoundScoresPanel students={students} attempts={attempts} />
          </Suspense>
        </div>
      ) : null}
      {activeTab === "measurement" ? (
        <div
          id="admin-insight-panel-measurement"
          className="admin-insight-tabpanel"
          role="tabpanel"
          aria-labelledby="admin-insight-tab-measurement"
        >
          <MeasurementAnalyticsPanel records={records} events={events} />
        </div>
      ) : null}
    </section>
  );
}
