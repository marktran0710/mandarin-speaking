import { useCallback, useEffect, useState } from "react";
import TeacherDashboardPage from "./pages/TeacherDashboardPage";
import LoginPage from "./pages/LoginPage";
import Navigation from "./components/Navigation";
import ErrorBoundary from "./components/ErrorBoundary";
import { currentRole, signOut } from "./utils/session";
import {
  canUseDatabase,
  deleteAudioRecordFromDatabase,
  getAudioRecordCount,
  HelpRequest,
  listAudioRecords,
  listHelpRequests,
  logoutTeacher,
  resolveHelpRequest,
  StoredAudioRecord,
} from "./services/database";

export default function TeacherApp() {
  const [activeRole, setActiveRole] = useState<"teacher" | null>(null);
  const [audioRecords, setAudioRecords] = useState<StoredAudioRecord[]>([]);
  const [audioRecordCount, setAudioRecordCount] = useState(0);
  const [audioRecordPageSize] = useState(100);
  const [helpRequests, setHelpRequests] = useState<HelpRequest[]>([]);

  const loadSavedAudioRecords = useCallback(async () => {
    if (!canUseDatabase()) return;
    try {
      const [records, total] = await Promise.all([
        listAudioRecords({ limit: audioRecordPageSize }),
        getAudioRecordCount(),
      ]);
      setAudioRecords(records);
      setAudioRecordCount(total);
    } catch (error) {
      console.error("Failed to load audio records from database:", error);
    }
  }, [audioRecordPageSize]);

  useEffect(() => {
    const role = currentRole("teacher");
    if (role === "teacher") {
      setActiveRole("teacher");
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
    setAudioRecordCount((count) => Math.max(0, count - 1));
    if (canUseDatabase()) {
      deleteAudioRecordFromDatabase(id).catch((error) => {
        console.error("Failed to delete audio record from database:", error);
        loadSavedAudioRecords();
      });
    }
  };

  const loadMoreAudioRecords = useCallback(async () => {
    if (!canUseDatabase() || audioRecords.length >= audioRecordCount) return;
    try {
      const records = await listAudioRecords({
        limit: audioRecordPageSize,
        skip: audioRecords.length,
      });
      setAudioRecords((currentRecords) => [...currentRecords, ...records]);
    } catch (error) {
      console.error("Failed to load more audio records from database:", error);
    }
  }, [audioRecordCount, audioRecordPageSize, audioRecords.length]);

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
    // LoginPage has already written the session; this only reacts to it.
    setActiveRole("teacher");
  };

  const handleLogout = () => {
    setActiveRole(null);
    signOut("teacher");
    void logoutTeacher().catch(() => {
      // Local role state is already cleared; the student app has its own
      // independent session cookie.
    });
  };

  // Logged-in teachers get the admin shell (its sidebar is the only nav);
  // the top Navigation bar only remains on the login screen.
  return (
    <ErrorBoundary>
      {activeRole === "teacher" ? (
        <TeacherDashboardPage
          records={audioRecords}
          totalRecordCount={audioRecordCount}
          hasMoreAudioRecords={audioRecords.length < audioRecordCount}
          onDeleteRecord={deleteAudioRecord}
          onLoadMoreAudioRecords={loadMoreAudioRecords}
          helpRequests={helpRequests}
          onResolveHelpRequest={handleResolveHelpRequest}
          onRefreshRecords={loadSavedAudioRecords}
          onLogout={handleLogout}
        />
      ) : (
        <div className="app-container">
          <Navigation
            currentPage="teacher-login"
            activeRole={null}
            // This app has no in-page router, so the logo's only sensible
            // destination is the teacher app root — a no-op here made the
            // logo look broken.
            onNavigate={() => {
              window.location.href = `${import.meta.env.BASE_URL}teacher.html`;
            }}
            onLogout={handleLogout}
            appVariant="teacher"
          />
          {/* No `onBack`: the teacher site deliberately has no route to the
              student site. The back button used to jump to BASE_URL, which
              was the third door between the two modes. */}
          <LoginPage role="teacher" onLogin={handleLogin} />
        </div>
      )}
    </ErrorBoundary>
  );
}
