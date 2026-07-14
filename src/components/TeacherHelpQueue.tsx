import type { HelpRequest } from "../services/database";
import { formatRequestTime } from "../utils/myStoriesUtils";

export default function TeacherHelpQueue({
  helpRequests,
  onResolveHelpRequest,
  compact = false,
}: {
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  compact?: boolean;
}) {
  const openRequests = helpRequests.filter(
    (request) => request.status === "open",
  );
  const resolvedRequests = helpRequests
    .filter((request) => request.status === "resolved")
    .slice(0, compact ? 2 : 5);

  return (
    <section className="teacher-panel teacher-help-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Live support</p>
          <h2>Student Help Requests</h2>
        </div>
        <span className="queue-count">{openRequests.length}</span>
      </div>

      {openRequests.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No raised hands</strong>
          <p>Open help requests will appear here when students ask for support.</p>
        </div>
      ) : (
        <div className="teacher-help-list">
          {openRequests.map((request) => (
            <article className="teacher-help-request" key={request.id}>
              <div>
                <strong>{request.studentName}</strong>
                <span>{formatRequestTime(request.createdAt)}</span>
                <p>{request.message}</p>
              </div>
              <button
                type="button"
                onClick={() => onResolveHelpRequest?.(request.id)}
                disabled={!onResolveHelpRequest}
              >
                Mark helped
              </button>
            </article>
          ))}
        </div>
      )}

      {!compact && resolvedRequests.length > 0 && (
        <div className="teacher-resolved-help">
          <h3>Recently helped</h3>
          {resolvedRequests.map((request) => (
            <div className="teacher-resolved-row" key={request.id}>
              <span>{request.studentName}</span>
              <small>{formatRequestTime(request.resolvedAt || request.createdAt)}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
