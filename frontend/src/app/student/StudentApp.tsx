import { useEffect, useState } from "react";
import type { NewAudioRecord } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "@entities/topic";
import { normalizeConversationTurns } from "../../components/story-recorder/StoryRecorder";
import { canUseDatabase, createStorySubmission, type SceneSubmission } from "../../services/database";
import { getVocabularyProgression, type VocabularyProgression } from "../../services/api/quiz-analytics";
import { computeStudyRowStatuses, nextTopicInSequence, topicStoryId } from "../../utils/lessonGroups";
import { computeQuizStarsSummary, loadLocalStars, PRACTICE_UNLOCK_STARS, topicHasQuiz } from "@entities/vocabulary";
import { getStudentId } from "../../utils/studentSession";
import { loadPhaseFlags } from "@shared/lib/studyProgressFlags";
import StudentShell from "./shell/StudentShell";
import { PHASE_ORDER, type StudentPhase, type StudentTopSection } from "./shell/StudentSidebar";
import StudyPage, { type StudyTopicStatus } from "../../features/study/StudyPage";
import VocabularyPreviewPage from "../../features/vocabulary/VocabularyPreviewPage";
import VocabularyQuizPage from "../../features/vocabulary/VocabularyQuizPage";
import StorySpeakingPage from "../../features/speaking/StorySpeakingPage";
import ConversationPage from "../../features/conversation/ConversationPage";
import SubmitStoryPage from "../../features/submit/SubmitStoryPage";
import CompletionPage from "../../features/completion/CompletionPage";
import ProgressPage from "../../features/progress/ProgressPage";
import PlacementPage from "../../features/placement/PlacementPage";
import StudentSettingsPage from "../../features/settings/StudentSettingsPage";
import { StudentSettingsProvider } from "./StudentSettingsContext";
import { loadSubmittedStoryIds, markStoryLevelSubmitted } from "../../utils/storyLevelProgress";

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
  // The furthest phase reached gates preview, quiz and submission in the
  // sidebar. Speaking and Conversation use their shared vocabulary gate.
  // Only ever moves forward; see advancePhase.
  const [furthestPhase, setFurthestPhase] = useState<StudentPhase>("vocab-preview");
  const [sceneIndex, setSceneIndex] = useState(0);
  // Every scene/turn's latest submission for the topic currently in
  // progress, keyed so a re-recorded attempt replaces its own entry rather
  // than duplicating it — assembled into one StorySubmission when the
  // student turns work in on the Submit screen.
  const [sceneSubmissions, setSceneSubmissions] = useState<Record<string, SceneSubmission>>({});
  const [completedPractice, setCompletedPractice] = useState<"speaking" | "conversation">("speaking");
  const [activeProgression, setActiveProgression] = useState<VocabularyProgression | null>(null);
  const [progressionRefresh, setProgressionRefresh] = useState(0);

  const openTopic = (topic: Topic) => {
    const hasQuiz = topicHasQuiz(topic);
    const quizAlreadyPassed = hasQuiz && loadLocalStars(topicStoryId(topic)) >= PRACTICE_UNLOCK_STARS;
    setActiveTopic(topic);
    setActiveProgression(null);
    setSceneIndex(0);
    setSceneSubmissions({});
    setCompletedPractice("speaking");
    setPhase("vocab-preview");
    // A previously earned three-star quiz is a completed gate when the
    // learner reopens the lesson; don't force the quiz just to re-enter
    // either practice path.
    setFurthestPhase(quizAlreadyPassed ? "story-speaking" : "vocab-preview");
  };

  const backToStudy = () => {
    setActiveTopic(null);
  };

  useEffect(() => {
    setActiveProgression(null);
    const studentId = getStudentId();
    const storyId = activeTopic?.sourceStory?.id ?? activeTopic?.id;
    if (!activeTopic || !studentId || !storyId || !canUseDatabase()) return;
    let cancelled = false;
    getVocabularyProgression(storyId, studentId)
      .then((progression) => {
        if (cancelled) return;
        setActiveProgression(progression);
        if (progression.quizStars >= PRACTICE_UNLOCK_STARS) {
          setFurthestPhase((prev) => (
            PHASE_ORDER.indexOf(prev) >= PHASE_ORDER.indexOf("story-speaking")
              ? prev
              : "story-speaking"
          ));
        }
      })
      .catch(() => { /* local mirror remains the offline fallback */ });
    return () => { cancelled = true; };
  }, [activeTopic, progressionRefresh]);

  const refreshProgression = () => {
    // Re-read the completed quiz's local mirror immediately, then refresh
    // the server result through the effect so older requests are cancelled.
    setActiveProgression(null);
    setProgressionRefresh((prev) => prev + 1);
  };

  // The only path that should ever move `phase` forward on its own (a
  // page's onDone/onFinished callback deciding its own work is actually
  // done) — bumps the watermark alongside it, never backward.
  const advancePhase = (next: StudentPhase) => {
    setPhase(next);
    setFurthestPhase((prev) => (PHASE_ORDER.indexOf(next) > PHASE_ORDER.indexOf(prev) ? next : prev));
  };

  const handleSceneSubmission = (key: string, submission: SceneSubmission) => {
    setSceneSubmissions((prev) => ({ ...prev, [key]: submission }));
  };

  // The one deliberate "hand it in" gesture (SubmitStoryPage) — only once
  // this resolves does completion actually record: a real backend failure
  // leaves the student on that screen to retry rather than silently
  // advancing past an unsubmitted story.
  const handleSubmitStory = async () => {
    if (!activeTopic) return;
    if (canUseDatabase()) {
      await createStorySubmission({
        id: `submission-${Date.now()}`,
        storyId: activeTopic.id,
        storyTitle: activeTopic.name,
        studentName,
        studentId: getStudentId(),
        submittedAt: new Date().toISOString(),
        scenes: Object.values(sceneSubmissions),
      });
    }
    markStoryLevelSubmitted(topicStoryId(activeTopic));
    advancePhase("completion");
  };

  const conversationTurns = activeTopic ? normalizeConversationTurns(activeTopic.conversationTurns) : null;
  // Conversation is a first-class lesson phase, like Story Speaking. Keep it
  // visible even when a story has not received teacher-authored turns yet;
  // ConversationPage renders a useful empty state for that case instead of
  // silently routing the learner to Submit.
  const conversationContentAvailable = Boolean(conversationTurns) && (activeProgression?.conversationAvailable ?? true);
  const availableConversationTurns = conversationContentAvailable ? (conversationTurns ?? []) : [];

  const statusByStoryId: Record<string, StudyTopicStatus> = {};
  if (section === "study" && !activeTopic) {
    const rowStatuses = computeStudyRowStatuses(topics, loadSubmittedStoryIds());
    for (const [id, status] of Object.entries(rowStatuses)) {
      statusByStoryId[id] = {
        status,
        ...(status === "in-progress" ? { phases: loadPhaseFlags(id) } : {}),
      };
    }
  }

  // Not memoized: stars change via localStorage writes (quiz completion)
  // that don't change the `topics` prop, so a [topics]-keyed memo would
  // go stale.
  const { quizStars: totalQuizStars, maxQuizStars } = computeQuizStarsSummary(topics);
  const currentLessonTitle = !activeTopic
    ? (() => {
        const current = Object.entries(statusByStoryId).find(([, entry]) => entry.status === "in-progress")
          ?? Object.entries(statusByStoryId).find(([, entry]) => entry.status === "not-started");
        const topic = current ? topics.find((candidate) => topicStoryId(candidate) === current[0]) : undefined;
        return topic?.name;
      })()
    : activeTopic.name;

  // Both practice modes are peers behind the same vocabulary gate.
  // Content availability controls the conversation page's empty state,
  // while earned stars alone determine access to both modes.
  const activeStoryId = activeTopic?.sourceStory?.id ?? activeTopic?.id;
  const activeStars = activeProgression?.quizStars ?? (activeStoryId ? loadLocalStars(activeStoryId) : 0);
  const practiceChoicesUnlocked = activeTopic
    ? (!topicHasQuiz(activeTopic) || activeStars >= PRACTICE_UNLOCK_STARS)
    : false;

  const finishVocabularyQuiz = () => {
    refreshProgression();
    advancePhase("story-speaking");
  };

  let body: React.ReactNode;

  if (section === "settings") {
    body = <StudentSettingsPage onRequireRelogin={onLogout} />;
  } else if (section === "progress") {
    body = <ProgressPage topics={topics} />;
  } else if (section === "placement") {
    body = <PlacementPage live />;
  } else if (!activeTopic) {
    body = <StudyPage topics={topics} statusByStoryId={statusByStoryId} onOpenTopic={openTopic} />;
  } else if (phase === "vocab-preview") {
    body = (
      <VocabularyPreviewPage
        topic={activeTopic}
        lessonLabel={activeTopic.name}
        onStartSpeaking={() => advancePhase(topicHasQuiz(activeTopic) ? "vocab-quiz" : "story-speaking")}
      />
    );
  } else if (phase === "vocab-quiz") {
    body = (
      <VocabularyQuizPage
        topic={activeTopic}
        lessonLabel={activeTopic.name}
        onFinished={finishVocabularyQuiz}
        onStartPractice={(practice) => {
          setCompletedPractice(practice === "conversation" ? "conversation" : "speaking");
          refreshProgression();
          advancePhase(practice);
        }}
      />
    );
  } else if (phase === "story-speaking") {
    body = (
      <StorySpeakingPage
        topic={activeTopic}
        selectedImageIndex={sceneIndex}
        onImageIndexChange={setSceneIndex}
        onAddRecord={onAddRecord}
        onSceneSubmission={handleSceneSubmission}
        onDone={() => {
          setCompletedPractice("speaking");
          advancePhase("submit");
        }}
      />
    );
  } else if (phase === "conversation") {
    body = (
      <ConversationPage
        topic={activeTopic}
        turns={availableConversationTurns}
        onAddRecord={onAddRecord}
        onSceneSubmission={handleSceneSubmission}
        onDone={() => {
          setCompletedPractice("conversation");
          advancePhase("submit");
        }}
        onBack={backToStudy}
      />
    );
  } else if (phase === "submit") {
    body = (
      <SubmitStoryPage
        topic={activeTopic}
        sceneCount={activeTopic.images.length}
        hasConversation={conversationContentAvailable}
        completedPractice={completedPractice}
        onSubmit={handleSubmitStory}
      />
    );
  } else {
    const submittedIds = loadSubmittedStoryIds();
    const rowStatuses = computeStudyRowStatuses(topics, submittedIds);
    const overallCompleted = Object.values(rowStatuses).filter((status) => status === "completed").length;
    const nextTopic = nextTopicInSequence(topics, activeTopic);
    const nextTopicUnlocked = nextTopic ? rowStatuses[topicStoryId(nextTopic)] !== "locked" : false;
    body = (
      <CompletionPage
        topic={activeTopic}
        sceneCount={activeTopic.images.length}
        hasConversation={conversationContentAvailable}
        quizStars={topicHasQuiz(activeTopic) ? activeStars : null}
        overallCompleted={overallCompleted}
        overallTotal={topics.length}
        nextTopic={nextTopic}
        nextTopicUnlocked={nextTopicUnlocked}
        onStartNext={openTopic}
        onBackToStudy={backToStudy}
      />
    );
  }

  return (
    <StudentSettingsProvider>
      <StudentShell
        studentName={studentName}
        currentLessonTitle={currentLessonTitle}
        activeSection={section}
        activePhase={section === "study" && activeTopic ? phase : null}
        quizStars={totalQuizStars}
        maxQuizStars={maxQuizStars}
        furthestPhase={furthestPhase}
        practiceChoicesUnlocked={practiceChoicesUnlocked}
        onNavigateSection={(next) => {
          const cameFromSettings = section === "settings";
          setSection(next);
          if (next === "study" && !cameFromSettings) setActiveTopic(null);
        }}
        onNavigatePhase={
          activeTopic
            ? (next) => {
                const reachable = next === "story-speaking" || next === "conversation"
                  ? practiceChoicesUnlocked
                  : PHASE_ORDER.indexOf(next) <= PHASE_ORDER.indexOf(furthestPhase);
                if (reachable) {
                  if (next === "story-speaking" || next === "conversation") {
                    setCompletedPractice(next === "conversation" ? "conversation" : "speaking");
                  }
                  setPhase(next);
                }
              }
            : undefined
        }
        onLogout={onLogout}
      >
        {body}
      </StudentShell>
    </StudentSettingsProvider>
  );
}
