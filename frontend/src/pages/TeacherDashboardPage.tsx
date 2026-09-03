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
import Icon, { type UiIconName } from "../shared/ui/Icon";
import StoryBuilderSection from "../components/teacher/StoryBuilderSection";
import TeacherHelpQueue from "../components/TeacherHelpQueue";
import TeacherRecordingsView from "../components/TeacherRecordingsView";
import TeacherSubmissionsView from "../components/TeacherSubmissionsView";
import QuizAnalyticsPanel from "../components/QuizAnalyticsPanel";
import RecordingAnalyticsPanel from "../components/RecordingAnalyticsPanel";
import TeacherRosterTable from "../components/teacher/TeacherRosterTable";
import TeacherStudentProfile from "../components/TeacherStudentProfile";
import TeacherImageBuilderPage from "./TeacherImageBuilderPage";
import TeacherQuizReviewPage from "./TeacherQuizReviewPage";
import { buildStudentAssessments } from "../utils/studentAssessment";
// Legacy view internals (panels, tables, builder form) still live in the
// shared stylesheet; the shell + workspace styles are in the two new files.
import "./MyStoriesPage.css";
import "./TeacherDashboardPage.css";

/** The three material tools are separate full-screen workspaces, reached by
 * drilling in from the Materials list rather than through a permanent
 * sub-tab bar — Quiz Review already hid the page chrome whenever it opened. */
export type MaterialsTool = "builder" | "imageBuilder" | "quizReview";
export type TeacherView = "today" | "submissions" | "students" | "materials";

const MATERIALS_TOOLS: Array<{ id: MaterialsTool; icon: UiIconName; title: string; blurb: string }> = [
  {
    id: "builder",
    icon: "library",
    title: "Story Builder",
    blurb: "Write a story, set its scenes, and publish it to students.",
  },
  {
    id: "imageBuilder",
    icon: "image",
    title: "AI Image Builder",
    blurb: "Generate and attach scene images for a story you have written.",
  },
  {
    id: "quizReview",
    icon: "check",
    title: "Quiz Review",
    blurb: "Check generated quiz questions, then publish the approved set.",
  },
];

export default function TeacherDashboardPage({
  records,
  hasMoreAudioRecords = false,
  onDeleteRecord,
  onLoadMoreAudioRecords,
  helpRequests,
  onResolveHelpRequest,
  onRefreshRecords,
  onLogout,
  onStorySaved,
  initialView = "today",
  initialMaterialsTool,
}: {
  records: AudioRecord[];
  hasMoreAudioRecords?: boolean;
  onDeleteRecord: (id: string) => void;
  onLoadMoreAudioRecords?: () => Promise<void>;
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  onRefreshRecords?: () => Promise<void>;
  onLogout: () => void;
  onStorySaved?: () => void;
  initialView?: TeacherView;
  initialMaterialsTool?: MaterialsTool;
}) {
  const [activeView, setActiveView] = useState<TeacherView>(initialView);
  const [materialsTool, setMaterialsTool] = useState<MaterialsTool | null>(initialMaterialsTool ?? null);
  // A nonce (not just the lesson number) so clicking "Go to Quiz Review"
  // twice for the same lesson still re-triggers the jump on the second click.
  const [quizReviewJump, setQuizReviewJump] = useState<{ lessonNumber: number | null; nonce: number } | null>(
    null,
  );
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
  // The builders and Quiz Review take over the whole workspace once opened.
  const inMaterialsTool = activeView === "materials" && materialsTool !== null;

  const openTool = (tool: MaterialsTool) => {
    setActiveView("materials");
    setMaterialsTool(tool);
  };

  const selectView = (view: TeacherView) => {
    setActiveView(view);
    // Materials always opens on its tool list; drilling in is deliberate.
    if (view === "materials") setMaterialsTool(null);
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

        {activeView === "materials" && !inMaterialsTool && (
          <section className="tdash-card">
            <div className="tdash-card-head">
              <h2>Materials</h2>
            </div>
            <p className="tdash-card-note">Pick a tool. Each one opens on its own.</p>
            <div className="tdash-tool-list">
              {MATERIALS_TOOLS.map((tool) => (
                <button type="button" className="tdash-tool" key={tool.id} onClick={() => openTool(tool.id)}>
                  <Icon name={tool.icon} size={20} />
                  <span>
                    <strong>{tool.title}</strong>
                    <small>{tool.blurb}</small>
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {inMaterialsTool && (
          <>
            <button type="button" className="tdash-back" onClick={() => setMaterialsTool(null)}>
              Back to Materials
            </button>
            {materialsTool === "builder" && (
              <StoryBuilderSection
                onStorySaved={onStorySaved}
                onGoToQuizReview={(lessonNumber) => {
                  setQuizReviewJump({ lessonNumber, nonce: Date.now() });
                  setMaterialsTool("quizReview");
                }}
              />
            )}
            {materialsTool === "imageBuilder" && <TeacherImageBuilderPage />}
            {materialsTool === "quizReview" && <TeacherQuizReviewPage jumpToLesson={quizReviewJump} />}
          </>
        )}
      </div>
    </ManagementShell>
  );
}
