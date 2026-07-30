import type { StudentAssessment } from "../utils/studentAssessment";

export default function TeacherWatchlist({
  assessments,
  onSelectStudent,
}: {
  assessments: StudentAssessment[];
  onSelectStudent: (studentId: string) => void;
}) {
  const watchlist = assessments
    .filter((assessment) => assessment.watchlistReasons.length > 0)
    .sort(
      (a, b) =>
        b.watchlistReasons.length - a.watchlistReasons.length ||
        a.studentName.localeCompare(b.studentName),
    );

  return (
    <section className="teacher-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Student check-in</p>
          <h2>Watchlist</h2>
        </div>
        <span className="queue-count">{watchlist.length}</span>
      </div>
      {watchlist.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No students need attention right now</strong>
        </div>
      ) : (
        <div className="student-assessment-list">
          {watchlist.map((assessment) => (
            <button
              type="button"
              className="student-assessment-row"
              key={assessment.studentId}
              onClick={() => onSelectStudent(assessment.studentId)}
            >
              <strong>{assessment.studentName}</strong>
              <span>{assessment.watchlistReasons.join(" · ")}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
