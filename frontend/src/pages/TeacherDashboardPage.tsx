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
import ManagementShell from "../components/management/ManagementShell";
import Icon from "../shared/ui/Icon";
import TeacherHelpQueue from "../components/teacher/TeacherHelpQueue";
import TeacherRecordingsView from "../components/teacher/TeacherRecordingsView";
import TeacherSubmissionsView from "../components/teacher/TeacherSubmissionsView";
import QuizAnalyticsPanel from "../components/teacher/QuizAnalyticsPanel";
import RecordingAnalyticsPanel from "../components/RecordingAnalyticsPanel";
import TeacherRosterTable from "../components/teacher/TeacherRosterTable";
import TeacherStudentProfile from "../components/teacher/TeacherStudentProfile";
import { buildStudentAssessments } from "../utils/studentAssessment";
// Legacy view internals (panels, tables, builder form) still live in the
// shared stylesheet; the shell + workspace styles are in the two new files.
import "./MyStoriesPage.css";
import "./TeacherDashboardPage.css";

export type TeacherView = "today" | "submissions" | "students";

export default function TeacherDashboardPage({
  records,
  hasMoreAudioRecords = false,
  onDeleteRecord,
  onLoadMoreAudioRecords,
  helpRequests,
  onResolveHelpRequest,
  onRefreshRecords,
  onLogout,
  initialView = "today",
}: {
  records: AudioRecord[];
  hasMoreAudioRecords?: boolean;
  onDeleteRecord: (id: string) => void;
  onLoadMoreAudioRecords?: () => Promise<void>;
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  onRefreshRecords?: () => Promise<void>;
  onLogout: () => void;
  initialView?: TeacherView;
}) {
  const [activeView, setActiveView] = useState<TeacherView>(initialView);
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
      setStudentsError("Could not load the student roster.");
    }
  }, []);

  useEffect(() => {
    if (activeView !== "students") return;
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
  const selectedAssessment =
    assessments.find((assessment) => assessment.studentId === selectedStudentId) ?? null;

  const openHelpRequests = helpRequests.filter((request) => request.status === "open");
  const pendingSubmissions = submissions.filter((submission) => submission.reviewStatus !== "reviewed");
  const selectView = (view: TeacherView) => {
    setActiveView(view);
  };

  return (
    <ManagementShell
      role="teacher"
      activeView={activeView}
      onSelectView={(view) => selectView(view as TeacherView)}
      submissionCount={pendingSubmissions.length}
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
        {activeView === "today" && (
          <>
            <TeacherHelpQueue helpRequests={helpRequests} onResolveHelpRequest={onResolveHelpRequest} />
            <button type="button" className="tdash-next-up" onClick={() => setActiveView("submissions")}>
              <Icon name="inbox" size={18} />
              <span>
                {pendingSubmissions.length === 0
                  ? "No work waiting to be marked"
                  : `${pendingSubmissions.length} submission${
                      pendingSubmissions.length === 1 ? "" : "s"
                    } waiting to be marked`}
              </span>
              <em>Open submissions</em>
            </button>
          </>
        )}

        {activeView === "submissions" && (
          <>
            <TeacherSubmissionsView
              submissions={submissions}
              onReviewUpdate={(updated) =>
                setSubmissions((previous) =>
                  previous.map((submission) => (submission.id === updated.id ? updated : submission)),
                )
              }
            />
            <TeacherRecordingsView
              records={records}
              hasMoreRecords={hasMoreAudioRecords}
              onDeleteRecord={onDeleteRecord}
              onLoadMoreRecords={onLoadMoreAudioRecords}
            />
            <RecordingAnalyticsPanel records={records} />
          </>
        )}

        {activeView === "students" &&
          (selectedAssessment ? (
            <TeacherStudentProfile
              assessment={selectedAssessment}
              attempts={quizAttempts}
              records={stableRecords}
              onClose={() => setSelectedStudentId(null)}
            />
          ) : (
            <>
              {studentsError && <p className="teacher-form-error">{studentsError}</p>}
              <TeacherRosterTable assessments={assessments} onSelectStudent={setSelectedStudentId} />
              <QuizAnalyticsPanel attempts={quizAttempts} loadError={quizAttemptsError} />
            </>
          ))}

      </div>
    </ManagementShell>
  );
}
