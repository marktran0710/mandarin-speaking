import { useEffect, useMemo, useState } from "react";
import { listCustomStories, type StoredCustomStory } from "../../../services/api/stories-submissions";
import type { Student } from "../../../services/api/roster-help";
import type { VocabQuizAttempt } from "../../../services/api/quiz-analytics";
import RoundScoresChart from "./RoundScoresChart";
import {
  ROUND_DEFINITIONS,
  buildRoundScoreRows,
  buildRoundScoreStoryOptions,
  mostRecentRoundScoreStoryId,
  selectLatestRoundAttempts,
  summarizeRoundScores,
  type RoundScoreCell,
  type RoundScoreRow,
} from "./model";
import "./RoundScoresPanel.css";

const PAGE_SIZE = 15;
type StatusFilter = "active" | "all";
type ProgressFilter = "all" | "started" | "completed";

const completedAtFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatCompletedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : completedAtFormatter.format(date);
}

function RoundScoreValue({ cell }: { cell: RoundScoreCell | null }) {
  if (!cell) return <span className="round-score-missing">Not completed</span>;
  return (
    <span className="round-score-value">
      <strong>{cell.score}%</strong>
      <small>{cell.correctCount}/{cell.totalQuestions} · {formatCompletedAt(cell.completedAt)}</small>
    </span>
  );
}

function matchesProgress(row: RoundScoreRow, filter: ProgressFilter): boolean {
  if (filter === "started") return row.completedRounds > 0;
  if (filter === "completed") return row.completedRounds === ROUND_DEFINITIONS.length;
  return true;
}

export default function RoundScoresPanel({
  students,
  attempts,
}: {
  students: Student[];
  attempts: VocabQuizAttempt[];
}) {
  const [stories, setStories] = useState<StoredCustomStory[]>([]);
  const [storiesLoading, setStoriesLoading] = useState(true);
  const [storyLoadFailed, setStoryLoadFailed] = useState(false);
  const [selectedStoryId, setSelectedStoryId] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [progressFilter, setProgressFilter] = useState<ProgressFilter>("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let cancelled = false;
    setStoriesLoading(true);
    listCustomStories()
      .then((result) => {
        if (cancelled) return;
        setStories(result);
        setStoryLoadFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setStories([]);
        setStoryLoadFailed(true);
      })
      .finally(() => {
        if (!cancelled) setStoriesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const latestAttempts = useMemo(() => selectLatestRoundAttempts(students, attempts), [attempts, students]);
  const storyOptions = useMemo(
    () => buildRoundScoreStoryOptions(latestAttempts, stories),
    [latestAttempts, stories],
  );
  const defaultStoryId = useMemo(() => mostRecentRoundScoreStoryId(latestAttempts), [latestAttempts]);

  useEffect(() => {
    if (storyOptions.some((story) => story.id === selectedStoryId)) return;
    setSelectedStoryId(defaultStoryId || storyOptions[0]?.id || "");
  }, [defaultStoryId, selectedStoryId, storyOptions]);

  const rows = useMemo(
    () => buildRoundScoreRows(students, latestAttempts, selectedStoryId),
    [latestAttempts, selectedStoryId, students],
  );
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredRows = useMemo(() => rows.filter((row) => {
    if (statusFilter === "active" && row.status !== "active") return false;
    if (!matchesProgress(row, progressFilter)) return false;
    if (!normalizedQuery) return true;
    return `${row.studentName} ${row.studentId}`.toLocaleLowerCase().includes(normalizedQuery);
  }), [normalizedQuery, progressFilter, rows, statusFilter]);
  const summary = useMemo(() => summarizeRoundScores(filteredRows), [filteredRows]);
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageRows = filteredRows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const hasPageScores = pageRows.some((row) => row.completedRounds > 0);
  const selectedStory = storyOptions.find((story) => story.id === selectedStoryId);

  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  const changeFilter = (update: () => void) => {
    update();
    setPage(1);
  };

  return (
    <section className="round-scores-panel" aria-labelledby="round-scores-title">
      <header className="round-scores-heading">
        <div>
          <span className="round-scores-eyebrow">Class comparison</span>
          <h2 id="round-scores-title">Three-round quiz scores</h2>
          <p>Latest completed attempt for each student, lesson, and round.</p>
        </div>
        <span className="round-scores-scale">Accuracy · 0–100%</span>
      </header>

      <p className="round-scores-note">
        <strong>Interpret with care.</strong> Meaning, pinyin, and context are different assessment dimensions.
        Score differences between rounds are not evidence of growth over time.
      </p>

      <div className="round-scores-controls">
        <label>
          Lesson
          <select
            value={selectedStoryId}
            disabled={storyOptions.length === 0}
            onChange={(event) => changeFilter(() => setSelectedStoryId(event.target.value))}
          >
            {storyOptions.length === 0 ? <option value="">No lessons available</option> : null}
            {storyOptions.map((story) => (
              <option key={story.id} value={story.id}>
                {story.title === story.id ? story.id : `${story.title} (${story.id})`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Search students
          <input
            type="search"
            value={query}
            placeholder="Name or student ID"
            onChange={(event) => changeFilter(() => setQuery(event.target.value))}
          />
        </label>
        <label>
          Student status
          <select
            value={statusFilter}
            onChange={(event) => changeFilter(() => setStatusFilter(event.target.value as StatusFilter))}
          >
            <option value="active">Active only</option>
            <option value="all">Active and inactive</option>
          </select>
        </label>
        <label>
          Round progress
          <select
            value={progressFilter}
            onChange={(event) => changeFilter(() => setProgressFilter(event.target.value as ProgressFilter))}
          >
            <option value="all">All</option>
            <option value="started">Started</option>
            <option value="completed">Completed all 3</option>
          </select>
        </label>
      </div>

      {storyLoadFailed ? (
        <p className="round-scores-load-note" role="status">Lesson names could not be loaded. Available lesson IDs are shown instead.</p>
      ) : null}

      {!selectedStoryId ? (
        <div className="round-scores-empty" role="status">
          <strong>{storiesLoading ? "Loading lessons…" : "No lesson data yet"}</strong>
          <span>No eligible three-round quiz attempts or lessons are available.</span>
        </div>
      ) : (
        <>
          <div className="round-scores-kpis" aria-label="Filtered round score summary">
            {ROUND_DEFINITIONS.map((round) => {
              const metric = summary.rounds[round.mode];
              return (
                <article key={round.mode}>
                  <span>{round.label} average</span>
                  <strong>{metric.average === null ? "—" : `${metric.average}%`}</strong>
                  <small>{metric.completed} student{metric.completed === 1 ? "" : "s"} completed</small>
                </article>
              );
            })}
            <article className="round-scores-kpi-complete">
              <span>Completed all three</span>
              <strong>{summary.completedAll}</strong>
              <small>of {filteredRows.length} filtered student{filteredRows.length === 1 ? "" : "s"}</small>
            </article>
          </div>

          <section className="round-scores-card" aria-labelledby="round-score-chart-title">
            <div className="round-scores-card-heading">
              <div>
                <h3 id="round-score-chart-title">{selectedStory?.title ?? selectedStoryId}</h3>
                <p>{filteredRows.length} matching student{filteredRows.length === 1 ? "" : "s"} · page {safePage} of {pageCount}</p>
              </div>
              <span>Latest attempt only</span>
            </div>

            {filteredRows.length === 0 ? (
              <div className="round-scores-empty" role="status">
                <strong>No matching students</strong>
                <span>Adjust the search, account status, or progress filter.</span>
              </div>
            ) : (
              <>
                {hasPageScores ? (
                  <RoundScoresChart rows={pageRows} />
                ) : (
                  <div className="round-scores-empty round-scores-chart-empty" role="status">
                    <strong>No completed rounds on this page</strong>
                    <span>These students remain visible below as “Not completed”; missing rounds are never scored as zero.</span>
                  </div>
                )}

                <div className="round-scores-table-scroll" tabIndex={0} aria-label="Scrollable round scores data table">
                  <table className="round-scores-table">
                    <caption>Round scores for {selectedStory?.title ?? selectedStoryId}</caption>
                    <thead>
                      <tr>
                        <th scope="col">Student</th>
                        <th scope="col">Status</th>
                        {ROUND_DEFINITIONS.map((round) => <th scope="col" key={round.mode}>{round.label}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {pageRows.map((row) => (
                        <tr key={row.studentId}>
                          <th scope="row">
                            <strong>{row.studentName}</strong>
                            <small>{row.studentId}</small>
                          </th>
                          <td><span className={`round-score-status is-${row.status}`}>{row.status}</span></td>
                          {ROUND_DEFINITIONS.map((round) => (
                            <td key={round.mode}><RoundScoreValue cell={row.rounds[round.mode]} /></td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {pageCount > 1 ? (
                  <nav className="round-scores-pagination" aria-label="Round scores pagination">
                    <button type="button" disabled={safePage === 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</button>
                    <span>Page {safePage} of {pageCount}</span>
                    <button type="button" disabled={safePage === pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>Next</button>
                  </nav>
                ) : null}
              </>
            )}
          </section>
        </>
      )}
    </section>
  );
}
