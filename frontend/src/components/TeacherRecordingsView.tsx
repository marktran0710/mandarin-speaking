import { useMemo, useState } from "react";
import RecordCard from "./RecordCard";
import type { AudioRecord } from "../pages/MyStoriesPage";

export default function TeacherRecordingsView({
  records,
  hasMoreRecords = false,
  onDeleteRecord,
  onLoadMoreRecords,
}: {
  records: AudioRecord[];
  hasMoreRecords?: boolean;
  onDeleteRecord: (id: string) => void;
  onLoadMoreRecords?: () => Promise<void>;
}) {
  const [loadingMore, setLoadingMore] = useState(false);
  const [versionFilter, setVersionFilter] = useState<"all" | "stable_v1" | "phoneme_tone_v2">("all");
  const visibleRecords = useMemo(
    () => versionFilter === "all"
      ? records
      : records.filter((record) => (record.praatMetrics?.analysis_version ?? "stable_v1") === versionFilter),
    [records, versionFilter],
  );

  const handleLoadMore = async () => {
    if (!onLoadMoreRecords) return;
    setLoadingMore(true);
    try {
      await onLoadMoreRecords();
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <section className="teacher-panel teacher-recordings-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Detailed review</p>
          <h2>Student Recording Evidence</h2>
        </div>
        <label>
          Analysis version
          <select value={versionFilter} onChange={(event) => setVersionFilter(event.target.value as typeof versionFilter)}>
            <option value="all">All versions</option>
            <option value="stable_v1">Stable V1 — official</option>
            <option value="phoneme_tone_v2">Experimental V2 — analytics</option>
          </select>
        </label>
      </div>

      {visibleRecords.length === 0 ? (
        <div className="stories-empty-state">
          <div className="stories-empty-icon">Data</div>
          <h2>{records.length === 0 ? "No Student Recordings Yet" : "No recordings match this version"}</h2>
          <p>{records.length === 0 ? "Student submissions will appear here after practice sessions." : "Choose another analysis version to review the available results."}</p>
        </div>
      ) : (
        <>
          <div className="stories-grid teacher-recording-grid">
            {visibleRecords.map((record) => (
              <RecordCard
                key={record.id}
                record={record}
                onDeleteRecord={onDeleteRecord}
              />
            ))}
          </div>
          {hasMoreRecords && onLoadMoreRecords && (
            <button
              type="button"
              className="teacher-refresh-btn"
              onClick={handleLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading..." : "Load more"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
