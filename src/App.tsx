import { useState, useEffect } from "react";
import HomePage from "./pages/HomePage";
import CreateStoryPage from "./pages/CreateStoryPage";
import MyStoriesPage from "./pages/MyStoriesPage";
import Navigation from "./components/Navigation";

export type Page = "home" | "create" | "mystories";

interface AudioRecord {
  id: string;
  audioBlob: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  model: "openai" | "gemini" | "webspeech";
  praatMetrics?: any;
  topicId?: string;
}

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("home");
  const [audioRecords, setAudioRecords] = useState<AudioRecord[]>([]);

  useEffect(() => {
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
      praatMetrics: record.praatMetrics
        ? {
            detected_tone: record.praatMetrics.detected_tone,
            tone_accuracy: record.praatMetrics.tone_accuracy,
            speech_rate: record.praatMetrics.speech_rate,
            fluency_score: record.praatMetrics.fluency_score,
          }
        : undefined,
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

  return (
    <div className="app-container">
      <Navigation currentPage={currentPage} onNavigate={setCurrentPage} />
      {currentPage === "home" && <HomePage onNavigate={setCurrentPage} />}
      {currentPage === "create" && (
        <CreateStoryPage onAddRecord={addAudioRecord} />
      )}
      {currentPage === "mystories" && (
        <MyStoriesPage
          records={audioRecords}
          onDeleteRecord={deleteAudioRecord}
        />
      )}
    </div>
  );
}
