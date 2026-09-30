import { lazy, Suspense, useRef, useState, type KeyboardEvent } from "react";
import type { AudioRecord } from "@entities/audio";
import TeacherPracticeDebugPage from "../teacher/TeacherPracticeDebugPage";
import AdminAsrComparePage from "./AdminAsrComparePage";
import "./AdminInsightsWorkspace.css";

const PronunciationEvaluationPage = lazy(() => import("./pronunciation/EvaluationPage"));

type SpeechTab = "practice" | "asr" | "pronunciation";

const SPEECH_TABS: Array<{ id: SpeechTab; label: string }> = [
  { id: "practice", label: "Practice debugger" },
  { id: "asr", label: "ASR compare" },
  { id: "pronunciation", label: "Pronunciation score" },
];

export default function AdminSpeechDiagnosticsWorkspace({
  records,
  initialTab = "practice",
}: {
  records: AudioRecord[];
  initialTab?: SpeechTab;
}) {
  const [activeTab, setActiveTab] = useState<SpeechTab>(initialTab);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tabIndex: number) => {
    let nextIndex = tabIndex;
    if (event.key === "ArrowRight") nextIndex = (tabIndex + 1) % SPEECH_TABS.length;
    else if (event.key === "ArrowLeft") nextIndex = (tabIndex - 1 + SPEECH_TABS.length) % SPEECH_TABS.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = SPEECH_TABS.length - 1;
    else return;

    event.preventDefault();
    const nextTab = SPEECH_TABS[nextIndex];
    setActiveTab(nextTab.id);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <section className="admin-insights-workspace" aria-label="Speech diagnostics">
      <nav className="admin-insight-tabs" aria-label="Speech diagnostic views" role="tablist">
        {SPEECH_TABS.map((tab, index) => (
          <button
            key={tab.id}
            ref={(element) => { tabRefs.current[index] = element; }}
            id={`admin-speech-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-controls={`admin-speech-panel-${tab.id}`}
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

      {activeTab === "practice" ? (
        <div id="admin-speech-panel-practice" className="admin-insight-tabpanel" role="tabpanel" aria-labelledby="admin-speech-tab-practice">
          <TeacherPracticeDebugPage records={records} />
        </div>
      ) : null}
      {activeTab === "asr" ? (
        <div id="admin-speech-panel-asr" className="admin-insight-tabpanel" role="tabpanel" aria-labelledby="admin-speech-tab-asr">
          <AdminAsrComparePage />
        </div>
      ) : null}
      {activeTab === "pronunciation" ? (
        <div id="admin-speech-panel-pronunciation" className="admin-insight-tabpanel" role="tabpanel" aria-labelledby="admin-speech-tab-pronunciation">
          <Suspense fallback={<p className="admin-insight-loading" role="status">Loading pronunciation evaluator…</p>}>
            <PronunciationEvaluationPage />
          </Suspense>
        </div>
      ) : null}
    </section>
  );
}
