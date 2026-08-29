import { useEffect, useState } from "react";
import CreateStoryPage from "../../pages/CreateStoryPage";
import MyStoriesPage from "../../pages/MyStoriesPage";
import { getStudentName } from "../../utils/studentSession";
import type { StudentWorkspacePageProps } from "../../pages/StudentWorkspacePage";
import type { StudentWorkspaceView } from "../../pages/StudentWorkspacePage";
import StudentSidebar from "./StudentSidebar";
import { loadBestLocalStars } from "../../utils/quizTiers";
import { topicHasQuiz } from "../../utils/topicQuiz";
import "../../components/BiLabel.css";
import "../../pages/StudentWorkspacePage.css";
import "./StudentWorkspaceV2.css";

const WORKSPACE_VIEWS = [
  { id: "practice" as const, icon: "image" as const, label: { zh: "課程", pinyin: "Kèchéng", en: "Practice" } },
  { id: "progress" as const, icon: "chart" as const, label: { zh: "我的學習", pinyin: "Wǒ de xuéxí", en: "Progress" } },
];

export default function StudentWorkspaceShell(props: StudentWorkspacePageProps) {
  const {
    view,
    onViewChange,
    onAddRecord,
    initialTopicId,
    initialImageIndex,
    initialStartAtQuiz,
    initialTargetKey,
    helpRequests,
    onRaiseHand,
    storyTopics,
    audioRecords,
    onSessionActiveChange,
    isInPracticeSession,
    onLogout,
  } = props;
  const [practiceStarted, setPracticeStarted] = useState(isInPracticeSession);

  useEffect(() => setPracticeStarted(isInPracticeSession), [isInPracticeSession]);

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
    return (
      <CreateStoryPage
        key={initialTopicId ? `${initialTopicId}:${initialImageIndex ?? 0}:${initialStartAtQuiz ? "quiz" : "practice"}:${initialTargetKey ?? 0}` : "browse"}
        onAddRecord={onAddRecord}
        initialTopicId={initialTopicId}
        initialImageIndex={initialImageIndex}
        initialStartAtQuiz={initialStartAtQuiz}
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

  const activeLabel = WORKSPACE_VIEWS.find((item) => item.id === view)?.label;

  // Same source and shape MyStoriesPage's "總星星 Total stars" card uses, so
  // the rail and that card can never disagree.
  const quizTopics = (storyTopics ?? []).filter((topic) => topicHasQuiz(topic));
  const totalStars = quizTopics.reduce(
    (sum, topic) => sum + loadBestLocalStars(topic.id),
    0,
  );
  const maxStars = quizTopics.length * 3;

  return (
    <main className={`student-workspace student-workspace-v2 ${practiceStarted ? "is-practicing" : ""}`}>
      {/* One rail for all of student mode. It stays mounted through a
          practice session and lends its middle to the story, rather than
          unmounting so StoryRecorder can open a second rail beside it. */}
      <StudentSidebar
        views={WORKSPACE_VIEWS}
        activeView={view}
        onChange={selectView}
        studentName={getStudentName()}
        onLogout={onLogout}
        totalStars={totalStars}
        maxStars={maxStars}
        sessionActive={practiceStarted}
      />
      <section
        id="student-workspace-panel"
        className="student-workspace-content student-workspace-content-v2"
        tabIndex={-1}
        aria-label={activeLabel ? `${activeLabel.zh} ${activeLabel.en}` : undefined}
        aria-live="polite"
      >
        {renderView()}
      </section>
    </main>
  );
}
