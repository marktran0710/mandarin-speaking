import { useState } from "react";
import type { VocabQuizAttempt } from "../services/database";
import DashboardStat from "./DashboardStat";

/** Class-wide quiz totals under the roster table. The trend chart and the
 * missed-words list were cut — per-student accuracy and missed words already
 * live on the roster and the student profile, so this panel now answers just
 * one question: how many attempts, how accurate, for this filter. */
export default function QuizAnalyticsPanel({
  attempts,
  loadError,
}: {
  attempts: VocabQuizAttempt[];
  loadError: string;
}) {
  // One filter, not three. Date range and quiz mode were cut: teachers ask
  // "how is this student doing", never "how did tier 2 go in the last 7 days".
  const [studentFilter, setStudentFilter] = useState("all");

  if (loadError) {
    return (
      <section className="teacher-panel teacher-quiz-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Vocabulary quiz analytics</p>
            <h2>Quiz Analytics</h2>
          </div>
        </div>
        <p className="teacher-form-error">{loadError}</p>
      </section>
    );
  }

  if (attempts.length === 0) {
    return (
      <section className="teacher-panel teacher-quiz-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Vocabulary quiz analytics</p>
            <h2>Quiz Analytics</h2>
          </div>
        </div>
        <div className="teacher-empty-panel">
          <strong>No quiz attempts yet</strong>
          <p>Attempts and accuracy will appear here after students complete a vocabulary quiz.</p>
        </div>
      </section>
    );
  }

  const students = Array.from(new Set(attempts.map((a) => a.studentName))).sort();
  const filtered = studentFilter === "all"
    ? attempts
    : attempts.filter((a) => a.studentName === studentFilter);

  const totalQuestions = filtered.reduce((sum, a) => sum + a.totalQuestions, 0);
  const correctCount = filtered.reduce((sum, a) => sum + a.correctCount, 0);
  const overallAccuracy = totalQuestions > 0 ? Math.round((correctCount / totalQuestions) * 100) : 0;

  return (
    <>
      <section className="teacher-panel quiz-analytics-filters-panel">
        <div className="quiz-analytics-filters">
          <label>
            Student
            <select value={studentFilter} onChange={(e) => setStudentFilter(e.target.value)}>
              <option value="all">All students</option>
              {students.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {filtered.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No attempts for this student yet</strong>
          <p>Pick another student, or choose "All students".</p>
        </div>
      ) : (
        <section className="teacher-stat-grid" aria-label="Quiz analytics overview">
          <DashboardStat
            label="Quiz attempts"
            value={String(filtered.length)}
            note="Completed vocabulary quiz sessions"
          />
          <DashboardStat
            label="Overall accuracy"
            value={`${overallAccuracy}%`}
            note={`${correctCount}/${totalQuestions} questions correct`}
          />
        </section>
      )}
    </>
  );
}
