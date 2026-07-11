import { useCallback, useEffect, useState } from "react";
import MyStoriesPage from "./pages/MyStoriesPage";
import TeacherImageBuilderPage from "./pages/TeacherImageBuilderPage";
import LoginPage from "./pages/LoginPage";
import Navigation from "./components/Navigation";
import ErrorBoundary from "./components/ErrorBoundary";
import {
  canUseDatabase,
  deleteAudioRecordFromDatabase,
  HelpRequest,
  listAudioRecords,
  listHelpRequests,
  resolveHelpRequest,
  StoredAudioRecord,
} from "./services/database";
import type { Page } from "./types/page";

type TeacherPage = Extract<Page, "teacher-login" | "teacher-dashboard" | "teacher-image-builder">;

export default function TeacherApp() {
  const [currentPage, setCurrentPage] = useState<TeacherPage>("teacher-login");
  const [activeRole, setActiveRole] = useState<"teacher" | null>(null);
  const [audioRecords, setAudioRecords] = useState<StoredAudioRecord[]>([]);
  const [helpRequests, setHelpRequests] = useState<HelpRequest[]>([]);

  const loadSavedAudioRecords = useCallback(async () => {
    if (!canUseDatabase()) return;
    try {
      setAudioRecords(await listAudioRecords());
    } catch (error) {
      console.error("Failed to load audio records from database:", error);
    }
  }, []);

  useEffect(() => {
    if (localStorage.getItem("activeRole") === "teacher") {
      setActiveRole("teacher");
      setCurrentPage("teacher-dashboard");
    }
    loadSavedAudioRecords();
  }, [loadSavedAudioRecords]);

  useEffect(() => {
    const loadSavedHelpRequests = async () => {
      if (!canUseDatabase()) return;
      try {
        setHelpRequests(await listHelpRequests());
      } catch (error) {
        console.error("Failed to load help requests from database:", error);
      }
    };

    loadSavedHelpRequests();
    if (!canUseDatabase()) return;
    const intervalId = window.setInterval(loadSavedHelpRequests, 5000);
    return () => window.clearInterval(intervalId);
  }, []);

  const deleteAudioRecord = (id: string) => {
    setAudioRecords((prev) => prev.filter((record) => record.id !== id));
    if (canUseDatabase()) {
      deleteAudioRecordFromDatabase(id).catch((error) => {
        console.error("Failed to delete audio record from database:", error);
      });
    }
  };

  const handleResolveHelpRequest = (id: string) => {
    const resolvedAt = new Date().toISOString();
    setHelpRequests((requests) =>
      requests.map((request) =>
        request.id === id ? { ...request, status: "resolved", resolvedAt } : request,
      ),
    );
    if (canUseDatabase()) {
      resolveHelpRequest(id)
        .then((savedRequest) => {
          setHelpRequests((requests) =>
            requests.map((request) => (request.id === id ? savedRequest : request)),
          );
        })
        .catch((error) => {
          console.error("Failed to resolve help request in database:", error);
        });
    }
  };

  const handleLogin = () => {
    setActiveRole("teacher");
    localStorage.setItem("activeRole", "teacher");
    setCurrentPage("teacher-dashboard");
  };

  const handleLogout = () => {
    setActiveRole(null);
    setCurrentPage("teacher-login");
    localStorage.removeItem("activeRole");
    localStorage.removeItem("teacherSession");
  };

  return (
    <ErrorBoundary>
      <div className="app-container">
        <Navigation
          currentPage={currentPage}
          activeRole={activeRole}
          onNavigate={(page) => setCurrentPage(page as TeacherPage)}
          onLogout={handleLogout}
          appVariant="teacher"
        />
        {currentPage === "teacher-login" && (
          <LoginPage
            role="teacher"
            onLogin={handleLogin}
            onBack={() => {
              window.location.href = import.meta.env.BASE_URL;
            }}
          />
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
