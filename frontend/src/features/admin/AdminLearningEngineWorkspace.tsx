import { useState } from "react";
import type { Student } from "../../services/api/roster-help";
import AdminBktDebugPage from "./AdminBktDebugPage";
import AdminBktVerificationPage from "./AdminBktVerificationPage";
import AdminLearningEnginePage from "./AdminLearningEnginePage";
import "./AdminInsightsWorkspace.css";

type LearningTab = "runtime" | "verification" | "replay";

export default function AdminLearningEngineWorkspace({
  students,
  refreshKey = 0,
  initialTab = "runtime",
}: {
  students: Student[];
  refreshKey?: number;
  initialTab?: LearningTab;
}) {
  const [activeTab, setActiveTab] = useState<LearningTab>(initialTab);

  return (
    <section className="admin-insights-workspace" aria-label="Learning engine tools">
      <nav className="admin-insight-tabs" aria-label="Learning engine views" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "runtime"}
          className={activeTab === "runtime" ? "is-active" : ""}
          onClick={() => setActiveTab("runtime")}
        >
          Runtime model
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "verification"}
          className={activeTab === "verification" ? "is-active" : ""}
          onClick={() => setActiveTab("verification")}
        >
          BKT verification
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "replay"}
          className={activeTab === "replay" ? "is-active" : ""}
          onClick={() => setActiveTab("replay")}
        >
          Synthetic replay
        </button>
      </nav>

      {activeTab === "runtime" && <AdminLearningEnginePage />}
      {activeTab === "verification" && <AdminBktVerificationPage refreshKey={refreshKey} />}
      {activeTab === "replay" && <AdminBktDebugPage students={students} />}
    </section>
  );
}
