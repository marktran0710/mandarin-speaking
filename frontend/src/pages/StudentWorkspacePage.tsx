import { useEffect, useState } from "react";
import CreateStoryPage from "./CreateStoryPage";
import ImageNarrationPage from "./ImageNarrationPage";
import MyStoriesPage, { type AudioRecord } from "./MyStoriesPage";
import StudentIcon, { type StudentIconName } from "../components/StudentIcon";
import { BiLabel, BiText } from "../components/BiLabel";
import type { HelpRequest } from "../shared/api/learningApi";
import type { NewAudioRecord } from "../components/StoryRecorder";
import type { Topic } from "../components/TopicSelector";
import { getStudentName } from "../utils/studentSession";
import type { WorkspaceView } from "../types/studentWorkspace";
import { StudentWorkspaceShell } from "../features/student-workspace";
import { studentWorkspaceShellEnabled } from "../app/featureFlags";
import "../components/BiLabel.css";
import "./StudentWorkspacePage.css";

export type StudentWorkspaceView = WorkspaceView;

export interface StudentWorkspacePageProps {
  view: StudentWorkspaceView;
  onViewChange: (view: StudentWorkspaceView) => void;
  onAddRecord: (record: NewAudioRecord) => void;
  initialTopicId?: string;
  initialImageIndex?: number;
  initialStartAtQuiz?: boolean;
  initialTargetKey?: number;
  helpRequests: HelpRequest[];
  onRaiseHand: (message: string) => void;
  storyTopics: Topic[];
  describeTopics: Topic[];
  audioRecords: AudioRecord[];
  onSessionActiveChange: (active: boolean) => void;
  isInPracticeSession: boolean;
  onStartActivity?: (topicId: string, startAtQuiz: boolean) => void;
}

const WORKSPACE_VIEWS: Array<{
  id: StudentWorkspaceView;
  icon: StudentIconName;
  label: { zh: string; pinyin: string; en: string };
}> = [
  {
    id: "practice",
    icon: "image",
    label: { zh: "課程", pinyin: "Kèchéng", en: "Practice" },
  },
  {
    id: "progress",
    icon: "chart",
    label: { zh: "我的學習", pinyin: "Wǒ de xuéxí", en: "Progress" },
  },
  {
    id: "picture-talk",
    icon: "image",
    label: { zh: "看圖說話", pinyin: "Kàn tú shuō huà", en: "Picture talk" },
  },
];

function LegacyStudentWorkspacePage({
  view,
  onViewChange,
  onAddRecord,
  initialTopicId,
  initialImageIndex,
  helpRequests,
  onRaiseHand,
  storyTopics,
  describeTopics,
  audioRecords,
  onSessionActiveChange,
  isInPracticeSession,
}: StudentWorkspacePageProps) {
  const availableViews = WORKSPACE_VIEWS.filter(
    (item) => item.id !== "picture-talk" || describeTopics.length > 0,
  );
  const [practiceStarted, setPracticeStarted] = useState(isInPracticeSession);

  useEffect(() => {
    setPracticeStarted(isInPracticeSession);
  }, [isInPracticeSession]);

  const selectView = (nextView: StudentWorkspaceView) => {
    if (nextView === view) return;
    onViewChange(nextView);
  };

  const renderView = () => {
    if (view === "progress") {
      return (
        <MyStoriesPage
          records={audioRecords}
          onBrowsePractice={() => selectView("practice")}
          helpRequests={helpRequests}
          onRaiseHand={onRaiseHand}
          publishedTopics={storyTopics}
        />
      );
    }

    if (view === "picture-talk") {
      return <ImageNarrationPage publishedTopics={describeTopics} />;
    }

    return (
      <CreateStoryPage
        key={initialTopicId ? `${initialTopicId}:${initialImageIndex ?? 0}` : "browse"}
        onAddRecord={onAddRecord}
        initialTopicId={initialTopicId}
        initialImageIndex={initialImageIndex}
        helpRequests={helpRequests}
        onRaiseHand={onRaiseHand}
        publishedTopics={storyTopics}
        onSessionActiveChange={(active) => {
          setPracticeStarted(active);
          onSessionActiveChange(active);
        }}
      />
    );
  };

  return (
    <main className={`student-workspace ${practiceStarted ? "is-practicing" : ""}`}>
      {!practiceStarted && (
        <header className="student-workspace-header">
          <div className="student-workspace-header-copy">
            <h1>
              <span lang="zh-Hant">我的學習</span>
            </h1>
            <div className="student-workspace-title-meta">
              <span className="student-workspace-pinyin">Wǒ de xuéxí</span>
              <span
                className="student-workspace-identity"
                aria-label={`Student username: ${getStudentName()}`}
              >
                <span className="student-workspace-identity-avatar" aria-hidden="true">
                  <StudentIcon name="user" size={19} />
                </span>
                <span className="student-workspace-identity-copy">
                  <span className="student-workspace-identity-label">
                    <span lang="zh-Hant">學生帳號</span>
                    <span aria-hidden="true"> · </span>
                    <span>Username</span>
                  </span>
                  <strong className="student-workspace-identity-name">{getStudentName()}</strong>
                </span>
              </span>
            </div>
            <p className="student-workspace-intro">
              <BiText
                zh="選一個方向，慢慢練習。"
                pinyin="Xuǎn yí ge fāngxiàng, mànmàn liànxí."
                en="Choose a path and keep learning, little by little."
              />
            </p>
          </div>
          <div className="student-workspace-mark" aria-hidden="true">
            <span>慢</span>
            <span>慢</span>
          </div>
        </header>
      )}

      {!practiceStarted && (
        <nav
          className={`student-workspace-tabs student-workspace-tabs-count-${availableViews.length}`}
          aria-label="Student learning areas"
          role="tablist"
        >
          {availableViews.map((item) => (
            <button
              key={item.id}
              id={`student-workspace-tab-${item.id}`}
              type="button"
              role="tab"
              aria-selected={view === item.id}
              aria-controls="student-workspace-panel"
              className={`student-workspace-tab ${view === item.id ? "active" : ""}`}
              onClick={() => selectView(item.id)}
            >
              <span className="student-workspace-tab-icon"><StudentIcon name={item.icon} size={23} /></span>
              <span className="student-workspace-tab-copy">
                <BiLabel {...item.label} />
              </span>
              <span className="student-workspace-tab-arrow" aria-hidden="true">→</span>
            </button>
          ))}
        </nav>
      )}

      <section
        id="student-workspace-panel"
        className="student-workspace-content"
        role="tabpanel"
        tabIndex={-1}
        aria-labelledby={`student-workspace-tab-${view}`}
        aria-live="polite"
      >
        {renderView()}
      </section>
    </main>
  );
}

export default function StudentWorkspacePage(props: StudentWorkspacePageProps) {
  if (studentWorkspaceShellEnabled) {
    return <StudentWorkspaceShell {...props} />;
  }
  return <LegacyStudentWorkspacePage {...props} />;
}
