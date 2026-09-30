import { useEffect, useRef, useState } from "react";
import { formatCompletedDate } from "./format";
import { ROUND_DEFINITIONS, type StudentRoundDashboardData } from "./model";
import { ResponseTimeValue, RoundScoreValue } from "./RoundScoreCells";
import StudentRoundChart from "./StudentRoundChart";

export default function StudentRoundDashboard({
  dashboard,
  initialStoryId,
  onBack,
}: {
  dashboard: StudentRoundDashboardData;
  initialStoryId: string;
  onBack: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [chosenStoryId, setChosenStoryId] = useState(initialStoryId);
  const selectedLesson = dashboard.lessons.find((lesson) => lesson.storyId === chosenStoryId) ?? dashboard.lessons[0];
  const { responseTime } = dashboard;

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <section className="round-scores-panel student-round-dashboard" aria-labelledby="student-round-dashboard-title">
      <header className="round-scores-heading">
        <div>
          <span className="round-scores-eyebrow">Student dashboard</span>
          <h2 id="student-round-dashboard-title" ref={headingRef} tabIndex={-1}>{dashboard.studentName}</h2>
          <p>
            {dashboard.studentId} · <span className={`round-score-status is-${dashboard.status}`}>{dashboard.status}</span>
          </p>
        </div>
        <button type="button" className="student-round-back" onClick={onBack}>Back to class</button>
      </header>

      <p className="round-scores-note">
        <strong>Interpret with care.</strong> Each lesson shows the latest completed attempt per round. The class average
        counts active students who completed that round, including this student. Response time is descriptive only.
      </p>

      {!selectedLesson ? (
        <div className="round-scores-empty" role="status">
          <strong>No completed rounds yet</strong>
          <span>This student has no eligible three-round quiz attempts.</span>
        </div>
      ) : (
        <>
          <div className="round-scores-kpis" aria-label="Student summary">
            <article>
              <span>Lessons attempted</span>
              <strong>{dashboard.lessonsAttempted}</strong>
              <small>with at least one completed round</small>
            </article>
            <article className="round-scores-kpi-complete">
              <span>Completed all 3 rounds</span>
              <strong>{dashboard.lessonsCompletedAll}</strong>
              <small>of {dashboard.lessonsAttempted} lesson{dashboard.lessonsAttempted === 1 ? "" : "s"}</small>
            </article>
            <article>
              <span>Avg response time</span>
              <strong>{responseTime.secondsPerQuestion === null ? "—" : `${responseTime.secondsPerQuestion}s`}</strong>
              <small>
                {responseTime.secondsPerQuestion === null
                  ? "Time unavailable"
                  : `per question · ${responseTime.totalQuestions} questions across ${responseTime.completedRounds} round${responseTime.completedRounds === 1 ? "" : "s"}`}
              </small>
            </article>
            <article>
              <span>Latest quiz activity</span>
              <strong className="round-scores-kpi-text">
                {dashboard.lastActivityAt ? formatCompletedDate(dashboard.lastActivityAt) : "—"}
              </strong>
              <small>latest completed round</small>
            </article>
          </div>

          <section className="round-scores-card" aria-labelledby="student-round-chart-title">
            <div className="round-scores-card-heading">
              <div>
                <h3 id="student-round-chart-title">{selectedLesson.title}</h3>
                <p>{dashboard.studentName} compared with the class average on each round</p>
              </div>
              <span>Latest attempt only</span>
            </div>
            <StudentRoundChart studentName={dashboard.studentName} lesson={selectedLesson} />
          </section>

          <section className="round-scores-card" aria-labelledby="student-round-lessons-title">
            <div className="round-scores-card-heading">
              <div>
                <h3 id="student-round-lessons-title">All lessons</h3>
                <p>Choose a lesson to show it in the chart above.</p>
              </div>
              <span>Newest first</span>
            </div>
            <div className="round-scores-table-scroll" tabIndex={0} aria-label="Scrollable lessons table">
              <table className="round-scores-table student-lessons-table">
                <caption>Round scores by lesson for {dashboard.studentName}</caption>
                <thead>
                  <tr>
                    <th scope="col">Lesson</th>
                    {ROUND_DEFINITIONS.map((round) => <th scope="col" key={round.mode}>{round.label}</th>)}
                    <th scope="col">Avg response time</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.lessons.map((lesson) => (
                    <tr key={lesson.storyId} className={lesson.storyId === selectedLesson.storyId ? "is-selected" : undefined}>
                      <th scope="row">
                        <button
                          type="button"
                          className="student-lesson-link"
                          aria-pressed={lesson.storyId === selectedLesson.storyId}
                          onClick={() => setChosenStoryId(lesson.storyId)}
                        >
                          {lesson.title}
                        </button>
                        <small>{lesson.storyId}</small>
                      </th>
                      {ROUND_DEFINITIONS.map((round) => (
                        <td key={round.mode}><RoundScoreValue cell={lesson.rounds[round.mode]} /></td>
                      ))}
                      <td><ResponseTimeValue summary={lesson.responseTime} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
