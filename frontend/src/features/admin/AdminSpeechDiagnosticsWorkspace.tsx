import { useState } from "react";
import type { AudioRecord } from "@entities/audio";
import TeacherPracticeDebugPage from "../teacher/TeacherPracticeDebugPage";
import AdminAsrComparePage from "./AdminAsrComparePage";
import "./AdminInsightsWorkspace.css";

type SpeechTab = "practice" | "asr";

export default function AdminSpeechDiagnosticsWorkspace({
  records,
  initialTab = "practice",
}: {
  records: AudioRecord[];
  initialTab?: SpeechTab;
}) {
  const [activeTab, setActiveTab] = useState<SpeechTab>(initialTab);

  return (
    <section className="admin-insights-workspace" aria-label="Speech diagnostics">
      <nav className="admin-insight-tabs" aria-label="Speech diagnostic views" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "practice"}
          className={activeTab === "practice" ? "is-active" : ""}
          onClick={() => setActiveTab("practice")}
        >
          Practice debugger
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "asr"}
          className={activeTab === "asr" ? "is-active" : ""}
          onClick={() => setActiveTab("asr")}
        >
          ASR compare
        </button>
      </nav>

      {activeTab === "practice" ? <TeacherPracticeDebugPage records={records} /> : <AdminAsrComparePage />}
    </section>
  );
}
