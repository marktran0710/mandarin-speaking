import { useEffect, useMemo, useState } from "react";
import CreateStoryPage from "../../pages/CreateStoryPage";
import ImageNarrationPage from "../../pages/ImageNarrationPage";
import MyStoriesPage from "../../pages/MyStoriesPage";
import { getStudentName } from "../../utils/studentSession";
import { isAdminSession } from "../../utils/studentSession";
import { loadCompletedVocabQuizzes } from "../../utils/vocabQuizStorage";
import { loadSubmittedStoryIds } from "../../utils/storyLevelProgress";
import { topicHasQuiz, topicQuizEntries } from "../../utils/topicQuiz";
import type { StudentWorkspacePageProps } from "../../pages/StudentWorkspacePage";
import type { StudentWorkspaceView } from "../../pages/StudentWorkspacePage";
import StudentWorkspaceHeader from "./StudentWorkspaceHeader";
import WorkspaceAreaTabs from "./WorkspaceAreaTabs";
import LearningOverview from "./LearningOverview";
import type { LearningSummary, QuizGateState, WorkspaceTopicSummary } from "../../types/studentWorkspace";
import "../../components/BiLabel.css";
import "../../pages/StudentWorkspacePage.css";
import "./StudentWorkspaceV2.css";

const WORKSPACE_VIEWS = [
  { id: "practice" as const, icon: "image" as const, label: { zh: "課程", pinyin: "Kèchéng", en: "Practice" } },
  { id: "progress" as const, icon: "chart" as const, label: { zh: "我的學習", pinyin: "Wǒ de xuéxí", en: "Progress" } },
  { id: "picture-talk" as const, icon: "image" as const, label: { zh: "看圖說話", pinyin: "Kàn tú shuō huà", en: "Picture talk" } },
];

function buildGate(topic: StudentWorkspacePageProps["storyTopics"][number] | undefined): QuizGateState {
  if (!topic) return { status: "unavailable", reason: "No activities are available yet." };
  if (!topicHasQuiz(topic)) return { status: "completed" };
  if (isAdminSession() || loadCompletedVocabQuizzes()[topic.id] === true) return { status: "completed" };
  return {
    status: "required",
    quizId: topic.id,
    reason: "Finish the vocabulary quiz before speaking practice.",
  };
}

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
    describeTopics,
    audioRecords,
    onSessionActiveChange,
    isInPracticeSession,
    onStartActivity,
  } = props;
  const [practiceStarted, setPracticeStarted] = useState(isInPracticeSession);

  useEffect(() => setPracticeStarted(isInPracticeSession), [isInPracticeSession]);

  const availableViews = useMemo(
    () => WORKSPACE_VIEWS.filter((item) => item.id !== "picture-talk" || describeTopics.length > 0),
    [describeTopics.length],
  );
  const activeTopic = storyTopics.find((topic) => topic.id === initialTopicId) ?? storyTopics[0];
  const topicSummary: WorkspaceTopicSummary | undefined = activeTopic
    ? {
        topic: activeTopic,
        quizGate: buildGate(activeTopic),
        quizWordCount: topicQuizEntries(activeTopic).length,
        recordedSceneCount: audioRecords.filter((record) => record.topicId === activeTopic.id).length,
      }
    : undefined;
  const submittedIds = loadSubmittedStoryIds();
  const completedActivities = storyTopics.filter((topic) => submittedIds.has(topic.id)).length;
  const today = new Date().toISOString().slice(0, 10);
  const todayRecords = audioRecords.filter((record) => record.timestamp.slice(0, 10) === today).length;
  const summary: LearningSummary = {
    lessonProgress: storyTopics.length ? (completedActivities / storyTopics.length) * 100 : 0,
    wordsToPractice: topicSummary?.quizWordCount ?? 0,
    todayGoal: { completed: Math.min(todayRecords, 3), total: 3 },
    continueTarget: topicSummary && topicSummary.recordedSceneCount > 0
      ? {
          storyId: topicSummary.topic.id,
          label: topicSummary.topic.name,
          progress: Math.min(100, (topicSummary.recordedSceneCount / Math.max(1, topicSummary.topic.images.length)) * 100),
        }
      : undefined,
    quizGate: topicSummary?.quizGate,
  };

  const selectView = (nextView: StudentWorkspaceView) => {
    if (nextView === view) return;
    onViewChange(nextView);
  };

  const startActivity = () => {
    const gate = topicSummary?.quizGate;
    if (activeTopic && onStartActivity) {
      onStartActivity(activeTopic.id, gate?.status === "required");
      return;
    }
    selectView("practice");
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
    if (view === "picture-talk") return <ImageNarrationPage publishedTopics={describeTopics} />;
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

  return (
    <main className={`student-workspace student-workspace-v2 ${practiceStarted ? "is-practicing" : ""}`}>
      {!practiceStarted && <StudentWorkspaceHeader username={getStudentName()} />}
      {!practiceStarted && (
        <WorkspaceAreaTabs views={availableViews} activeView={view} onChange={selectView} />
      )}
      {!practiceStarted && (
        <LearningOverview
          summary={summary}
          topicSummary={topicSummary}
          onStartActivity={startActivity}
          onOpenProgress={() => selectView("progress")}
          onOpenPractice={() => selectView("practice")}
        />
      )}
      <section
        id="student-workspace-panel"
        className="student-workspace-content student-workspace-content-v2"
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
