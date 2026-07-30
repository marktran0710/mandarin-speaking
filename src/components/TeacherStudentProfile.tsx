import DashboardStat from "./DashboardStat";
import { AccuracyTimeChart, FluencyToneTimeChart } from "./MyStoriesCharts";
import type { AudioRecord } from "../pages/MyStoriesPage";
import type { VocabQuizAttempt } from "../services/database";
import { getTopicLabel, quizAttemptAccuracy } from "../utils/myStoriesUtils";
import type { StudentAssessment } from "../utils/studentAssessment";

function score(value: number | null, suffix = "") {
  return value === null ? "--" : `${value}${suffix}`;
}

export default function TeacherStudentProfile({
  assessment,
  attempts,
  records,
  onClose,
}: {
  assessment: StudentAssessment;
  attempts: VocabQuizAttempt[];
  records: AudioRecord[];
  onClose: () => void;
}) {
  const studentAttempts = attempts
    .filter((attempt) => attempt.studentId === assessment.studentId)
    .sort((a, b) => new Date(a.completedAt).getTime() - new Date(b.completedAt).getTime());
  const studentRecords = records
    .filter((record) => record.studentId === assessment.studentId && record.praatMetrics)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  const accuracyPoints = studentAttempts.map((attempt) => ({
    label: new Date(attempt.completedAt).toLocaleDateString(),
    value: quizAttemptAccuracy(attempt),
  }));
  const speakingPoints = studentRecords.map((record) => ({
    label: new Date(record.timestamp).toLocaleDateString(),
    fluency: record.praatMetrics?.fluency_score ?? 0,
    tone: record.praatMetrics?.tone_accuracy ?? 0,
  }));

  return (
    <div className="student-profile-view">
      <section className="teacher-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Student profile</p>
            <h2>{assessment.studentName}</h2>
          </div>
          <button type="button" className="btn btn-small btn-secondary" onClick={onClose}>
            Back to students
          </button>
        </div>
        <section className="teacher-stat-grid" aria-label={`${assessment.studentName} overall snapshot`}>
          <DashboardStat
            label="Quiz accuracy"
            value={score(assessment.quiz.accuracyPct, "%")}
            note={`${assessment.quiz.attemptCount} quiz attempt${assessment.quiz.attemptCount === 1 ? "" : "s"}`}
          />
          <DashboardStat
            label="Recordings"
            value={String(assessment.speaking.recordingCount)}
            note="Roster-linked speaking attempts"
          />
          <DashboardStat
            label="Last activity"
            value={assessment.activity.lastActivityAt ? new Date(assessment.activity.lastActivityAt).toLocaleDateString() : "--"}
            note={assessment.activity.lastActivityAt ? "Quiz, recording, or submission" : "No linked activity yet"}
          />
        </section>
      </section>

      <section className="teacher-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Vocabulary quiz</p>
            <h2>Quiz progress</h2>
          </div>
        </div>
        <div className="student-profile-grid">
          <div>
            <h3>Stars by story</h3>
            {assessment.quiz.tierAttemptStoryIds.length === 0 ? (
              <p className="roster-status">No tier attempts linked to this student yet.</p>
            ) : (
              <div className="student-profile-list">
                {assessment.quiz.tierAttemptStoryIds.map((storyId) => (
                  <div key={storyId}>
                    <span>{getTopicLabel(storyId)}</span>
                    <strong>{"★".repeat(assessment.quiz.starsByStory[storyId] ?? 0) || "—"}</strong>
                  </div>
                ))}
              </div>
            )}
            <h3>Top missed words</h3>
            {assessment.quiz.topMissedWords.length === 0 ? (
              <p className="roster-status">No missed words recorded.</p>
            ) : (
              <div className="student-profile-list">
                {assessment.quiz.topMissedWords.map((word) => (
                  <div key={word.word}>
                    <strong lang="zh-Hant">{word.word}</strong>
                    <span>missed {word.timesMissed}/{word.timesAsked}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="quiz-analytics-chart-card">
            <h3>Accuracy over time</h3>
            {accuracyPoints.length === 0 ? (
              <p className="quiz-analytics-empty-note">No quiz attempts linked to this student yet.</p>
            ) : <AccuracyTimeChart points={accuracyPoints} />}
          </div>
        </div>
      </section>

      <section className="teacher-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Speaking practice</p>
            <h2>Speaking progress</h2>
          </div>
        </div>
        {assessment.speaking.recordingCount === 0 ? (
          <div className="teacher-empty-panel">
            <strong>No speaking recordings linked to this student yet</strong>
          </div>
        ) : (
          <>
            <section className="teacher-stat-grid" aria-label={`${assessment.studentName} speaking snapshot`}>
              <DashboardStat label="Avg. fluency" value={score(assessment.speaking.avgFluencyScore, "/100")} note="Praat fluency score" />
              <DashboardStat label="Avg. tone accuracy" value={score(assessment.speaking.avgToneAccuracy, "%")} note="Praat tone accuracy" />
              <DashboardStat label="Avg. AI feedback" value={score(assessment.speaking.avgAiFeedbackScore, "/100")} note="Available feedback dimensions" />
            </section>
            <div className="quiz-analytics-chart-card">
              <h3>Fluency and tone over time</h3>
              {speakingPoints.length === 0 ? (
                <p className="quiz-analytics-empty-note">No analyzed speaking recordings linked to this student yet.</p>
              ) : <FluencyToneTimeChart points={speakingPoints} />}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
