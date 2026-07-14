import { useState } from "react";
import type { VocabQuizAttempt } from "../services/database";
import DashboardStat from "./DashboardStat";
import { AccuracyTimeChart, ModeAccuracyChart, QUIZ_MODE_INFO, WordMissChart } from "./MyStoriesCharts";
import {
  computeStudentQuizStats,
  computeWordMissStats,
  quizAttemptAccuracy,
  summarizeWordMissTrends,
  wordMissSeverity,
  type WordMissSeverity,
} from "../utils/myStoriesUtils";

const QUIZ_MODE_ORDER: Array<"speed" | "strikes" | "free"> = ["speed", "strikes", "free"];

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
  const [studentFilter, setStudentFilter] = useState("all");
  const [modeFilter, setModeFilter] = useState<"all" | "speed" | "strikes" | "free">("all");

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
  const studentFiltered = studentFilter === "all"
    ? attempts
    : attempts.filter((a) => a.studentName === studentFilter);
  const filtered = modeFilter === "all"
    ? studentFiltered
    : studentFiltered.filter((a) => a.mode === modeFilter);

  const totalQuestions = filtered.reduce((sum, a) => sum + a.totalQuestions, 0);
  const correctCount = filtered.reduce((sum, a) => sum + a.correctCount, 0);
  const totalTimeMs = filtered.reduce((sum, a) => sum + a.totalTimeMs, 0);
  const overallAccuracy = totalQuestions > 0 ? Math.round((correctCount / totalQuestions) * 100) : 0;
  const avgTimePerQuestion = totalQuestions > 0 ? Math.round(totalTimeMs / totalQuestions / 1000) : 0;

  const studentStats = computeStudentQuizStats(filtered);
  const allWordStats = computeWordMissStats(filtered);
  const wordStats = allWordStats.slice(0, 10);
  const wordMissInsight = summarizeWordMissTrends(allWordStats, wordStats.length);

  // Mode comparison always reads the student-filtered set (not mode-filtered)
  // so all three mode bars stay visible for comparison no matter which mode
  // is picked in the filter above.
  const modeChartData = QUIZ_MODE_ORDER.map((mode) => {
    const modeAttempts = studentFiltered.filter((a) => a.mode === mode);
    const avg = modeAttempts.length === 0
      ? 0
      : Math.round(modeAttempts.reduce((sum, a) => sum + quizAttemptAccuracy(a), 0) / modeAttempts.length);
    return { mode, avg, count: modeAttempts.length };
  });

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
          <label>
            Quiz mode
            <select value={modeFilter} onChange={(e) => setModeFilter(e.target.value as typeof modeFilter)}>
              <option value="all">All modes</option>
              {QUIZ_MODE_ORDER.map((mode) => (
                <option key={mode} value={mode}>{QUIZ_MODE_INFO[mode].icon} {QUIZ_MODE_INFO[mode].label}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {filtered.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No attempts match this filter</strong>
          <p>Try a different student or quiz mode.</p>
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
            <DashboardStat
              label="Avg. time / question"
              value={`${avgTimePerQuestion}s`}
              note="Across all recorded attempts"
            />
          </section>

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Visualized</p>
                <h2>Charts</h2>
              </div>
            </div>
            <div className="quiz-analytics-charts">
              <div className="quiz-analytics-chart-card">
                <h3>Accuracy by quiz mode</h3>
                <ModeAccuracyChart data={modeChartData} />
              </div>
              <div className="quiz-analytics-chart-card">
                <h3>
                  {studentFilter === "all"
                    ? "Class average accuracy over time"
                    : `${studentFilter}'s accuracy over time`}
                </h3>
                <AccuracyTimeChart points={timeSeries} />
              </div>
              <div className="quiz-analytics-chart-card quiz-analytics-chart-wide">
                <h3>Most-missed vocabulary words</h3>
                {wordStats.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No missed words in this filter — nice work!</p>
                ) : (
                  <>
                    <p className="quiz-analytics-insight">{wordMissInsight}</p>
                    <WordMissChart data={wordStats} />
                  </>
                )}
              </div>
            </div>
          </section>

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Per student</p>
                <h2>Student Quiz Performance</h2>
              </div>
              <span className="queue-count">{studentStats.length}</span>
            </div>

            <div className="quiz-analytics-student-table">
              <div className="quiz-analytics-student-row quiz-analytics-student-head">
                <span>Student</span>
                <span>Attempts</span>
                <span>Accuracy</span>
                <span>Avg. time/question</span>
                <span>Most repeated mistake</span>
              </div>
              {studentStats.map((student) => (
                <div className="quiz-analytics-student-row" key={student.studentName}>
                  <span>{student.studentName}</span>
                  <span>{student.attempts}</span>
                  <span>{student.accuracyPct}%</span>
                  <span>{(student.avgTimePerQuestionMs / 1000).toFixed(1)}s</span>
                  <span>
                    {student.topMissedWord
                      ? `${student.topMissedWord.word} (missed ${student.topMissedWord.missCount}×)`
                      : "—"}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Class-wide</p>
                <h2>Words Needing the Most Practice</h2>
              </div>
              <span className="queue-count">{wordStats.length}</span>
            </div>

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
                      <strong>{word.word}</strong>
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
