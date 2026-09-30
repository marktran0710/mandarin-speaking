import { formatCompletedAt } from "./format";
import { cellSecondsPerQuestion, type ResponseTimeSummary, type RoundScoreCell } from "./model";

export function RoundScoreValue({ cell }: { cell: RoundScoreCell | null }) {
  if (!cell) return <span className="round-score-missing">Not completed</span>;
  const seconds = cellSecondsPerQuestion(cell);
  return (
    <span className="round-score-value">
      <strong>{cell.score}%</strong>
      <small>
        {cell.correctCount}/{cell.totalQuestions}
        {seconds === null ? " · Time unavailable" : ` · ${seconds}s/question`}
        {` · ${formatCompletedAt(cell.completedAt)}`}
      </small>
    </span>
  );
}

export function ResponseTimeValue({ summary }: { summary: ResponseTimeSummary }) {
  if (summary.secondsPerQuestion === null) return <span className="round-score-missing">Not available</span>;
  return (
    <span className="round-score-value round-response-time-value">
      <strong>{summary.secondsPerQuestion}s/question</strong>
      <small>{summary.totalQuestions} questions across {summary.completedRounds} round{summary.completedRounds === 1 ? "" : "s"}</small>
    </span>
  );
}
