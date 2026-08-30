import CreateStoryPage from "../../pages/CreateStoryPage";
import MyStoriesPage from "../../pages/MyStoriesPage";
import { getStudentName } from "../../utils/studentSession";
import type { StudentWorkspacePageProps } from "../../pages/StudentWorkspacePage";
import type { StudentWorkspaceView } from "../../pages/StudentWorkspacePage";
import StudentModeFrame, { STUDENT_WORKSPACE_VIEWS } from "./StudentModeFrame";
import { loadBestLocalStars } from "../../utils/quizTiers";
import { topicHasQuiz } from "../../utils/topicQuiz";
import "../../components/BiLabel.css";
import "../../pages/StudentWorkspacePage.css";
import "./StudentWorkspaceV2.css";

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
    onLogout,
  } = props;
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
        onSessionActiveChange={onSessionActiveChange}
      />
    );
  };

  const activeLabel = STUDENT_WORKSPACE_VIEWS.find((item) => item.id === view)?.label;

  // Same source and shape MyStoriesPage's "總星星 Total stars" card uses, so
  // the rail and that card can never disagree.
  const quizTopics = (storyTopics ?? []).filter((topic) => topicHasQuiz(topic));
  const totalStars = quizTopics.reduce(
    (sum, topic) => sum + loadBestLocalStars(topic.id),
    0,
  );
  const maxStars = quizTopics.length * 3;

  return (
    <StudentModeFrame
      activeView={view}
      onChange={selectView}
      studentName={getStudentName()}
      onLogout={onLogout}
      totalStars={totalStars}
      maxStars={maxStars}
      ariaLabel={activeLabel ? `${activeLabel.zh} ${activeLabel.en}` : undefined}
    >
      {renderView()}
    </StudentModeFrame>
  );
}
