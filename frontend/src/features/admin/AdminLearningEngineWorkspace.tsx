import { useState } from "react";
import type { Student } from "../../services/api/roster-help";
import AdminBktDebugPage from "./AdminBktDebugPage";
import AdminAlgorithmVerifierPage from "./AdminAlgorithmVerifierPage";
import AdminLearningEnginePage from "./AdminLearningEnginePage";
import "./AdminInsightsWorkspace.css";

type LearningTab = "runtime" | "verification" | "verifier" | "replay";

export default function AdminLearningEngineWorkspace({
  students,
  refreshKey = 0,
  initialTab = "runtime",
}: {
  students: Student[];
  refreshKey?: number;
  initialTab?: LearningTab;
}) {
  const [activeTab, setActiveTab] = useState<LearningTab>(initialTab === "verification" ? "verifier" : initialTab);

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
          aria-selected={activeTab === "verifier"}
          className={activeTab === "verifier" ? "is-active" : ""}
          onClick={() => setActiveTab("verifier")}
        >
          Algorithm verifier
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
      {activeTab === "verifier" && <AdminAlgorithmVerifierPage refreshKey={refreshKey} />}
      {activeTab === "replay" && <AdminBktDebugPage students={students} />}
    </section>
  );
}
