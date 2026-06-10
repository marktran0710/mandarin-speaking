import { useState, useEffect } from "react";
import HomePage from "./pages/HomePage";
import CreateStoryPage from "./pages/CreateStoryPage";
import MyStoriesPage from "./pages/MyStoriesPage";
import VoiceTestPage from "./pages/VoiceTestPage";
import TeacherImageBuilderPage from "./pages/TeacherImageBuilderPage";
import LoginPage, { LoginRole } from "./pages/LoginPage";
import Navigation from "./components/Navigation";
import {
  canUseDatabase,
  createAudioRecord,
  deleteAudioRecordFromDatabase,
  listAudioRecords,
  StoredAudioRecord,
} from "./database";

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
  const [practiceTarget, setPracticeTarget] = useState<PracticeTarget | null>(
    null,
  );

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

    const loadSavedAudioRecords = async () => {
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
      if (!stored) {
        return;
      }

      try {
        const recordsData = JSON.parse(stored);
        if (Array.isArray(recordsData)) {
          setAudioRecords(recordsFromStored(recordsData));
        }
      } catch (error) {
        console.error("Failed to load audio records:", error);
      }
    };

    loadSavedAudioRecords();
  }, []);

  const addAudioRecord = (record: AudioRecord) => {
    setAudioRecords((prev) => [record, ...prev]);
    const audioData = serializeAudioRecord(record);
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    localStorage.setItem(
      "audioRecords",
      JSON.stringify([audioData, ...stored]),
    );

    if (canUseDatabase()) {
      createAudioRecord(audioData, record.audioBlob)
        .then((savedRecord) => {
          if (!savedRecord?.audioUrl) {
            return;
          }
          updateStoredAudioRecord(record.id, savedRecord.audioUrl);
          setAudioRecords((currentRecords) =>
            currentRecords.map((currentRecord) =>
              currentRecord.id === record.id
                ? { ...currentRecord, audioUrl: savedRecord.audioUrl }
                : currentRecord,
            ),
          );
        })
        .catch((error) => {
          console.error("Failed to save audio record to database:", error);
        });
    }
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

  return (
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
        />
      )}
      {currentPage === "student-stories" && activeRole === "student" && (
        <MyStoriesPage
          records={audioRecords}
          onDeleteRecord={deleteAudioRecord}
          onPracticeImage={handlePracticeImage}
          mode="student"
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
        />
      )}
      {currentPage === "teacher-image-builder" && activeRole === "teacher" && (
        <TeacherImageBuilderPage />
      )}
    </div>
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
