import { useEffect, useState } from "react";
import {
  canUseDatabase,
  HelpRequest,
  listStorySubmissions,
  listVocabQuizAttempts,
  type StorySubmission,
  type VocabQuizAttempt,
} from "../services/database";
import type { AudioRecord } from "./MyStoriesPage";
import TeacherShell, { type TeacherView } from "../components/teacher/TeacherShell";
import StoryBuilderSection from "../components/teacher/StoryBuilderSection";
import TeacherHelpQueue from "../components/TeacherHelpQueue";
import TeacherProgressView from "../components/TeacherProgressView";
import TeacherRosterView from "../components/TeacherRosterView";
import TeacherInsightsView from "../components/TeacherInsightsView";
import TeacherRecordingsView from "../components/TeacherRecordingsView";
import TeacherSubmissionsView from "../components/TeacherSubmissionsView";
import QuizAnalyticsPanel from "../components/QuizAnalyticsPanel";
import RecordingAnalyticsPanel from "../components/RecordingAnalyticsPanel";
import DashboardStat from "../components/DashboardStat";
import TeacherImageBuilderPage from "./TeacherImageBuilderPage";
import TeacherQuizReviewPage from "./TeacherQuizReviewPage";
import { formatRequestTime, getAverageMetric } from "../utils/myStoriesUtils";
// Legacy view internals (panels, tables, builder form) still live in the
// shared stylesheet; the shell + overview styles are in the two new files.
import "./MyStoriesPage.css";
import "./TeacherDashboardPage.css";

/** Sub-tab definitions for the merged sidebar sections. */
type RecordingsHelpTab = "recordings" | "help";
type MaterialsTab = "builder" | "imageBuilder" | "quizReview";
type StudentsTab = "progress" | "roster";
type AnalyticsTab = "quiz" | "recordings" | "insights";

function SubTabs<Tab extends string>({
  tabs,
  active,
  onSelect,
  ariaLabel,
}: {
  tabs: Array<{ id: Tab; label: string; count?: number }>;
  active: Tab;
  onSelect: (tab: Tab) => void;
  ariaLabel: string;
}) {
  return (
    <div className="tdash-subtabs" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab) => (
        <button
          type="button"
          role="tab"
          key={tab.id}
          aria-selected={active === tab.id}
          className={active === tab.id ? "active" : ""}
          onClick={() => onSelect(tab.id)}
        >
          {tab.label}
          {tab.count !== undefined && tab.count > 0 && <strong>{tab.count}</strong>}
        </button>
      ))}
    </div>
  );
}

export default function TeacherDashboardPage({
  records,
  onDeleteRecord,
  helpRequests,
  onResolveHelpRequest,
  onRefreshRecords,
  onLogout,
  onStorySaved,
}: {
  records: AudioRecord[];
  onDeleteRecord: (id: string) => void;
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  onRefreshRecords?: () => Promise<void>;
  onLogout: () => void;
  onStorySaved?: () => void;
}) {
  const [activeView, setActiveView] = useState<TeacherView>("overview");
  const [recordingsHelpTab, setRecordingsHelpTab] = useState<RecordingsHelpTab>("recordings");
  const [materialsTab, setMaterialsTab] = useState<MaterialsTab>("builder");
  const [studentsTab, setStudentsTab] = useState<StudentsTab>("progress");
  const [analyticsTab, setAnalyticsTab] = useState<AnalyticsTab>("quiz");
  const [refreshing, setRefreshing] = useState(false);
  const [submissions, setSubmissions] = useState<StorySubmission[]>([]);

  useEffect(() => {
    if (!canUseDatabase()) return;
    listStorySubmissions().then(setSubmissions).catch(() => {});
  }, []);

  useEffect(() => {
    if (activeView !== "submissions" || !canUseDatabase()) return;
    listStorySubmissions().then(setSubmissions).catch(() => {});
  }, [activeView]);

  const [quizAttempts, setQuizAttempts] = useState<VocabQuizAttempt[]>([]);
  const [quizAttemptsError, setQuizAttemptsError] = useState("");

  useEffect(() => {
    if (activeView !== "analytics" || !canUseDatabase()) return;
    setQuizAttemptsError("");
    listVocabQuizAttempts()
      .then(setQuizAttempts)
      .catch(() => setQuizAttemptsError("Could not load vocabulary quiz analytics."));
  }, [activeView]);

  const analyzedRecords = records.filter((record) => record.praatMetrics);
  const feedbackReadyRecords = records.filter(
    (record) => record.praatMetrics?.ai_feedback,
  );
  const averageFluency = getAverageMetric(analyzedRecords, "fluency_score");
  const averageToneAccuracy = getAverageMetric(analyzedRecords, "tone_accuracy");
  const openHelpRequests = helpRequests.filter(
    (request) => request.status === "open",
  );
  const latestSubmissions = [...submissions]
    .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt))
    .slice(0, 5);

  const openHelpQueue = () => {
    setActiveView("recordingsHelp");
    setRecordingsHelpTab("help");
  };

  return (
    <TeacherShell
      activeView={activeView}
      onSelectView={setActiveView}
      submissionCount={submissions.length}
      openHelpCount={openHelpRequests.length}
      refreshing={refreshing}
      onRefresh={
        onRefreshRecords
          ? async () => {
              setRefreshing(true);
              await onRefreshRecords();
              setRefreshing(false);
            }
          : undefined
      }
      onLogout={onLogout}
    >
      <div className="teacher-dashboard-page tdash-workspace">
        {activeView === "overview" && (
          <>
            <header className="tdash-view-header">
              <div>
                <p className="stories-kicker">Teacher workspace</p>
                <h1>Class Overview</h1>
              </div>
              <span className="tdash-view-date">{new Date().toLocaleDateString()}</span>
            </header>

            <section className="teacher-stat-grid" aria-label="Class overview">
              <DashboardStat
                label="Recordings"
                value={String(records.length)}
                note="Total saved student attempts"
              />
              <DashboardStat
                label="Feedback ready"
                value={String(feedbackReadyRecords.length)}
                note="Gemini/Praat results available"
              />
              <DashboardStat
                label="Avg. fluency"
                value={averageFluency === null ? "--" : `${averageFluency}/100`}
                note="Based on analyzed recordings"
              />
              <DashboardStat
                label="Tone accuracy"
                value={averageToneAccuracy === null ? "--" : `${averageToneAccuracy}%`}
                note="Class pronunciation trend"
              />
            </section>

            <div className="tdash-overview-grid">
              <section className="teacher-panel tdash-overview-panel" aria-label="Latest submissions">
                <div className="tdash-overview-panel-header">
                  <h2>📥 Latest submissions</h2>
                  <button type="button" onClick={() => setActiveView("submissions")}>
                    View all →
                  </button>
                </div>
                {latestSubmissions.length === 0 ? (
                  <div className="teacher-empty-panel">
                    <strong>No submissions yet</strong>
                    <p>Completed story runs students send in will appear here.</p>
                  </div>
                ) : (
                  <ul className="tdash-overview-list">
                    {latestSubmissions.map((submission) => (
                      <li key={submission.id}>
                        <strong>{submission.studentName}</strong>
                        <span className="tdash-overview-detail">{submission.storyTitle}</span>
                        <span className="tdash-overview-meta">
                          {submission.scenes.length} scene{submission.scenes.length === 1 ? "" : "s"}
                          {" · "}
                          {new Date(submission.submittedAt).toLocaleDateString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="teacher-panel tdash-overview-panel" aria-label="Help queue">
                <div className="tdash-overview-panel-header">
                  <h2>✋ Help queue</h2>
                  <button type="button" onClick={openHelpQueue}>
                    Open →
                  </button>
                </div>
                {openHelpRequests.length === 0 ? (
                  <div className="teacher-empty-panel">
                    <strong>No raised hands</strong>
                    <p>Open help requests will appear here when students ask for support.</p>
                  </div>
                ) : (
                  <ul className="tdash-overview-list">
                    {openHelpRequests.map((request) => (
                      <li key={request.id}>
                        <strong>{request.studentName}</strong>
                        <span className="tdash-overview-detail">{request.message}</span>
                        <span className="tdash-overview-meta tdash-overview-wait">
                          {formatRequestTime(request.createdAt)}
                        </span>
                        {onResolveHelpRequest && (
                          <button
                            type="button"
                            className="tdash-resolve-btn"
                            onClick={() => onResolveHelpRequest(request.id)}
                          >
                            Mark helped
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          </>
        )}

        {activeView === "submissions" && (
          <TeacherSubmissionsView submissions={submissions} />
        )}

        {activeView === "recordingsHelp" && (
          <>
            <SubTabs
              ariaLabel="Recordings and help"
              tabs={[
                { id: "recordings" as const, label: "Recordings", count: records.length },
                { id: "help" as const, label: "Help requests", count: openHelpRequests.length },
              ]}
              active={recordingsHelpTab}
              onSelect={setRecordingsHelpTab}
            />
            {recordingsHelpTab === "recordings" ? (
              <TeacherRecordingsView records={records} onDeleteRecord={onDeleteRecord} />
            ) : (
              <TeacherHelpQueue
                helpRequests={helpRequests}
                onResolveHelpRequest={onResolveHelpRequest}
              />
            )}
          </>
        )}

        {activeView === "materials" && (
          <>
            <SubTabs
              ariaLabel="Teaching materials"
              tabs={[
                { id: "builder" as const, label: "Story Builder" },
                { id: "imageBuilder" as const, label: "AI Image Builder" },
                { id: "quizReview" as const, label: "Quiz Review" },
              ]}
              active={materialsTab}
              onSelect={setMaterialsTab}
            />
            {materialsTab === "builder" && (
              <StoryBuilderSection onStorySaved={onStorySaved} />
            )}
            {materialsTab === "imageBuilder" && <TeacherImageBuilderPage />}
            {materialsTab === "quizReview" && <TeacherQuizReviewPage />}
          </>
        )}

        {activeView === "students" && (
          <>
            <SubTabs
              ariaLabel="Students"
              tabs={[
                { id: "progress" as const, label: "Progress" },
                { id: "roster" as const, label: "Roster" },
              ]}
              active={studentsTab}
              onSelect={setStudentsTab}
            />
            {studentsTab === "progress" ? (
              <TeacherProgressView records={records} />
            ) : (
              <TeacherRosterView />
            )}
          </>
        )}

        {activeView === "analytics" && (
          <>
            <SubTabs
              ariaLabel="Analytics"
              tabs={[
                { id: "quiz" as const, label: "Quiz", count: quizAttempts.length },
                { id: "recordings" as const, label: "Recordings", count: feedbackReadyRecords.length },
                { id: "insights" as const, label: "Insights" },
              ]}
              active={analyticsTab}
              onSelect={setAnalyticsTab}
            />
            {analyticsTab === "quiz" && (
              <QuizAnalyticsPanel attempts={quizAttempts} loadError={quizAttemptsError} />
            )}
            {analyticsTab === "recordings" && (
              <RecordingAnalyticsPanel records={records} />
            )}
            {analyticsTab === "insights" && <TeacherInsightsView />}
          </>
        )}
      </div>
    </TeacherShell>
  );
}
