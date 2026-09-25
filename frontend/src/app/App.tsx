import { useState, useEffect, useCallback } from "react";
import HomePage from "../features/home/HomePage";
import ErrorBoundary from "../components/ui/ErrorBoundary";

import StudentLoginPage from "../features/auth/StudentLoginPage";
import Navigation from "../components/navigation/Navigation";
import {
  getStudentName,
  getStudentId,
  saveLastVisitedPage,
  clearLastVisitedPage,
} from "../utils/studentSession";
import { signOut } from "../utils/session";
import {
  canUseDatabase,
  createAudioRecord,
  listCustomStories,
  logoutStudent,
} from "../services/database";
import { getStudentAppBootstrapState, collectPinyinTexts } from "../config/appNavigation";
import type { AudioRecord, PracticeTarget } from "./appTypes";
import {
  serializeAudioRecord,
  updateStoredAudioRecord,
  writeAudioRecordsCache,
} from "@entities/audio";
import {
  publishedTopicsFromStories,
  saveCustomStories,
} from "@entities/story";
import type { Topic } from "@entities/topic";
import { primePinyin } from "../utils/pinyin";
import type { Page } from "../types/page";
import StudentApp from "./student/StudentApp";
import { replaceHistorySnapshot } from "../utils/studentHistory";

const STUDENT_APP_HISTORY_KEY = "mandarinApp";

type StudentAppHistoryState = {
  currentPage: Page;
};

const STUDENT_MODE_PAGES: readonly Page[] = [
  "student-workspace",
  "student-practice",
  "student-stories",
  "voice-test",
  "listen-retell",
  "placement-test",
];

export type { Page };

export type { AudioRecord, PracticeTarget };
export { getStudentAppBootstrapState } from "../config/appNavigation";

export default function App() {
  const [bootstrapState] = useState(getStudentAppBootstrapState);
  const [currentPage, setCurrentPage] = useState<Page>(bootstrapState.currentPage);
  const [activeRole, setActiveRole] = useState<"student" | null>(bootstrapState.activeRole);
  // Full audio history is owned by the Progress page and fetched when the
  // learner opens it. Nothing from the historical recording table blocks
  // the student shell bootstrap.
  // Only the setter is read now — the list itself is written straight to the
  // local cache/backend and re-read by the Progress page, not rendered here.
  const [, setAudioRecords] = useState<AudioRecord[]>([]);
  // The student shell is gated only on data required to choose and launch a
  // lesson. Recording history is intentionally deferred to Progress.
  const [publishedTopicsReady, setPublishedTopicsReady] = useState(false);
  const studentDataReady = publishedTopicsReady;
  const [publishedTopics, setPublishedTopics] = useState<Topic[]>([]);
  const [, setPinyinRevision] = useState(0);
  const storyTopics = publishedTopics;

  // The student workspace is state-driven rather than URL-driven, so keep a
  // browser history snapshot for deep activity launches. This lets the story
  // header's Back button restore Home/Progress/etc. instead of always
  // reconstructing the Practice catalogue.
  useEffect(() => {
    if (typeof window === "undefined") return;

    if (!window.history.state?.[STUDENT_APP_HISTORY_KEY]) {
      const initialHistory: StudentAppHistoryState = {
        currentPage: bootstrapState.currentPage,
      };
      replaceHistorySnapshot(STUDENT_APP_HISTORY_KEY, initialHistory);
    }

    const restoreStudentHistory = (event: PopStateEvent) => {
      const next = event.state?.[STUDENT_APP_HISTORY_KEY] as
        | StudentAppHistoryState
        | undefined;
      if (!next) return;
      setCurrentPage(next.currentPage);
    };

    window.addEventListener("popstate", restoreStudentHistory);
    return () => window.removeEventListener("popstate", restoreStudentHistory);
  }, [bootstrapState]);
  // A signed-in student must never land back on the login screen — e.g. the
  // browser Back button popping to a stale pre-login history entry. They've
  // already authenticated (the session is live), so bounce them straight to
  // their workspace instead of re-prompting a login they've completed.
  useEffect(() => {
    if (activeRole === "student" && currentPage === "student-login") {
      setCurrentPage("student-workspace");
    }
  }, [activeRole, currentPage]);
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

  // Remembers the page a student is on so a reload (or reopening the
  // browser later — this is signed in via localStorage, not a per-tab
  // session) lands them back there. StudentApp owns its own Study/Progress
  // + lesson-phase state internally now, so this only needs the top-level
  // page, not a workspace view or in-progress practice target.
  useEffect(() => {
    if (activeRole !== "student") return;
    saveLastVisitedPage(currentPage);
  }, [activeRole, currentPage]);

  const refreshPublishedTopics = useCallback(async () => {
    if (!canUseDatabase()) {
      setPublishedTopics([]);
      return;
    }
    try {
      const stories = await listCustomStories();
      saveCustomStories(stories);
      setPublishedTopics(publishedTopicsFromStories(stories));
    } catch {/* keep current */}
  }, []);

  useEffect(() => {
    if (activeRole !== "student") {
      setPublishedTopics([]);
      setPublishedTopicsReady(true);
      return;
    }

    setPublishedTopicsReady(false);
    refreshPublishedTopics().finally(() => setPublishedTopicsReady(true));
  }, [activeRole, refreshPublishedTopics]);

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

  const addAudioRecord = async (record: AudioRecord): Promise<string | undefined> => {
    const linkedRecord = { ...record, studentId: getStudentId() };
    setAudioRecords((prev) => [linkedRecord, ...prev]);
    const audioData = serializeAudioRecord(linkedRecord);
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    writeAudioRecordsCache([audioData, ...stored]);

    if (canUseDatabase() && !(record.serverVerified && record.serverRecordId)) {
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
    setCurrentPage("student-workspace");
    // The history entry current at login time still carries the pre-login
    // "home" snapshot written on mount (nothing else replaces it). Left
    // alone, a single Back out of a story pops straight to that stale
    // entry and bounces a signed-in student to the marketing page instead
    // of their workspace.
    if (typeof window !== "undefined") {
      replaceHistorySnapshot(STUDENT_APP_HISTORY_KEY, {
        currentPage: "student-workspace",
      });
    }
  };

  const handleLogout = () => {
    setActiveRole(null);
    setAudioRecords([]);
    // Must run before signOut() clears the session — the scope key they
    // read to find this student's stored state comes from that session.
    clearLastVisitedPage();
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

  // NOTE: the student-side "raise hand" affordance was removed with the old
  // Student Mode UI (StudentHelpPanel/StudentHelpCard). The teacher help
  // queue still reads requests from the backend; nothing in the new student
  // IA creates one. Restore a button + this handler if that feature is
  // wanted back.

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
          actions on screen twice. The rail stays fixed through a practice
          session too (the running story's own navigation lives in a header
          strip above its content, not here and not in the rail), so this
          top bar is simply never shown on this route, session or not. */}
      {!(activeRole === "student" && STUDENT_MODE_PAGES.includes(currentPage)) && (
        <Navigation
          currentPage={currentPage}
          activeRole={activeRole}
          onNavigate={setCurrentPage}
          onLogout={handleLogout}
        />
      )}
      {currentPage === "home" && <HomePage onNavigate={setCurrentPage} />}
      {currentPage === "student-login" && (
        <StudentLoginPage
          onLogin={handleLogin}
        />
      )}
      {activeRole === "student" && !studentDataReady && STUDENT_MODE_PAGES.includes(currentPage) && (
        <div className="app-loading">
          <div className="app-loading-card">
            <div className="app-loading-icon" aria-hidden="true" />
            <h2>Loading your progress…</h2>
          </div>
        </div>
      )}
      {/* Every legacy student route (the old practice/progress workspace,
          voice-test, listen-retell, placement-test) now mounts the same
          new Student Mode UI — those distinct standalone tools don't exist
          in the new IA (Study + Progress only), so a student who had one
          of those pages saved as their last-visited page still lands
          somewhere real instead of a dead route. */}
      {STUDENT_MODE_PAGES.includes(currentPage) && activeRole === "student" && studentDataReady && (
        <StudentApp
          studentName={getStudentName()}
          topics={storyTopics}
          onAddRecord={addAudioRecord}
          onLogout={handleLogout}
        />
      )}
    </div>
    </ErrorBoundary>
  );
}
