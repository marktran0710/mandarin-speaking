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
  // Teachers see official results only. The analysis-version switch was
  // research plumbing — experimental V2 output lives in the admin console.
  const visibleRecords = useMemo(
    () => records.filter(
      (record) => (record.praatMetrics?.analysis_version ?? "stable_v1") === "stable_v1",
    ),
    [records],
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
      </div>

      {visibleRecords.length === 0 ? (
        <div className="stories-empty-state">
          <div className="stories-empty-icon">Data</div>
          <h2>No Student Recordings Yet</h2>
          <p>Student submissions will appear here after practice sessions.</p>
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
