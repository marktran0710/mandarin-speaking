import type { ContentDiffSegment } from "./StoryRecorder";

export default function ContentDiffDisplay({
  target,
  heard,
  diff,
  contentMatch,
}: {
  target: string;
  heard?: string | null;
  diff?: ContentDiffSegment[];
  contentMatch: boolean | null | undefined;
}) {
  if (contentMatch !== true && contentMatch !== false) {
    return (
      <p className="content-diff-unverified" role="status">
        We couldn't verify the words in this recording. Please record it again.
      </p>
    );
  }

  const segments = diff && diff.length > 0
    ? diff
    : [{ type: contentMatch ? "match" : "replace", target, heard: heard ?? "" } satisfies ContentDiffSegment];

  const renderLine = (side: "target" | "heard") => (
    <span className="content-diff-line-text" lang="zh-TW">
      {segments.map((segment, index) => {
        const text = segment[side];
        if (!text) return null;
        const highlight = segment.type !== "match";
        return highlight ? (
          <strong key={`${side}-${index}`} className="content-diff-highlight">
            {text}
          </strong>
        ) : (
          <span key={`${side}-${index}`}>{text}</span>
        );
      })}
    </span>
  );

  return (
    <div className="content-diff" aria-label="Script and recognized speech comparison">
      <p className="content-diff-line">
        <span className="content-diff-label">Target:</span>
        {renderLine("target")}
      </p>
      <p className="content-diff-line">
        <span className="content-diff-label">You said:</span>
        {heard ? renderLine("heard") : <span className="content-diff-empty">(no speech detected)</span>}
      </p>
      {contentMatch === false && (
        <p className="content-diff-hint">Bold text shows the difference.</p>
      )}
    </div>
  );
}
