import { useState, useEffect } from "react";
import HomePage from "./pages/HomePage";
import CreateStoryPage from "./pages/CreateStoryPage";
import MyStoriesPage from "./pages/MyStoriesPage";
import LoginPage, { LoginRole } from "./pages/LoginPage";
import Navigation from "./components/Navigation";

export type Page =
  | "home"
  | "student-login"
  | "teacher-login"
  | "student-practice"
  | "student-stories"
  | "teacher-dashboard";

interface AudioRecord {
  id: string;
  audioBlob: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  model: "openai" | "gemini" | "webspeech";
  praatMetrics?: any;
  topicId?: string;
  imageUrl?: string;
  imageIndex?: number;
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
    const storedRole = localStorage.getItem("activeRole");
    if (storedRole === "student" || storedRole === "teacher") {
      setActiveRole(storedRole);
      setCurrentPage(
        storedRole === "student" ? "student-practice" : "teacher-dashboard",
      );
    }

    const stored = localStorage.getItem("audioRecords");
    if (stored) {
      try {
        const recordsData = JSON.parse(stored);
        setAudioRecords(
          recordsData.map((data: any) => ({
            ...data,
            audioBlob: new Blob([], { type: "audio/webm" }),
          })),
        );
      } catch (e) {
        console.error("Failed to load audio records:", e);
      }
    }
  }, []);

  const addAudioRecord = (record: AudioRecord) => {
    setAudioRecords((prev) => [record, ...prev]);
    const audioData = {
      id: record.id,
      timestamp: record.timestamp,
      duration: record.duration,
      transcription: record.transcription,
      model: record.model,
      topicId: record.topicId,
      imageUrl: record.imageUrl,
      imageIndex: record.imageIndex,
      praatMetrics: record.praatMetrics,
    };
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    localStorage.setItem(
      "audioRecords",
      JSON.stringify([audioData, ...stored]),
    );
  };

  const deleteAudioRecord = (id: string) => {
    setAudioRecords((prev) => prev.filter((record) => record.id !== id));
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    const updated = stored.filter((record: any) => record.id !== id);
    localStorage.setItem("audioRecords", JSON.stringify(updated));
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
      {currentPage === "teacher-dashboard" && activeRole === "teacher" && (
        <MyStoriesPage
          records={audioRecords}
          onDeleteRecord={deleteAudioRecord}
          mode="teacher"
        />
      )}
    </div>
  );
}
