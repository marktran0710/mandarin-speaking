import { useMemo, useState } from "react";
import RecordCard from "../../../components/speaking-flow-card/RecordCard";
import type { AudioRecord } from "@entities/audio";

export default function TeacherRecordingsView({
  records,
  hasMoreRecords = false,
  onDeleteRecord,
  onLoadMoreRecords,
  title = "Student Recording Evidence",
  kicker = "Detailed review",
  includeExperimental = false,
  emptyTitle = "No Student Recordings Yet",
  emptyDescription = "Student submissions will appear here after practice sessions.",
}: {
  records: AudioRecord[];
  hasMoreRecords?: boolean;
  onDeleteRecord?: (id: string) => void;
  onLoadMoreRecords?: () => Promise<void>;
  title?: string;
  kicker?: string;
  includeExperimental?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  const [loadingMore, setLoadingMore] = useState(false);
  // Teachers see official results only. The analysis-version switch was
  // research plumbing — experimental V2 output lives in the admin console.
  const visibleRecords = useMemo(
    () => includeExperimental
      ? records
      : records.filter(
          (record) => (record.praatMetrics?.analysis_version ?? "stable_v1") === "stable_v1",
        ),
    [includeExperimental, records],
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
          <p className="stories-kicker">{kicker}</p>
          <h2>{title}</h2>
        </div>
      </div>

      {visibleRecords.length === 0 ? (
        <div className="stories-empty-state">
          <div className="stories-empty-icon">Data</div>
          <h2>{emptyTitle}</h2>
          <p>{emptyDescription}</p>
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
