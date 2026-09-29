import { useEffect, useRef, useState } from "react";
import type { NewAudioRecord } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "@entities/topic";
import { normalizeConversationTurns } from "../../components/story-recorder/StoryRecorder";
import { canUseDatabase, createStorySubmission, listSpeakingProgress, type SceneSubmission } from "../../services/database";
import { getVocabularyProgression, type VocabularyProgression } from "../../services/api/quiz-analytics";
import { computeStudyRowStatuses, nextTopicInSequence, topicStoryId } from "../../utils/lessonGroups";
import { computeQuizStarsSummary, loadLocalStars, PRACTICE_UNLOCK_STARS, topicHasQuiz } from "@entities/vocabulary";
import { getStudentId, isAdminSession } from "../../utils/studentSession";
import { loadPhaseFlags, markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { resetLocalVocabularyProgress, syncServerVocabularyProgress } from "../../utils/serverVocabularyProgress";
import StudentShell from "./shell/StudentShell";
import type { StudentPhase, StudentTopSection } from "./shell/StudentSidebar";
import {
  computeLessonSteps,
  conversationPathDone,
  countRecorded,
  firstUnfinishedPhase,
  sceneSubmissionsFromProgress,
  scenesForSubmission,
  speakingPathDone,
  type LessonProgressInput,
} from "./lessonSteps";
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
import { StudentSettingsProvider } from "@features/settings/StudentSettingsContext";
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
  const [sceneIndex, setSceneIndex] = useState(0);
  // Every scene/turn's latest submission for the open topic, keyed
  // `speaking:<scene>` / `conversation:<turn>` so a re-recorded attempt
  // replaces its own entry. Seeded from the server's saved speaking progress
  // when the lesson opens, so a refresh doesn't lose finished work.
  const [sceneSubmissions, setSceneSubmissions] = useState<Record<string, SceneSubmission>>({});
  const [activeProgression, setActiveProgression] = useState<VocabularyProgression | null>(null);
  const [previewCompletedFor, setPreviewCompletedFor] = useState<string | null>(null);
  // Bumped whenever saved progress changes outside React state (quiz rounds
  // write localStorage, pages write the phase flags) so derived gates re-read.
  const [progressVersion, setProgressVersion] = useState(0);
  const bumpProgress = () => setProgressVersion((version) => version + 1);
  // True until the learner navigates in the reopened lesson: once saved
  // progress finishes loading we may move them to the first unfinished step,
  // but never yank them away from a step they picked themselves.
  const autoLandingRef = useRef(false);

  const openTopic = (topic: Topic) => {
    setActiveTopic(topic);
    setActiveProgression(null);
    setSceneIndex(0);
    setSceneSubmissions({});
    setPreviewCompletedFor(null);
    autoLandingRef.current = true;
    setPhase(firstUnfinishedPhase(progressInputFor(topic, {}, null)));
  };

  const backToStudy = () => {
    setActiveTopic(null);
  };

  useEffect(() => {
    if (activeTopic) {
      const latest = topics.find((topic) => topicStoryId(topic) === topicStoryId(activeTopic));
      const currentVersion = activeTopic.sourceStory?.vocabularyVersion ?? activeTopic.vocabularyVersion;
      const latestVersion = latest?.sourceStory?.vocabularyVersion ?? latest?.vocabularyVersion;
      if (latest && latestVersion !== undefined && latestVersion !== currentVersion) {
        resetLocalVocabularyProgress(topicStoryId(latest));
        openTopic(latest);
        return;
      }
    }
    setActiveProgression(null);
    const studentId = getStudentId();
    const storyId = activeTopic?.sourceStory?.id ?? activeTopic?.id;
    if (!activeTopic || !studentId || !storyId || !canUseDatabase()) return;
    let cancelled = false;
    const progressionRequest = getVocabularyProgression(storyId, studentId)
      .then((progression) => {
        if (!cancelled) {
          syncServerVocabularyProgress(progression);
          setActiveProgression(progression);
        }
        return progression;
      })
      .catch(() => null /* local mirror remains the offline fallback */);
    const recordsRequest = listSpeakingProgress(studentId, activeTopic.id)
      .then((rows) => {
        const restored = sceneSubmissionsFromProgress(rows);
        // Anything recorded in this tab while the request was in flight wins.
        if (!cancelled) setSceneSubmissions((current) => ({ ...restored, ...current }));
        return restored;
      })
      .catch(() => ({} as Record<string, SceneSubmission>));
    void Promise.all([progressionRequest, recordsRequest]).then(([progression, restored]) => {
      if (cancelled || !autoLandingRef.current) return;
      setPhase(firstUnfinishedPhase(progressInputFor(activeTopic, restored, progression)));
    });
    return () => { cancelled = true; };
    // progressInputFor reads only the arguments and saved storage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTopic, topics]);

  const conversationTurnsFor = (topic: Topic) => normalizeConversationTurns(topic.conversationTurns);
  const conversationAvailableFor = (topic: Topic, progression: VocabularyProgression | null) =>
    Boolean(conversationTurnsFor(topic)) && (progression?.conversationAvailable ?? true);

  // Every lesson gate derives from saved data (quiz attempts, recordings,
  // submission status, saved phase flags) — see lessonSteps.ts.
  function progressInputFor(
    topic: Topic,
    submissions: Record<string, SceneSubmission>,
    progression: VocabularyProgression | null,
  ): LessonProgressInput {
    const storyId = topicStoryId(topic);
    const flags = loadPhaseFlags(storyId);
    const hasQuiz = topicHasQuiz(topic);
    const roundsDone = Math.max(progression?.quizStars ?? 0, loadLocalStars(topic.sourceStory?.id ?? topic.id));
    const sceneIndexes = topic.images.map((_, index) => index);
    const conversationAvailable = conversationAvailableFor(topic, progression);
    const studentTurnIndexes = conversationAvailable
      ? (conversationTurnsFor(topic) ?? []).flatMap((turn, index) => (turn.speaker === "student" ? [index] : []))
      : [];
    // A finished path's saved flag stands in for recordings the server could
    // not return (offline mode, or a failed progress read).
    const scenesRecorded = flags.speaking ? sceneIndexes.length : countRecorded(submissions, "speaking", sceneIndexes);
    const turnsRecorded = flags.conversation
      ? studentTurnIndexes.length
      : countRecorded(submissions, "conversation", studentTurnIndexes);
    return {
      hasQuiz,
      previewDone: flags.vocab || previewCompletedFor === storyId,
      quizDone: !hasQuiz || isAdminSession() || roundsDone >= PRACTICE_UNLOCK_STARS,
      sceneCount: sceneIndexes.length,
      scenesRecorded,
      turnCount: studentTurnIndexes.length,
      turnsRecorded,
      conversationAvailable,
      submitted: loadSubmittedStoryIds().has(storyId),
    };
  }

  const handleSceneSubmission = (key: string, submission: SceneSubmission) => {
    setSceneSubmissions((prev) => ({ ...prev, [key]: submission }));
  };

  const navigateTo = (next: StudentPhase) => {
    autoLandingRef.current = false;
    setPhase(next);
  };

  // Read on every render (not memoized): quiz rounds and page flags update
  // localStorage, and progressVersion forces the re-render that picks it up.
  void progressVersion;
  const progressInput = activeTopic ? progressInputFor(activeTopic, sceneSubmissions, activeProgression) : null;
  const computedSteps = progressInput ? computeLessonSteps(progressInput) : undefined;
  // Admin previews every step without doing the work first.
  const lessonSteps = computedSteps && isAdminSession()
    ? (Object.fromEntries(Object.entries(computedSteps).map(([phase, step]) => [phase, { ...step, unlocked: true }])) as typeof computedSteps)
    : computedSteps;
  const speakingDone = progressInput ? speakingPathDone(progressInput) : false;
  const conversationDone = progressInput ? conversationPathDone(progressInput) : false;

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
        scenes: scenesForSubmission(sceneSubmissions, { speaking: speakingDone, conversation: conversationDone }),
      });
    }
    markStoryLevelSubmitted(topicStoryId(activeTopic));
    bumpProgress();
    navigateTo("completion");
  };

  const conversationTurns = activeTopic ? conversationTurnsFor(activeTopic) : null;
  // Conversation is a first-class lesson phase, like Story Speaking. Keep it
  // visible even when a story has not received teacher-authored turns yet;
  // ConversationPage renders a useful empty state for that case instead of
  // silently routing the learner to Submit.
  const conversationContentAvailable = activeTopic ? conversationAvailableFor(activeTopic, activeProgression) : false;
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

  const activeStoryId = activeTopic?.sourceStory?.id ?? activeTopic?.id;
  const activeStars = activeProgression?.quizStars ?? (activeStoryId ? loadLocalStars(activeStoryId) : 0);

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
        onStartSpeaking={() => {
          setPreviewCompletedFor(topicStoryId(activeTopic));
          bumpProgress();
          navigateTo(topicHasQuiz(activeTopic) ? "vocab-quiz" : "story-speaking");
        }}
      />
    );
  } else if (phase === "vocab-quiz") {
    body = (
      <VocabularyQuizPage
        topic={activeTopic}
        lessonLabel={activeTopic.name}
        hasConversation={conversationContentAvailable}
        onFinished={() => {
          bumpProgress();
          navigateTo("story-speaking");
        }}
        onRoundCompleted={bumpProgress}
        onOpenPreview={() => navigateTo("vocab-preview")}
        onStartPractice={(practice) => {
          bumpProgress();
          const studentId = getStudentId();
          const storyId = activeTopic.sourceStory?.id ?? activeTopic.id;
          if (studentId && canUseDatabase()) {
            getVocabularyProgression(storyId, studentId)
              .then(setActiveProgression)
              .catch(() => { /* local star mirror is the fallback */ });
          }
          navigateTo(practice);
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
          markPhaseSeen(topicStoryId(activeTopic), "speaking");
          bumpProgress();
          navigateTo("submit");
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
          if (availableConversationTurns.length > 0) markPhaseSeen(topicStoryId(activeTopic), "conversation");
          bumpProgress();
          navigateTo("submit");
        }}
        onBack={backToStudy}
      />
    );
  } else if (phase === "submit") {
    body = (
      <SubmitStoryPage
        topic={activeTopic}
        sceneCount={progressInput?.sceneCount ?? 0}
        scenesRecorded={progressInput?.scenesRecorded ?? 0}
        turnCount={progressInput?.turnCount ?? 0}
        turnsRecorded={progressInput?.turnsRecorded ?? 0}
        alreadySubmitted={lessonSteps?.submit.done ?? false}
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
        steps={lessonSteps}
        onNavigateSection={(next) => {
          const cameFromSettings = section === "settings";
          setSection(next);
          if (next === "study" && !cameFromSettings) setActiveTopic(null);
        }}
        onNavigatePhase={
          activeTopic
            ? (next) => {
                if (next !== "completion" && lessonSteps && !lessonSteps[next].unlocked) return;
                navigateTo(next);
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
