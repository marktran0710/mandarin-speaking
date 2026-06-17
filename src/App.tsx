import { useState, useEffect, useCallback } from "react";
import HomePage from "./pages/HomePage";
import CreateStoryPage from "./pages/CreateStoryPage";
import MyStoriesPage from "./pages/MyStoriesPage";
import VoiceTestPage from "./pages/VoiceTestPage";
import TeacherImageBuilderPage from "./pages/TeacherImageBuilderPage";
import ErrorBoundary from "./components/ErrorBoundary";

import LoginPage, { LoginRole } from "./pages/LoginPage";
import Navigation from "./components/Navigation";
import {
  canUseDatabase,
  createAudioRecord,
  createHelpRequest,
  deleteAudioRecordFromDatabase,
  HelpRequest,
  listAudioRecords,
  listCustomStories,
  listHelpRequests,
  resolveHelpRequest,
  StoredAudioRecord,
} from "./database";
import {
  loadPublishedTeacherTopics,
  saveCustomStories,
} from "./utils/teacherStories";
import type { Topic } from "./TopicSelector";

export type Page =
  | "home"
  | "student-login"
  | "teacher-login"
  | "student-practice"
  | "student-stories"
  | "voice-test"
  | "teacher-dashboard"
  | "teacher-image-builder";

interface AudioRecord {
  id: string;
  audioBlob: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  model: "openai" | "gemini" | "webspeech" | "funasr" | "vibevoice";
  praatMetrics?: any;
  topicId?: string;
  imageUrl?: string;
  imageIndex?: number;
  audioUrl?: string;
}

interface PracticeTarget {
  topicId: string;
  imageIndex: number;
}

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("home");
  const [activeRole, setActiveRole] = useState<LoginRole | null>(null);
  const [audioRecords, setAudioRecords] = useState<AudioRecord[]>([]);
  const [helpRequests, setHelpRequests] = useState<HelpRequest[]>([]);
  const [practiceTarget, setPracticeTarget] = useState<PracticeTarget | null>(null);
  const [publishedTopics, setPublishedTopics] = useState<Topic[]>(
    () => loadPublishedTeacherTopics(),
  );

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
    const directVoiceTestPath =
      window.location.pathname === "/analyze" ||
      window.location.pathname === "/voice-test";
    const storedRole = localStorage.getItem("activeRole");
    if (storedRole === "student" || storedRole === "teacher") {
      setActiveRole(storedRole);
      setCurrentPage(
        storedRole === "student" && directVoiceTestPath
          ? "voice-test"
          : storedRole === "student"
            ? "student-practice"
            : "teacher-dashboard",
      );
    }

    loadSavedAudioRecords();
  }, []);

  useEffect(() => {
    if (!canUseDatabase()) return;
    listCustomStories()
      .then((stories) => {
        saveCustomStories(stories as any);
        setPublishedTopics(loadPublishedTeacherTopics());
      })
      .catch(() => {/* keep localStorage version */});
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
    setAudioRecords((prev) => [record, ...prev]);
    const audioData = serializeAudioRecord(record);
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

  const deleteAudioRecord = (id: string) => {
    setAudioRecords((prev) => prev.filter((record) => record.id !== id));
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    const updated = stored.filter((record: any) => record.id !== id);
    localStorage.setItem("audioRecords", JSON.stringify(updated));

    if (canUseDatabase()) {
      deleteAudioRecordFromDatabase(id).catch((error) => {
        console.error("Failed to delete audio record from database:", error);
      });
    }
  };

  const handleLogin = (role: LoginRole) => {
    setActiveRole(role);
    localStorage.setItem("activeRole", role);
    setCurrentPage(role === "student" ? "student-practice" : "teacher-dashboard");
  };

  const handleLogout = () => {
    setActiveRole(null);
    setPracticeTarget(null);
    localStorage.removeItem("activeRole");
    setCurrentPage("home");
  };

  const handlePracticeImage = (topicId: string, imageIndex: number) => {
    setPracticeTarget({ topicId, imageIndex });
    setCurrentPage("student-practice");
  };

  const handleRaiseHand = (message: string) => {
    const studentName = getSessionName("studentSession", "Student");
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

  const handleResolveHelpRequest = (id: string) => {
    const resolvedAt = new Date().toISOString();
    setHelpRequests((requests) =>
      saveHelpRequestsLocally(
        requests.map((request) =>
          request.id === id
            ? { ...request, status: "resolved", resolvedAt }
            : request,
        ),
      ),
    );

    if (canUseDatabase()) {
      resolveHelpRequest(id)
        .then((savedRequest) => {
          setHelpRequests((requests) =>
            saveHelpRequestsLocally(upsertHelpRequest(requests, savedRequest)),
          );
        })
        .catch((error) => {
          console.error("Failed to resolve help request in database:", error);
        });
    }
  };

  return (
    <ErrorBoundary>
    <div className="app-container">
      <Navigation
        currentPage={currentPage}
        activeRole={activeRole}
        onNavigate={setCurrentPage}
        onLogout={handleLogout}
      />
      {currentPage === "home" && <HomePage onNavigate={setCurrentPage} />}
      {currentPage === "student-login" && (
        <LoginPage role="student" onLogin={handleLogin} onBack={() => setCurrentPage("home")} />
      )}
      {currentPage === "teacher-login" && (
        <LoginPage role="teacher" onLogin={handleLogin} onBack={() => setCurrentPage("home")} />
      )}
      {currentPage === "student-practice" && activeRole === "student" && (
        <CreateStoryPage
          onAddRecord={addAudioRecord}
          initialTopicId={practiceTarget?.topicId}
          initialImageIndex={practiceTarget?.imageIndex}
          helpRequests={helpRequests}
          onRaiseHand={handleRaiseHand}
          publishedTopics={publishedTopics}
        />
      )}
      {currentPage === "student-stories" && activeRole === "student" && (
        <MyStoriesPage
          records={audioRecords}
          onDeleteRecord={deleteAudioRecord}
          onPracticeImage={handlePracticeImage}
          mode="student"
          helpRequests={helpRequests}
          onRaiseHand={handleRaiseHand}
          publishedTopics={publishedTopics}
        />
      )}
      {currentPage === "voice-test" && activeRole === "student" && (
        <VoiceTestPage />
      )}
      {currentPage === "teacher-dashboard" && activeRole === "teacher" && (
        <MyStoriesPage
          records={audioRecords}
          onDeleteRecord={deleteAudioRecord}
          mode="teacher"
          helpRequests={helpRequests}
          onResolveHelpRequest={handleResolveHelpRequest}
          onRefreshRecords={loadSavedAudioRecords}
        />
      )}
      {currentPage === "teacher-image-builder" && activeRole === "teacher" && (
        <TeacherImageBuilderPage />
      )}
    </div>
    </ErrorBoundary>
  );
}

function getSessionName(storageKey: string, fallback: string) {
  try {
    const session = JSON.parse(localStorage.getItem(storageKey) || "{}");
    return typeof session.name === "string" && session.name.trim()
      ? session.name.trim()
      : fallback;
  } catch {
    return fallback;
  }
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
    imageUrl: record.imageUrl,
    imageIndex: record.imageIndex,
    audioUrl: record.audioUrl,
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
