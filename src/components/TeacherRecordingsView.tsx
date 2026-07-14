import RecordCard from "./RecordCard";
import type { AudioRecord } from "../pages/MyStoriesPage";

export default function TeacherRecordingsView({
  records,
  onDeleteRecord,
}: {
  records: AudioRecord[];
  onDeleteRecord: (id: string) => void;
}) {
  return (
    <section className="teacher-panel teacher-recordings-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Detailed review</p>
          <h2>Student Recording Evidence</h2>
        </div>
      </div>

      {records.length === 0 ? (
        <div className="stories-empty-state">
          <div className="stories-empty-icon">Data</div>
          <h2>No Student Recordings Yet</h2>
          <p>Student submissions will appear here after practice sessions.</p>
        </div>
      ) : (
        <div className="stories-grid teacher-recording-grid">
          {records.map((record) => (
            <RecordCard
              key={record.id}
              record={record}
              onDeleteRecord={onDeleteRecord}
            />
          ))}
        </div>
      )}
    </section>
  );
}
