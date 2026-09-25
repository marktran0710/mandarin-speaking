import { useMemo, useState } from "react";
import type { AudioRecord } from "@entities/audio";
import TeacherRecordingsView from "@features/teacher/components/TeacherRecordingsView";
import "../../shared/styles/MyStoriesPage.css";
import "../teacher/TeacherDashboardPage.css";
import "./AdminAudioLibraryPage.css";

export default function AdminAudioLibraryPage({
  records,
  hasMoreRecords,
  onDeleteRecord,
  onLoadMoreRecords,
}: {
  records: AudioRecord[];
  hasMoreRecords: boolean;
  onDeleteRecord: (id: string) => void;
  onLoadMoreRecords: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const students = new Set(records.map((record) => record.studentId).filter(Boolean));
  const withAudio = records.filter((record) => Boolean(record.audioUrl)).length;
  const visibleRecords = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return records;
    return records.filter((record) => [
      record.studentId,
      record.topicId,
      record.transcription,
      record.model,
    ].some((value) => String(value ?? "").toLowerCase().includes(needle)));
  }, [query, records]);

  return (
    <div className="admin-audio-library">
      <section className="admin-audio-summary" aria-labelledby="admin-audio-summary-title">
        <div>
          <p className="admin-eyebrow">Canonical evidence</p>
          <h2 id="admin-audio-summary-title">Audio Library</h2>
          <p>
            Student recordings are created during practice and stored in the backend.
            Only administrators can remove records or their uploaded media.
          </p>
        </div>
        <dl>
          <div>
            <dt>Loaded</dt>
            <dd>{records.length}</dd>
          </div>
          <div>
            <dt>Students</dt>
            <dd>{students.size}</dd>
          </div>
          <div>
            <dt>With media</dt>
            <dd>{withAudio}</dd>
          </div>
        </dl>
      </section>

      <label className="admin-audio-filter">
        <span>Find a student, topic, transcript, or model</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search loaded records"
        />
      </label>

      <TeacherRecordingsView
        records={visibleRecords}
        hasMoreRecords={hasMoreRecords}
        onDeleteRecord={onDeleteRecord}
        onLoadMoreRecords={onLoadMoreRecords}
        title="All recording evidence"
        kicker="Admin audio operations"
        includeExperimental
        emptyTitle={query ? "No matching audio records" : "No audio records yet"}
        emptyDescription={query ? "Try a different search or load more records." : "Student recordings will appear here after the first practice session."}
      />
    </div>
  );
}
