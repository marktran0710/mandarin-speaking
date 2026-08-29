import { useState } from "react";
import type { VocabQuizAttempt } from "../services/database";
import DashboardStat from "./DashboardStat";
import { AccuracyTimeChart } from "./MyStoriesCharts";
import {
  computeWordMissStats,
  quizAttemptAccuracy,
  summarizeWordMissTrends,
  wordMissSeverity,
  type WordMissSeverity,
} from "../utils/myStoriesUtils";

const WORD_SEVERITY_LABEL: Record<WordMissSeverity, string> = {
  critical: "Critical",
  watch: "Watch",
  ok: "OK",
};

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
          <p>Time spent, accuracy, and repeated mistakes will appear here after students complete a vocabulary quiz.</p>
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

  const allWordStats = computeWordMissStats(filtered);
  const wordStats = allWordStats.slice(0, 10);
  const wordMissInsight = summarizeWordMissTrends(allWordStats, wordStats.length);

  // One point per attempt when a single student is selected (a short-term
  // trend is visible); a single class-average-per-day line for "All
  // students" — never one line per student, which would need an unbounded
  // categorical palette for a whole classroom.
  const sortedByDate = [...filtered].sort(
    (a, b) => new Date(a.completedAt).getTime() - new Date(b.completedAt).getTime(),
  );
  const timeSeries = studentFilter !== "all"
    ? sortedByDate.map((a) => ({ label: new Date(a.completedAt).toLocaleDateString(), value: quizAttemptAccuracy(a) }))
    : (() => {
        const byDay = new Map<string, number[]>();
        sortedByDate.forEach((a) => {
          const day = new Date(a.completedAt).toLocaleDateString();
          byDay.set(day, [...(byDay.get(day) || []), quizAttemptAccuracy(a)]);
        });
        return Array.from(byDay.entries()).map(([day, values]) => ({
          label: day,
          value: Math.round(values.reduce((s, v) => s + v, 0) / values.length),
        }));
      })();

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
        <>
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

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Quiz trend</p>
                <h2>
                  {studentFilter === "all"
                    ? "Class average accuracy over time"
                    : `${studentFilter}'s accuracy over time`}
                </h2>
              </div>
            </div>
            <AccuracyTimeChart points={timeSeries} />
          </section>

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Class-wide</p>
                <h2>Words Needing the Most Practice</h2>
              </div>
              <span className="queue-count">{wordStats.length}</span>
            </div>

            {wordStats.length > 0 && <p className="quiz-analytics-insight">{wordMissInsight}</p>}

            {wordStats.length === 0 ? (
              <div className="teacher-empty-panel">
                <strong>No repeated mistakes yet</strong>
                <p>Words students get wrong more than once will show up here.</p>
              </div>
            ) : (
              <div className="quiz-analytics-word-list">
                {wordStats.map((word) => {
                  const severity = wordMissSeverity(word.missRatePct);
                  return (
                    <div className="quiz-analytics-word-row" key={word.word}>
                      <strong lang="zh-Hant">{word.word}</strong>
                      <span className={`word-severity-badge word-severity-${severity}`}>
                        {WORD_SEVERITY_LABEL[severity]}
                      </span>
                      <span>
                        Missed {word.timesMissed}/{word.timesAsked} times ({word.missRatePct}%)
                      </span>
                      <span>Avg. {(word.avgTimeMs / 1000).toFixed(1)}s/question</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
