import { useState, useEffect, useCallback, useMemo } from "react";
import HomePage from "./pages/HomePage";
import CreateStoryPage from "./pages/CreateStoryPage";
import MyStoriesPage from "./pages/MyStoriesPage";
import VoiceTestPage from "./pages/VoiceTestPage";
import ImageNarrationPage from "./pages/ImageNarrationPage";
import ListenRetellPage from "./pages/ListenRetellPage";
import ErrorBoundary from "./components/ErrorBoundary";

import StudentLoginPage from "./pages/StudentLoginPage";
import Navigation from "./components/Navigation";
import JourneyBubble from "./components/JourneyBubble";
import WrongMode from "./components/WrongMode";
import {
  getStudentName,
  getStudentId,
  getLastVisitedPage,
  saveLastVisitedPage,
  clearLastVisitedPage,
  getLastPracticeTarget,
  saveLastPracticeTarget,
  clearLastPracticeTarget,
} from "./utils/studentSession";
import { currentRole, signOut } from "./utils/session";
import {
  canUseDatabase,
  createAudioRecord,
  createHelpRequest,
  HelpRequest,
  listAudioRecords,
  listCustomStories,
  listHelpRequests,
  StoredAudioRecord,
} from "./services/database";
import {
  loadPublishedTeacherTopics,
  saveCustomStories,
} from "./utils/teacherStories";
import type { Topic } from "./components/TopicSelector";
import {
  groupTopicsByLesson,
  isLessonGroupUnlocked,
  lessonCompletion,
} from "./utils/lessonGroups";
import { loadSubmittedStoryIds } from "./utils/storyLevelProgress";
import { topicHasQuiz } from "./utils/topicQuiz";
import { primePinyin } from "./utils/pinyin";
import type { Page } from "./types/page";
import type { SpeechModel } from "./components/StoryRecorder";

export type { Page };

interface AudioRecord {
  id: string;
  audioBlob: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  // Was its own stale "openai" | "gemini" | ... | "funasr" union, drifted
  // from StoryRecorder's actual SpeechModel options (only ever masked
  // because CreateStoryPage's onAddRecord prop was typed `any`).
  model: SpeechModel;
  praatMetrics?: any;
  topicId?: string;
  studentId?: string | null;
  imageUrl?: string;
  imageIndex?: number;
  audioUrl?: string;
  analysisVersion?: "stable_v1" | "phoneme_tone_v2";
  analysisSchemaVersion?: string;
  modelVersion?: string;
  comparisonGroupId?: string;
  sessionId?: string;
  attemptId?: string;
  attemptNumber?: number;
  attemptType?: "WHOLE_SENTENCE_INITIAL" | "FOCUSED_RETRY" | "WHOLE_SENTENCE_FINAL";
}

interface PracticeTarget {
  topicId: string;
  imageIndex: number;
  /** Bumped on every jump so CreateStoryPage remounts (and opens the
   * target story) even when the student is already on the practice page
   * or jumps to the same story twice. */
  seq?: number;
}

// Sections worth restoring on reload. Excludes "home" and "student-login" —
// if a logged-in student's stored page were ever one of those (shouldn't
// happen, but storage can be stale or edited) landing back on the marketing
// page instead of practice would look like the app forgot they were signed in.
const RESTORABLE_STUDENT_PAGES: readonly Page[] = [
  "student-practice",
  "student-stories",
  "voice-test",
  "image-narration",
  "listen-retell",
];

function isRestorableStudentPage(page: string | null): page is Page {
  return RESTORABLE_STUDENT_PAGES.includes(page as Page);
}

function collectPinyinTexts(topics: readonly Topic[]): string[] {
  const texts: string[] = [];
  for (const topic of topics) {
    texts.push(...(topic.prompts ?? []));
    for (const scene of Object.values(topic.vocabulary)) texts.push(...scene);
    for (const scene of Object.values(topic.phrases ?? {})) texts.push(...scene);
    for (const group of Object.values(topic.vocabularyGroups ?? {})) {
      for (const vocabGroup of group) texts.push(...vocabGroup.words);
    }
    texts.push(...Object.values(topic.suggestedAnswers ?? {}));
    texts.push(...Object.values(topic.listenScripts ?? {}));
  }
  return texts;
}

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("home");
  const [activeRole, setActiveRole] = useState<"student" | null>(null);
  // A teacher session reaching the student site. Read once on mount, like
  // `activeRole` below — the session only changes through a sign-in or a
  // sign-out, and both of those reload or re-render this component anyway.
  const [blockedRole, setBlockedRole] = useState(false);
  const [isInPracticeSession, setIsInPracticeSession] = useState(false);
  const [audioRecords, setAudioRecords] = useState<AudioRecord[]>([]);
  const [helpRequests, setHelpRequests] = useState<HelpRequest[]>([]);
  const [practiceTarget, setPracticeTarget] = useState<PracticeTarget | null>(null);
  const [publishedTopics, setPublishedTopics] = useState<Topic[]>(
    () => loadPublishedTeacherTopics(),
  );
  const [, setPinyinRevision] = useState(0);
  const storyTopics = useMemo(
    () => publishedTopics.filter((t) => (t.narrativeMode ?? "story") === "story"),
    [publishedTopics],
  );
  const describeTopics = useMemo(
    () => publishedTopics.filter((t) => t.narrativeMode === "describe"),
    [publishedTopics],
  );
  const listenRetellTopics = useMemo(
    () => publishedTopics.filter((t) => t.narrativeMode === "listen_retell"),
    [publishedTopics],
  );

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
        const recordsData = await listAudioRecords();
        setAudioRecords(recordsFromStored(recordsData));
        localStorage.setItem("audioRecords", JSON.stringify(recordsData));
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
    // Deliberately URL-only: the voice test is a diagnostic tool (raw pitch
    // contours, Praat plots) for the teacher and for debugging, not a
    // student learning section, so it gets no navbar link. Reaching it
    // still requires an existing student session — the paths below only
    // choose the landing page for a student who is already logged in.
    const directVoiceTestPath =
      window.location.pathname === "/analyze" ||
      window.location.pathname === "/voice-test";
    const role = currentRole();
    if (role === "teacher") {
      // Teacher signed in on this device — the student site is closed to
      // them until they sign out. Covers the /analyze and /voice-test deep
      // links too, since those route through here.
      setBlockedRole(true);
      return;
    }
    if (role === "student") {
      setActiveRole("student");
      if (directVoiceTestPath) {
        setCurrentPage("voice-test");
      } else {
        const lastPage = getLastVisitedPage();
        const restoredPage = isRestorableStudentPage(lastPage)
          ? lastPage
          : "student-practice";
        setCurrentPage(restoredPage);
        // Only worth restoring for the page it actually feeds — a saved
        // target would otherwise silently jump the student straight back
        // into that story the next time they land on student-practice.
        if (restoredPage === "student-practice") {
          const lastTarget = getLastPracticeTarget();
          if (lastTarget) {
            setPracticeTarget({
              topicId: lastTarget.topicId,
              imageIndex: lastTarget.imageIndex,
            });
          }
        }
      }
    }

    loadSavedAudioRecords();
  }, []);

  // Remembers the section a student is on so a reload (or reopening the
  // browser later — this is signed in via localStorage, not a per-tab
  // session) lands them back there instead of always bouncing to practice.
  useEffect(() => {
    if (activeRole !== "student") return;
    saveLastVisitedPage(currentPage);
  }, [activeRole, currentPage]);

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
    refreshPublishedTopics();
  }, []);

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

    loadSavedHelpRequests();

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
    localStorage.setItem(
      "audioRecords",
      JSON.stringify([audioData, ...stored]),
    );

    if (canUseDatabase()) {
      try {
        const savedRecord = await createAudioRecord(audioData, record.audioBlob);
        if (savedRecord?.audioUrl) {
          updateStoredAudioRecord(record.id, savedRecord.audioUrl);
          setAudioRecords((currentRecords) =>
            currentRecords.map((currentRecord) =>
              currentRecord.id === record.id
                ? { ...currentRecord, audioUrl: savedRecord.audioUrl }
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
    setCurrentPage("student-practice");
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
    signOut();
    setCurrentPage("home");
  };

  const handlePracticeImage = (topicId: string, imageIndex: number) => {
    setPracticeTarget({ topicId, imageIndex, seq: Date.now() });
    setCurrentPage("student-practice");
  };

  // My Profile's lesson/story rows link back to the lesson list to practice
  // rather than jumping into a specific prompt — clears any stale target so
  // CreateStoryPage renders the table-of-contents browse view.
  const handleBrowsePractice = () => {
    setPracticeTarget(null);
    setCurrentPage("student-practice");
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

  // The bubble's jump candidates: the newest unlocked lesson — the TOC's
  // "you are here" row (first unlocked numbered lesson still holding
  // unsubmitted stories) — narrowed to its quiz-capable stories. Groups
  // are built from ALL story topics so the sequential lock matches the
  // TOC exactly; only the candidate list is quiz-filtered. Recomputed per
  // render on purpose: submission state lives in localStorage and changes
  // as stories are finished.
  const bubbleTargetIds = (() => {
    const groups = groupTopicsByLesson(storyTopics);
    const submittedIds = loadSubmittedStoryIds();
    const nowGroup = groups.find(
      (group, index) =>
        group.lessonNumber !== null &&
        isLessonGroupUnlocked(groups, index, submittedIds) &&
        lessonCompletion(group, submittedIds).done < group.topics.length,
    );
    if (!nowGroup) return undefined;
    const quizIds = new Set(quizStoryTopics.map((t) => t.id));
    // Empty is a real answer here (this lesson has no quiz-capable
    // stories), not "unknown scope" — only a missing group falls back to
    // undefined, so the bubble never pulses for a story outside this lesson.
    return nowGroup.topics.map((t) => t.id).filter((id) => quizIds.has(id));
  })();

  // One bubble across every logged-in student page (it mounts here, not
  // per-page) — hidden only while a practice session is active, where its
  // "jump into your current story" call-to-action would point at the
  // place the student already is.
  const showJourneyBubble =
    activeRole === "student" &&
    currentPage !== "home" &&
    currentPage !== "student-login" &&
    !(currentPage === "student-practice" && isInPracticeSession);

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

  if (blockedRole) {
    return (
      <ErrorBoundary>
        <WrongMode expected="student" />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
    <div className="app-container">
      <Navigation
        currentPage={currentPage}
        activeRole={activeRole}
        onNavigate={setCurrentPage}
        onLogout={handleLogout}
        compact={currentPage === "student-practice" && isInPracticeSession}
        hasDescribeStories={describeTopics.length > 0}
        hasListenRetellStories={listenRetellTopics.length > 0}
      />
      {currentPage === "home" && <HomePage onNavigate={setCurrentPage} />}
      {currentPage === "student-login" && (
        <StudentLoginPage
          onLogin={handleLogin}
          onBack={() => setCurrentPage("home")}
        />
      )}
      {currentPage === "student-practice" && activeRole === "student" && (
        <CreateStoryPage
          key={
            practiceTarget
              ? `${practiceTarget.topicId}:${practiceTarget.seq ?? 0}`
              : "browse"
          }
          onAddRecord={addAudioRecord}
          initialTopicId={practiceTarget?.topicId}
          initialImageIndex={practiceTarget?.imageIndex}
          helpRequests={helpRequests}
          onRaiseHand={handleRaiseHand}
          publishedTopics={storyTopics}
          onSessionActiveChange={setIsInPracticeSession}
        />
      )}
      {currentPage === "student-stories" && activeRole === "student" && (
        <MyStoriesPage
          records={audioRecords}
          onBrowsePractice={handleBrowsePractice}
          helpRequests={helpRequests}
          onRaiseHand={handleRaiseHand}
          publishedTopics={storyTopics}
        />
      )}
      {currentPage === "voice-test" && activeRole === "student" && (
        <VoiceTestPage />
      )}
      {currentPage === "image-narration" && activeRole === "student" && (
        <ImageNarrationPage publishedTopics={describeTopics} />
      )}
      {currentPage === "listen-retell" && activeRole === "student" && (
        <ListenRetellPage publishedTopics={listenRetellTopics} />
      )}
      {showJourneyBubble && (
        <JourneyBubble
          studentName={getStudentName()}
          studentId={getStudentId()}
          storyCount={quizStoryTopics.length}
          storyTitles={storyTitles}
          // Admin gets the same bubble as a student — the pulse is a demo
          // surface, not a gate, and an inert dial reads as broken when
          // the teacher walks through the app (which is what admin is for).
          targetIds={bubbleTargetIds}
          refreshToken={`${currentPage}:${isInPracticeSession}`}
          onJumpToStory={handleJumpToStory}
        />
      )}
    </div>
    </ErrorBoundary>
  );
}

function loadLocalHelpRequests(): HelpRequest[] {
  try {
    const requests = JSON.parse(localStorage.getItem("helpRequests") || "[]");
    return Array.isArray(requests) ? requests : [];
  } catch {
    return [];
  }
}

function saveHelpRequestsLocally(requests: HelpRequest[]): HelpRequest[] {
  localStorage.setItem("helpRequests", JSON.stringify(requests));
  return requests;
}

function upsertHelpRequest(
  requests: HelpRequest[],
  nextRequest: HelpRequest,
): HelpRequest[] {
  const existingIndex = requests.findIndex(
    (request) => request.id === nextRequest.id,
  );
  if (existingIndex === -1) {
    return [nextRequest, ...requests];
  }

  return requests.map((request, index) =>
    index === existingIndex ? nextRequest : request,
  );
}

function serializeAudioRecord(record: AudioRecord): StoredAudioRecord {
  return {
    id: record.id,
    timestamp: record.timestamp,
    duration: record.duration,
    transcription: record.transcription,
    model: record.model,
    topicId: record.topicId,
    studentId: getStudentId(),
    imageUrl: record.imageUrl,
    imageIndex: record.imageIndex,
      audioUrl: record.audioUrl,
      analysisVersion: record.analysisVersion ?? record.praatMetrics?.analysis_version ?? "stable_v1",
      analysisSchemaVersion: record.analysisSchemaVersion ?? record.praatMetrics?.analysis_schema_version,
      modelVersion: record.modelVersion ?? record.praatMetrics?.model_version,
      comparisonGroupId: record.comparisonGroupId,
      sessionId: record.sessionId,
      attemptId: record.attemptId,
      attemptNumber: record.attemptNumber,
      attemptType: record.attemptType,
    praatMetrics: record.praatMetrics,
  };
}

function recordsFromStored(recordsData: StoredAudioRecord[]): AudioRecord[] {
  return recordsData.map((data) => ({
    ...data,
    audioBlob: new Blob([], { type: "audio/webm" }),
    model: data.model as AudioRecord["model"],
  }));
}

function updateStoredAudioRecord(id: string, audioUrl: string) {
  const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
  const updated = stored.map((record: StoredAudioRecord) =>
    record.id === id ? { ...record, audioUrl } : record,
  );
  localStorage.setItem("audioRecords", JSON.stringify(updated));
}
