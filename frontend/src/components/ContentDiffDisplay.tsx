import type { ContentDiffSegment } from "./StoryRecorder";

/**
 * Always renders the same two-line-plus-status shape (Target / You said /
 * status line) regardless of whether content was verified as matching,
 * verified as wrong, or couldn't be verified at all — so the results card
 * doesn't change height depending on how the attempt went. Previously the
 * unverified case short-circuited to a single line and the matched case
 * wasn't rendered at all, which meant the whole speaking-flow-card jumped
 * size between a correct attempt and a wrong/unverified one.
 */
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
  const verified = contentMatch === true || contentMatch === false;
  const segments: ContentDiffSegment[] = verified
    ? diff && diff.length > 0
      ? diff
      : [{ type: contentMatch ? "match" : "replace", target, heard: heard ?? "" }]
    : [];

  const renderLine = (side: "target" | "heard") => {
    if (!verified) {
      const text = side === "target" ? target : heard;
      return text ? (
        <span className="content-diff-line-text" lang="zh-TW">
          {text}
        </span>
      ) : null;
    }
    return (
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
  };

  const status =
    contentMatch === true
      ? { text: "✓ Matches the script.", tone: "match" as const }
      : contentMatch === false
        ? { text: "Bold text shows the difference.", tone: "mismatch" as const }
        : {
            text: "We couldn't verify the words in this recording. Please record it again.",
            tone: "unverified" as const,
          };

  return (
    <div className="content-diff" aria-label="Script and recognized speech comparison" role="status">
      <p className="content-diff-line">
        <span className="content-diff-label">Target:</span>
        {renderLine("target")}
      </p>
      <p className="content-diff-line">
        <span className="content-diff-label">You said:</span>
        {heard ? renderLine("heard") : <span className="content-diff-empty">(no speech detected)</span>}
      </p>
      <p className={`content-diff-hint content-diff-hint-${status.tone}`}>{status.text}</p>
    </div>
  );
}
