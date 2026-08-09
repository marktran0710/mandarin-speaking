import { useCallback, useEffect, useMemo, useState } from "react";
import {
  canUseDatabase,
  HelpRequest,
  listStorySubmissions,
  listStudents,
  listVocabQuizAttempts,
  type Student,
  type StorySubmission,
  type VocabQuizAttempt,
} from "../services/database";
import type { AudioRecord } from "./MyStoriesPage";
import TeacherShell, { type TeacherView } from "../components/teacher/TeacherShell";
import StoryBuilderSection from "../components/teacher/StoryBuilderSection";
import TeacherHelpQueue from "../components/TeacherHelpQueue";
import TeacherRosterView from "../components/TeacherRosterView";
import TeacherRecordingsView from "../components/TeacherRecordingsView";
import TeacherSubmissionsView from "../components/TeacherSubmissionsView";
import QuizAnalyticsPanel from "../components/QuizAnalyticsPanel";
import RecordingAnalyticsPanel from "../components/RecordingAnalyticsPanel";
import TeacherStarBoard from "../components/TeacherStarBoard";
import TeacherStudentProfile from "../components/TeacherStudentProfile";
import TeacherWatchlist from "../components/TeacherWatchlist";
import DashboardStat from "../components/DashboardStat";
import TeacherImageBuilderPage from "./TeacherImageBuilderPage";
import TeacherQuizReviewPage from "./TeacherQuizReviewPage";
import TeacherPracticeDebugPage from "./TeacherPracticeDebugPage";
import TeacherBenchmarkPage from "./TeacherBenchmarkPage";
import { formatRequestTime, getAverageMetric } from "../utils/myStoriesUtils";
import { buildStudentAssessments } from "../utils/studentAssessment";
// Legacy view internals (panels, tables, builder form) still live in the
// shared stylesheet; the shell + overview styles are in the two new files.
import "./MyStoriesPage.css";
import "./TeacherDashboardPage.css";

/** Sub-tab definitions for the merged sidebar sections. */
type RecordingsHelpTab = "recordings" | "help";
type MaterialsTab = "builder" | "imageBuilder" | "quizReview";
type AnalyticsTab = "students" | "quizTrends" | "recordingTrends";

const VIEW_COPY: Record<TeacherView, { eyebrow: string; title: string; description: string }> = {
  overview: {
    eyebrow: "Teacher workspace",
    title: "Class Overview",
    description: "A calm snapshot of what needs your attention today.",
  },
  submissions: {
    eyebrow: "Review student work",
    title: "Story Submissions",
    description: "Read completed story runs and give students clear next steps.",
  },
  recordingsHelp: {
    eyebrow: "Listen and support",
    title: "Recordings & Help",
    description: "Review recordings, then respond to students who need you.",
  },
  materials: {
    eyebrow: "Plan the next lesson",
    title: "Teaching Materials",
    description: "Build stories, prepare images, and check quiz material before publishing.",
  },
  students: {
    eyebrow: "Know your class",
    title: "Students",
    description: "Follow progress and keep your class list up to date.",
  },
  analytics: {
    eyebrow: "Spot patterns early",
    title: "Learning Insights",
    description: "Use class trends to decide what to revisit next.",
  },
  practiceDebug: {
    eyebrow: "Inspect the scoring pipeline",
    title: "Practice Stage Debugger",
    description: "Trace one student attempt through ASR, Praat, AI feedback, rubrics, and progression gates.",
  },
  benchmark: {
    eyebrow: "Validate against expert ratings",
    title: "External Benchmark",
    description: "Measure our tone scoring against the OMPAL expert-rated corpus, and against how well those experts agree with each other.",
  },
};

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
  totalRecordCount = records.length,
  hasMoreAudioRecords = false,
  onDeleteRecord,
  onLoadMoreAudioRecords,
  helpRequests,
  onResolveHelpRequest,
  onRefreshRecords,
  onLogout,
  onStorySaved,
}: {
  records: AudioRecord[];
  totalRecordCount?: number;
  hasMoreAudioRecords?: boolean;
  onDeleteRecord: (id: string) => void;
  onLoadMoreAudioRecords?: () => Promise<void>;
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  onRefreshRecords?: () => Promise<void>;
  onLogout: () => void;
  onStorySaved?: () => void;
}) {
  const [activeView, setActiveView] = useState<TeacherView>("overview");
  const [recordingsHelpTab, setRecordingsHelpTab] = useState<RecordingsHelpTab>("recordings");
  const [materialsTab, setMaterialsTab] = useState<MaterialsTab>("builder");
  // A nonce (not just the lesson number) so clicking "Go to Quiz Review"
  // twice for the same lesson still re-triggers the jump on the second click.
  const [quizReviewJump, setQuizReviewJump] = useState<{ lessonNumber: number | null; nonce: number } | null>(
    null,
  );
  const [analyticsTab, setAnalyticsTab] = useState<AnalyticsTab>("students");
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
  const [students, setStudents] = useState<Student[]>([]);
  const [studentsError, setStudentsError] = useState("");
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);

  const loadQuizAttempts = useCallback(async () => {
    if (!canUseDatabase()) return;
    setQuizAttemptsError("");
    try {
      setQuizAttempts(await listVocabQuizAttempts());
    } catch {
      setQuizAttemptsError("Could not load vocabulary quiz analytics.");
    }
  }, []);

  const loadStudents = useCallback(async () => {
    if (!canUseDatabase()) return;
    setStudentsError("");
    try {
      setStudents(await listStudents());
    } catch {
      setStudentsError("Could not load the student roster for analytics.");
    }
  }, []);

  useEffect(() => {
    if (activeView !== "analytics") return;
    loadQuizAttempts();
    loadStudents();
  }, [activeView, loadQuizAttempts, loadStudents]);

  const stableRecords = useMemo(
    () => records.filter((record) => (record.praatMetrics?.analysis_version ?? "stable_v1") === "stable_v1"),
    [records],
  );
  const assessments = useMemo(
    () => buildStudentAssessments(students, quizAttempts, stableRecords, submissions),
    [students, quizAttempts, stableRecords, submissions],
  );
  const selectedAssessment = assessments.find((assessment) => assessment.studentId === selectedStudentId) ?? null;

  const analyzedRecords = stableRecords.filter((record) => record.praatMetrics);
  const feedbackReadyRecords = stableRecords.filter(
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
  const viewCopy = VIEW_COPY[activeView];
  const isQuizReview = activeView === "materials" && materialsTab === "quizReview";

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
              await Promise.all([onRefreshRecords(), loadQuizAttempts(), loadStudents()]);
              setRefreshing(false);
            }
          : undefined
      }
      onLogout={onLogout}
    >
      <div className="teacher-dashboard-page tdash-workspace">
        {!isQuizReview && <header className="tdash-view-header">
          <div>
            <p className="tdash-view-kicker">{viewCopy.eyebrow}</p>
            <h1>{viewCopy.title}</h1>
            <p className="tdash-view-description">{viewCopy.description}</p>
          </div>
          {activeView === "overview" && (
            <div className="tdash-view-summary">
              <span>Today</span>
              <strong>{new Date().toLocaleDateString(undefined, { month: "short", day: "numeric" })}</strong>
              <small>{openHelpRequests.length} open help request{openHelpRequests.length === 1 ? "" : "s"}</small>
            </div>
          )}
        </header>}

        {activeView === "overview" && (
          <>
            <section className="teacher-stat-grid" aria-label="Class overview">
              <DashboardStat
                label="Recordings"
                value={String(totalRecordCount)}
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
          <TeacherSubmissionsView
            submissions={submissions}
            onReviewUpdate={(updated) =>
              setSubmissions((previous) =>
                previous.map((submission) =>
                  submission.id === updated.id ? updated : submission,
                ),
              )
            }
          />
        )}

        {activeView === "recordingsHelp" && (
          <>
            <SubTabs
              ariaLabel="Recordings and help"
              tabs={[
                { id: "recordings" as const, label: "Recordings", count: totalRecordCount },
                { id: "help" as const, label: "Help requests", count: openHelpRequests.length },
              ]}
              active={recordingsHelpTab}
              onSelect={setRecordingsHelpTab}
            />
            {recordingsHelpTab === "recordings" ? (
              <TeacherRecordingsView
                records={records}
                hasMoreRecords={hasMoreAudioRecords}
                onDeleteRecord={onDeleteRecord}
                onLoadMoreRecords={onLoadMoreAudioRecords}
              />
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
              <StoryBuilderSection
                onStorySaved={onStorySaved}
                onGoToQuizReview={(lessonNumber) => {
                  setQuizReviewJump({ lessonNumber, nonce: Date.now() });
                  setMaterialsTab("quizReview");
                }}
              />
            )}
            {materialsTab === "imageBuilder" && <TeacherImageBuilderPage />}
            {materialsTab === "quizReview" && <TeacherQuizReviewPage jumpToLesson={quizReviewJump} />}
          </>
        )}

        {activeView === "students" && <TeacherRosterView />}

        {activeView === "analytics" && (
          <>
            <SubTabs
              ariaLabel="Analytics"
              tabs={[
                { id: "students" as const, label: "Students", count: assessments.filter((assessment) => assessment.watchlistReasons.length > 0).length },
                { id: "quizTrends" as const, label: "Quiz trends", count: quizAttempts.length },
                { id: "recordingTrends" as const, label: "Recording trends", count: feedbackReadyRecords.length },
              ]}
              active={analyticsTab}
              onSelect={setAnalyticsTab}
            />
            {analyticsTab === "students" && (
              selectedAssessment ? (
                <TeacherStudentProfile
                  assessment={selectedAssessment}
                  attempts={quizAttempts}
                  records={stableRecords}
                  onClose={() => setSelectedStudentId(null)}
                />
              ) : (
                <>
                  {studentsError && <p className="teacher-form-error">{studentsError}</p>}
                  <TeacherWatchlist assessments={assessments} onSelectStudent={setSelectedStudentId} />
                  <TeacherStarBoard assessments={assessments} />
                  <section className="teacher-panel">
                    <div className="teacher-panel-header">
                      <div>
                        <p className="stories-kicker">Class roster</p>
                        <h2>All students</h2>
                      </div>
                      <span className="queue-count">{assessments.length}</span>
                    </div>
                    {assessments.length === 0 ? (
                      <div className="teacher-empty-panel">
                        <strong>No students in the roster yet</strong>
                        <p>Add students from the Students section to see their linked assessment history here.</p>
                      </div>
                    ) : (
                      <div className="student-assessment-list">
                        {assessments.map((assessment) => (
                          <button
                            type="button"
                            className="student-assessment-row"
                            key={assessment.studentId}
                            onClick={() => setSelectedStudentId(assessment.studentId)}
                          >
                            <strong>{assessment.studentName}</strong>
                            <span>
                              {assessment.quiz.accuracyPct === null
                                ? "No quiz attempts yet"
                                : `${assessment.quiz.accuracyPct}% quiz accuracy`}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </section>
                </>
              )
            )}
            {analyticsTab === "quizTrends" && (
              <QuizAnalyticsPanel attempts={quizAttempts} loadError={quizAttemptsError} />
            )}
            {analyticsTab === "recordingTrends" && (
              <RecordingAnalyticsPanel records={records} />
            )}
          </>
        )}

        {activeView === "practiceDebug" && <TeacherPracticeDebugPage records={records} />}
        {activeView === "benchmark" && <TeacherBenchmarkPage />}
      </div>
    </TeacherShell>
  );
}
