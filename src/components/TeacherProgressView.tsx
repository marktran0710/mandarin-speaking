import { getTopicLabel } from "../utils/myStoriesUtils";
import type { AudioRecord } from "../pages/MyStoriesPage";

export default function TeacherProgressView({
  records,
}: {
  records: AudioRecord[];
}) {
  return (
    <section className="teacher-dashboard-grid">
      <div className="teacher-panel topic-coverage-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Curriculum coverage</p>
            <h2>Topic Progress</h2>
          </div>
        </div>

        <div className="topic-coverage-list">
          {<div className="teacher-empty-panel">
            <strong>Activity Coverage</strong>
            <p>Coverage displays for published teacher materials.</p>
          </div>}
        </div>
      </div>

      <div className="teacher-panel review-queue-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Review queue</p>
            <h2>Recent Submissions</h2>
          </div>
          <span className="queue-count">{records.length}</span>
        </div>

        {records.length === 0 ? (
          <div className="teacher-empty-panel">
            <strong>No submissions yet</strong>
            <p>Student recordings will appear here after practice sessions.</p>
          </div>
        ) : (
          <div className="teacher-submission-list">
            {records.slice(0, 5).map((record) => (
              <div className="teacher-submission-row" key={record.id}>
                <div>
                  <strong>{getTopicLabel(record.topicId)}</strong>
                  <span>
                    Part {(record.imageIndex ?? 0) + 1} · {record.duration}s
                  </span>
                </div>
                <div className="submission-score">
                  {record.praatMetrics
                    ? `${Math.round(record.praatMetrics.fluency_score)}/100`
                    : "Pending"}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
