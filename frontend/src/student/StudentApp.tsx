import { useState } from "react";
import type { NewAudioRecord } from "../components/story-recorder/StoryRecorder";
import type { Topic } from "../components/content/topic-selector/types";
import { normalizeConversationTurns } from "../components/story-recorder/StoryRecorder";
import { topicStoryId } from "../utils/lessonGroups";
import StudentShell from "./shell/StudentShell";
import type { StudentPhase, StudentTopSection } from "./shell/StudentSidebar";
import StudyPage, { type StudyTopicStatus } from "./study/StudyPage";
import VocabularyPreviewPage from "./vocabulary/VocabularyPreviewPage";
import VocabularyQuizPage from "./vocabulary/VocabularyQuizPage";
import StorySpeakingPage from "./speaking/StorySpeakingPage";
import ConversationPage from "./conversation/ConversationPage";
import ProgressPage from "./progress/ProgressPage";
import { loadSubmittedStoryIds } from "../utils/storyLevelProgress";

interface StudentAppProps {
  studentName: string;
  topics: Topic[];
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  onLogout: () => void;
}

/**
 * Top-level Student Mode composition. Owns which top-level section
 * (Study/Progress) and, inside Study, which lesson + pedagogical phase is
 * active. Delegates all quiz/speaking/conversation/feedback state to the
 * page it currently renders — matches the StudentShell contract (shell
 * knows nothing about that state).
 */
export default function StudentApp({ studentName, topics, onAddRecord, onLogout }: StudentAppProps) {
  const [section, setSection] = useState<StudentTopSection>("study");
  const [activeTopic, setActiveTopic] = useState<Topic | null>(null);
  const [phase, setPhase] = useState<StudentPhase>("vocab-preview");
  const [sceneIndex, setSceneIndex] = useState(0);

  const openTopic = (topic: Topic) => {
    setActiveTopic(topic);
    setSceneIndex(0);
    setPhase("vocab-preview");
  };

  const backToStudy = () => {
    setActiveTopic(null);
  };

  const conversationTurns = activeTopic ? normalizeConversationTurns(activeTopic.conversationTurns) : null;

  const statusByStoryId: Record<string, StudyTopicStatus> = {};
  if (section === "study" && !activeTopic) {
    const submitted = loadSubmittedStoryIds();
    for (const topic of topics) {
      const id = topicStoryId(topic);
      statusByStoryId[id] = { status: submitted.has(id) ? "completed" : "not-started" };
    }
  }

  let body: React.ReactNode;

  if (section === "progress") {
    body = <ProgressPage topics={topics} />;
  } else if (!activeTopic) {
    body = <StudyPage topics={topics} statusByStoryId={statusByStoryId} onOpenTopic={openTopic} />;
  } else if (phase === "vocab-preview") {
    body = (
      <VocabularyPreviewPage
        topic={activeTopic}
        lessonLabel={activeTopic.name}
        onStartSpeaking={() => setPhase("vocab-quiz")}
      />
    );
  } else if (phase === "vocab-quiz") {
    body = (
      <VocabularyQuizPage
        topic={activeTopic}
        lessonLabel={activeTopic.name}
        onFinished={() => setPhase("story-speaking")}
      />
    );
  } else if (phase === "story-speaking") {
    body = (
      <StorySpeakingPage
        topic={activeTopic}
        selectedImageIndex={sceneIndex}
        onImageIndexChange={setSceneIndex}
        onAddRecord={onAddRecord}
        onDone={() => setPhase(conversationTurns ? "conversation" : "completion")}
      />
    );
  } else if (phase === "conversation" && conversationTurns) {
    body = (
      <ConversationPage
        topic={activeTopic}
        turns={conversationTurns}
        onAddRecord={onAddRecord}
        onDone={() => setPhase("completion")}
        onBack={backToStudy}
      />
    );
  } else {
    // Completion screen design is pending the user's own addition to
    // .superdesign/design-system.md — this stub keeps the phase reachable
    // without inventing a visual for it.
    body = (
      <div className="sa-page-container">
        <p>Lesson complete. (Completion screen design pending.)</p>
      </div>
    );
  }

  return (
    <StudentShell
      studentName={studentName}
      activeSection={section}
      activePhase={activeTopic ? phase : null}
      onNavigateSection={(next) => {
        setSection(next);
        if (next === "study") setActiveTopic(null);
      }}
      onNavigatePhase={activeTopic ? setPhase : undefined}
      onLogout={onLogout}
    >
      {body}
    </StudentShell>
  );
}
