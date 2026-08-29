import { useState, useEffect, useCallback, useMemo } from "react";
import HomePage from "./pages/HomePage";
import VoiceTestPage from "./pages/VoiceTestPage";
import StudentWorkspacePage, {
  type StudentWorkspaceView,
} from "./pages/StudentWorkspacePage";
import ErrorBoundary from "./components/ErrorBoundary";

import StudentLoginPage from "./pages/StudentLoginPage";
import { BiLabel } from "./components/BiLabel";
import Navigation from "./components/Navigation";
import AppJourneyBubble from "./components/AppJourneyBubble";
import {
  getStudentName,
  getStudentId,
  saveLastVisitedPage,
  clearLastVisitedPage,
  saveLastPracticeTarget,
  clearLastPracticeTarget,
} from "./utils/studentSession";
import { signOut } from "./utils/session";
import {
  canUseDatabase,
  createAudioRecord,
  createHelpRequest,
  HelpRequest,
  listAudioRecords,
  listCustomStories,
  listHelpRequests,
  logoutStudent,
  StoredAudioRecord,
} from "./shared/api/learningApi";
import { getStudentAppBootstrapState, collectPinyinTexts } from "./config/appNavigation";
import type { AudioRecord, PracticeTarget } from "./app/appTypes";
import {
  recordsFromStored,
  serializeAudioRecord,
  updateStoredAudioRecord,
  writeAudioRecordsCache,
} from "./helpers/audioRecords";
import {
  loadLocalHelpRequests,
  saveHelpRequestsLocally,
  upsertHelpRequest,
} from "./helpers/helpRequests";
import {
  loadPublishedTeacherTopics,
  saveCustomStories,
} from "./utils/teacherStories";
import type { Topic } from "./components/TopicSelector";
import { topicHasQuiz } from "./utils/topicQuiz";
import { primePinyin } from "./utils/pinyin";
import type { Page } from "./types/page";
import { getJourneyBubbleTargetIds } from "./helpers/journeyBubble";

export type { Page };

export type { AudioRecord, PracticeTarget };
export { getStudentAppBootstrapState } from "./config/appNavigation";

export default function App() {
  const [bootstrapState] = useState(getStudentAppBootstrapState);
  const [currentPage, setCurrentPage] = useState<Page>(bootstrapState.currentPage);
  const [activeRole, setActiveRole] = useState<"student" | null>(bootstrapState.activeRole);
  const [studentWorkspaceView, setStudentWorkspaceView] =
    useState<StudentWorkspaceView>(bootstrapState.studentWorkspaceView);
  const [isInPracticeSession, setIsInPracticeSession] = useState(false);
  const [audioRecords, setAudioRecords] = useState<AudioRecord[]>([]);
  const [helpRequests, setHelpRequests] = useState<HelpRequest[]>([]);
  // Each of the student workspace's three initial fetches (audio records,
  // published topics, help requests) used to paint its own screen the
  // instant it resolved, so the workspace could visibly assemble itself
  // piece by piece on a slow connection. Gate the student routes behind all
  // three settling once, so they mount already fully populated.
  const [audioRecordsReady, setAudioRecordsReady] = useState(false);
  const [publishedTopicsReady, setPublishedTopicsReady] = useState(false);
  const [helpRequestsReady, setHelpRequestsReady] = useState(false);
  const studentDataReady = audioRecordsReady && publishedTopicsReady && helpRequestsReady;
  const [practiceTarget, setPracticeTarget] = useState<PracticeTarget | null>(
    bootstrapState.practiceTarget,
  );
  const [publishedTopics, setPublishedTopics] = useState<Topic[]>(
    () => loadPublishedTeacherTopics(),
  );
  const [, setPinyinRevision] = useState(0);
  const storyTopics = publishedTopics;
  useEffect(() => {
    let active = true;
    void primePinyin(collectPinyinTexts(publishedTopics))
      .then(() => {
        if (active) setPinyinRevision((revision) => revision + 1);
      })
      .catch(() => {
        // toPinyin keeps an offline fallback so the practice UI remains usable
        // when the backend is temporarily unavailable.
      });
    return () => {
      active = false;
    };
  }, [publishedTopics]);

  const loadSavedAudioRecords = useCallback(async () => {
    if (canUseDatabase()) {
      try {
        const serverRecords = await listAudioRecords({
          limit: 1000,
          studentId: getStudentId(),
        });
        let localRecords: StoredAudioRecord[] = [];
        try {
          const parsed = JSON.parse(localStorage.getItem("audioRecords") || "[]");
          if (Array.isArray(parsed)) {
            const studentId = getStudentId();
            localRecords = parsed.filter(
              (record: StoredAudioRecord) => !studentId || record.studentId === studentId,
            );
          }
        } catch {
          localRecords = [];
        }
        const byId = new Map<string, StoredAudioRecord>();
        for (const record of [...localRecords, ...serverRecords]) byId.set(record.id, record);
        const recordsData = Array.from(byId.values());
        setAudioRecords(recordsFromStored(recordsData));
        writeAudioRecordsCache(recordsData);
        return;
      } catch (error) {
        console.error("Failed to load audio records from database:", error);
      }
    }
    const stored = localStorage.getItem("audioRecords");
    if (!stored) return;
    try {
      const recordsData = JSON.parse(stored);
      if (Array.isArray(recordsData)) setAudioRecords(recordsFromStored(recordsData));
    } catch (error) {
      console.error("Failed to load audio records:", error);
    }
  }, []);

  useEffect(() => {
    loadSavedAudioRecords().finally(() => setAudioRecordsReady(true));
  }, []);

  // Remembers the section a student is on so a reload (or reopening the
  // browser later — this is signed in via localStorage, not a per-tab
  // session) lands them back there instead of always bouncing to practice.
  useEffect(() => {
    if (activeRole !== "student") return;
    const pageToSave: Page =
      currentPage !== "student-workspace"
        ? currentPage
        : studentWorkspaceView === "progress"
          ? "student-stories"
          : "student-practice";
    saveLastVisitedPage(pageToSave);
  }, [activeRole, currentPage, studentWorkspaceView]);

  // Remembers which story (and scene) was open on the practice page, so
  // that restore above lands on the actual session instead of the browse
  // view. `null` is saved deliberately too, once the student backs out.
  useEffect(() => {
    if (activeRole !== "student") return;
    saveLastPracticeTarget(
      practiceTarget
        ? { topicId: practiceTarget.topicId, imageIndex: practiceTarget.imageIndex }
        : null,
    );
  }, [activeRole, practiceTarget]);

  const refreshPublishedTopics = useCallback(async () => {
    if (!canUseDatabase()) {
      setPublishedTopics(loadPublishedTeacherTopics());
      return;
    }
    try {
      const stories = await listCustomStories();
      saveCustomStories(stories as any);
      setPublishedTopics(loadPublishedTeacherTopics());
    } catch {/* keep current */}
  }, []);

  useEffect(() => {
    refreshPublishedTopics().finally(() => setPublishedTopicsReady(true));
  }, []);

  // `publishedTopics` otherwise only loads once per page load, so a script a
  // teacher republishes after that never reaches an already-open tab until
  // the student reloads. Re-pull from the backend whenever the tab regains
  // focus (teacher and student are separate SPA instances/tabs, so this is
  // the only signal available without a push channel).
  useEffect(() => {
    if (activeRole !== "student") return;
    const handleVisibility = () => {
      if (document.visibilityState === "visible") refreshPublishedTopics();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", refreshPublishedTopics);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", refreshPublishedTopics);
    };
  }, [activeRole, refreshPublishedTopics]);

  useEffect(() => {
    const loadSavedHelpRequests = async () => {
      if (canUseDatabase()) {
        try {
          const requests = await listHelpRequests();
          setHelpRequests(requests);
          localStorage.setItem("helpRequests", JSON.stringify(requests));
          return;
        } catch (error) {
          console.error("Failed to load help requests from database:", error);
        }
      }

      setHelpRequests(loadLocalHelpRequests());
    };

    loadSavedHelpRequests().finally(() => setHelpRequestsReady(true));

    if (!canUseDatabase()) {
      return;
    }

    const intervalId = window.setInterval(loadSavedHelpRequests, 5000);
    return () => window.clearInterval(intervalId);
  }, []);

  const addAudioRecord = async (record: AudioRecord): Promise<string | undefined> => {
    const linkedRecord = { ...record, studentId: getStudentId() };
    setAudioRecords((prev) => [linkedRecord, ...prev]);
    const audioData = serializeAudioRecord(linkedRecord);
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    writeAudioRecordsCache([audioData, ...stored]);

    if (canUseDatabase()) {
      try {
        const savedRecord = await createAudioRecord(audioData, record.audioBlob);
        if (savedRecord?.audioUrl) {
          updateStoredAudioRecord(record.id, {
            audioUrl: savedRecord.audioUrl,
            audioName: savedRecord.audioName,
          });
          setAudioRecords((currentRecords) =>
            currentRecords.map((currentRecord) =>
              currentRecord.id === record.id
                ? {
                    ...currentRecord,
                    audioUrl: savedRecord.audioUrl,
                    audioName: savedRecord.audioName,
                  }
                : currentRecord,
            ),
          );
          return savedRecord.audioUrl;
        }
      } catch (error) {
        console.error("Failed to save audio record to database:", error);
      }
    }
    return undefined;
  };

  const handleLogin = () => {
    // StudentLoginPage has already written the session (it owns the name and
    // roster id); this only reacts to it.
    setActiveRole("student");
    setStudentWorkspaceView("practice");
    setCurrentPage("student-workspace");
  };

  const handleLogout = () => {
    setActiveRole(null);
    setPracticeTarget(null);
    // Must run before signOut() clears the session — the scope key they
    // read to find this student's stored state comes from that session.
    clearLastVisitedPage();
    clearLastPracticeTarget();
    // Clears the whole session, not just the role — the old code removed
    // `activeRole` and left `studentSession` behind forever, which meant a
    // "logged out" browser still carried a student identity.
    signOut("student");
    void logoutStudent().catch(() => {
      // Local role state is already cleared; an expired backend cookie will
      // be rejected on the next request and does not affect the teacher app.
    });
    setCurrentPage("home");
  };

  const handlePracticeImage = (topicId: string, imageIndex: number) => {
    setPracticeTarget({ topicId, imageIndex, seq: Date.now() });
    setStudentWorkspaceView("practice");
    setCurrentPage("student-workspace");
  };

  const handleStartActivity = (topicId: string, startAtQuiz: boolean) => {
    setPracticeTarget({
      topicId,
      imageIndex: 0,
      startAtQuiz,
      seq: Date.now(),
    });
    setStudentWorkspaceView("practice");
    setCurrentPage("student-workspace");
  };

  // The floating star bubble's jump target — quiz story ids may carry a
  // Medium/Hard tier suffix on the base topic id.
  const handleJumpToStory = (storyId: string) => {
    const topic = storyTopics.find(
      (t) => t.id === storyId || storyId.startsWith(`${t.id}-`),
    );
    if (topic) handlePracticeImage(topic.id, 0);
  };

  // Stars only come from vocab quizzes, so only quiz-capable stories join
  // the bubble's tally and target list — a story with no quiz content gets
  // no quiz phase (see StoryRecorder's hasVocabQuiz) and would otherwise
  // pulse forever as a dead-end target. Same test the lesson gate uses
  // (utils/topicQuiz), not a proxy, so both agree on which stories count.
  const quizStoryTopics = useMemo(
    () => storyTopics.filter((t) => topicHasQuiz(t)),
    [storyTopics],
  );
  const storyTitles = useMemo(
    () => Object.fromEntries(quizStoryTopics.map((t) => [t.id, t.name])),
    [quizStoryTopics],
  );

  const bubbleTargetIds = getJourneyBubbleTargetIds(storyTopics, quizStoryTopics);

  // One bubble across every logged-in student page (it mounts here, not
  // per-page) — hidden only while a practice session is active, where its
  // "jump into your current story" call-to-action would point at the
  // place the student already is. This used to also require
  // currentPage === "student-practice", which was the only route that ever
  // set isInPracticeSession back when this was written. The default
  // student workspace shell now runs practice sessions from inside
  // currentPage === "student-workspace" instead, so that extra check never
  // matched there — the bubble (position: fixed, bottom-right) stayed
  // visible through an entire recording, including the results/self-eval
  // screen, where it could sit on top of the "Record again"/"Next scene"
  // buttons in that same corner. isInPracticeSession alone is what the
  // comment above already describes; check only that.
  const showJourneyBubble =
    activeRole === "student" &&
    studentDataReady &&
    currentPage !== "home" &&
    currentPage !== "student-login" &&
    !isInPracticeSession &&
    // The workspace rail now carries the star tally in its own progress
    // card, and every lesson card already has its own "開始生詞測驗 Start
    // vocabulary quiz" button — the floating bubble was a third copy of
    // both, parked over the bottom-right corner where it overlapped page
    // content. It stays only on routes that render no rail.
    currentPage !== "student-workspace";

  const handleRaiseHand = (message: string) => {
    const studentName = getStudentName();
    const existingOpenRequest = helpRequests.find(
      (request) =>
        request.studentName === studentName && request.status === "open",
    );
    const request: HelpRequest = {
      id: existingOpenRequest?.id || `help-${Date.now()}`,
      studentName,
      message: message.trim() || "I need teacher help.",
      status: "open",
      createdAt: existingOpenRequest?.createdAt || new Date().toISOString(),
      resolvedAt: null,
    };

    setHelpRequests((requests) => saveHelpRequestsLocally(upsertHelpRequest(requests, request)));

    if (canUseDatabase()) {
      createHelpRequest(request)
        .then((savedRequest) => {
          setHelpRequests((requests) =>
            saveHelpRequestsLocally(upsertHelpRequest(requests, savedRequest)),
          );
        })
        .catch((error) => {
          console.error("Failed to send help request to database:", error);
        });
    }
  };

  return (
    <ErrorBoundary>
    <div
      className={`app-container${
        activeRole === "student" || currentPage === "home" || currentPage === "student-login"
          ? " student-app"
          : ""
      }`}
    >
      {/* The student workspace carries its own left rail (StudentSidebar),
          which already holds the section switch, identity, dark mode and
          log out — rendering this top bar as well would put those same
          actions on screen twice. During a practice session the rail stands
          down, so this bar comes back (compact) as the only chrome. */}
      {!(activeRole === "student" && currentPage === "student-workspace") && (
        <Navigation
          currentPage={currentPage}
          activeRole={activeRole}
          onNavigate={(page) => {
            if (page === "student-workspace") {
              setStudentWorkspaceView("practice");
            }
            setCurrentPage(page);
          }}
          onLogout={handleLogout}
          compact={activeRole === "student" && isInPracticeSession}
        />
      )}
      {currentPage === "home" && <HomePage onNavigate={setCurrentPage} />}
      {currentPage === "student-login" && (
        <StudentLoginPage
          onLogin={handleLogin}
        />
      )}
      {activeRole === "student" &&
        !studentDataReady &&
        (currentPage === "student-workspace" ||
          currentPage === "student-practice" ||
          currentPage === "student-stories" ||
          currentPage === "voice-test") && (
          <div className="app-loading">
            <div className="app-loading-card">
              <div className="app-loading-icon" aria-hidden="true" />
              <h2><BiLabel k="loading_your_progress" /></h2>
            </div>
          </div>
        )}
      {currentPage === "student-workspace" && activeRole === "student" && studentDataReady && (
        <StudentWorkspacePage
          view={studentWorkspaceView}
          onViewChange={(nextView) => {
            setStudentWorkspaceView(nextView);
            if (nextView !== "practice") setPracticeTarget(null);
          }}
          onAddRecord={addAudioRecord}
          initialTopicId={practiceTarget?.topicId}
          initialImageIndex={practiceTarget?.imageIndex}
          initialStartAtQuiz={practiceTarget?.startAtQuiz}
          initialTargetKey={practiceTarget?.seq}
          helpRequests={helpRequests}
          onRaiseHand={handleRaiseHand}
          storyTopics={storyTopics}
          audioRecords={audioRecords}
          onSessionActiveChange={setIsInPracticeSession}
          isInPracticeSession={isInPracticeSession}
          onStartActivity={handleStartActivity}
          onLogout={handleLogout}
        />
      )}
      {/* currentPage is never actually set to "student-practice" or
          "student-stories" during a live session — every navigation
          handler (handleStartActivity, handleJumpToStory) routes through
          "student-workspace" plus a
          studentWorkspaceView, and the boot-time restore in
          appNavigation.ts translates a saved "student-stories"/
          "student-practice" value into "student-workspace" too. These two
          Page values now exist only as the on-disk encoding
          saveLastVisitedPage uses to remember which workspace view (see
          below) — the standalone CreateStoryPage/MyStoriesPage renders
          that used to live here, from before StudentWorkspaceShell
          existed, could never be reached and were removed. */}
      {currentPage === "voice-test" && activeRole === "student" && studentDataReady && (
        <VoiceTestPage />
      )}
      <AppJourneyBubble
        visible={showJourneyBubble}
        studentName={getStudentName()}
        studentId={getStudentId()}
        storyCount={quizStoryTopics.length}
        storyTitles={storyTitles}
        targetIds={bubbleTargetIds}
        refreshToken={`${currentPage}:${studentWorkspaceView}:${isInPracticeSession}`}
        onJumpToStory={handleJumpToStory}
      />
    </div>
    </ErrorBoundary>
  );
}
