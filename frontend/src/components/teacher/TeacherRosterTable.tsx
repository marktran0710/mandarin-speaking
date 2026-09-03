import { useMemo, useState } from "react";
import { getTopicLabel } from "../../utils/myStoriesUtils";
import type { StudentAssessment } from "../../utils/studentAssessment";

/** One roster table replaces what used to be four overlapping student lists
 * (Watchlist, Class Star Board, "All students", and the quiz panel's own
 * student table). Students needing attention sort to the top and carry a
 * reason; the per-story star columns are the old Star Board, folded in
 * behind a toggle so the default table stays one screen wide. */
export default function TeacherRosterTable({
  assessments,
  onSelectStudent,
}: {
  assessments: StudentAssessment[];
  onSelectStudent: (studentId: string) => void;
}) {
  const [showStars, setShowStars] = useState(false);

  const storyIds = useMemo(
    () =>
      Array.from(
        new Set(assessments.flatMap((assessment) => assessment.quiz.tierAttemptStoryIds)),
      ).sort(),
    [assessments],
  );

  const rows = useMemo(
    () =>
      [...assessments].sort(
        (a, b) =>
          b.watchlistReasons.length - a.watchlistReasons.length ||
          a.studentName.localeCompare(b.studentName),
      ),
    [assessments],
  );

  const needAttention = rows.filter((row) => row.watchlistReasons.length > 0).length;

  const totalStars = (assessment: StudentAssessment) =>
    storyIds.reduce((sum, storyId) => sum + (assessment.quiz.starsByStory[storyId] ?? 0), 0);

  if (assessments.length === 0) {
    return (
      <section className="tdash-card">
        <div className="tdash-card-head">
          <h2>Students</h2>
        </div>
        <div className="tdash-empty">
          <strong>No students yet</strong>
          <p>Names appear here once student accounts are created in the admin console.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="tdash-card">
      <div className="tdash-card-head">
        <h2>
          Students <span className="tdash-count">{rows.length}</span>
        </h2>
        {storyIds.length > 0 && (
          <button
            type="button"
            className="tdash-ghost-btn"
            aria-pressed={showStars}
            onClick={() => setShowStars((open) => !open)}
          >
            {showStars ? "Hide stars per story" : "Stars per story"}
          </button>
        )}
      </div>

      <p className="tdash-card-note">
        {needAttention === 0
          ? "Nobody needs attention right now."
          : `${needAttention} student${needAttention === 1 ? "" : "s"} need attention — sorted to the top.`}
      </p>

      <div className="tdash-table-scroll">
        <table className="tdash-roster">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Stars</th>
              {showStars &&
                storyIds.map((storyId) => (
                  <th scope="col" key={storyId} title={storyId}>
                    {getTopicLabel(storyId)}
                  </th>
                ))}
              <th scope="col">Quiz</th>
              <th scope="col">Recordings</th>
              <th scope="col">Last active</th>
              <th scope="col">Needs attention</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((assessment) => (
              <tr
                key={assessment.studentId}
                className={assessment.watchlistReasons.length > 0 ? "is-flagged" : ""}
              >
                <th scope="row">
                  <button type="button" onClick={() => onSelectStudent(assessment.studentId)}>
                    {assessment.studentName}
                  </button>
                </th>
                <td className="tdash-num">{totalStars(assessment) || "—"}</td>
                {showStars &&
                  storyIds.map((storyId) => {
                    const earned = assessment.quiz.starsByStory[storyId] ?? 0;
                    return (
                      <td key={storyId} aria-label={`${earned} of 3 stars`}>
                        {earned > 0 ? "★".repeat(earned) : "—"}
                      </td>
                    );
                  })}
                <td className="tdash-num">
                  {assessment.quiz.accuracyPct === null ? "—" : `${assessment.quiz.accuracyPct}%`}
                </td>
                <td className="tdash-num">{assessment.speaking.recordingCount || "—"}</td>
                <td>
                  {assessment.activity.lastActivityAt
                    ? new Date(assessment.activity.lastActivityAt).toLocaleDateString()
                    : "—"}
                </td>
                <td>
                  {assessment.watchlistReasons.length === 0 ? (
                    <span className="tdash-ok">—</span>
                  ) : (
                    <span className="tdash-flag">{assessment.watchlistReasons.join(" · ")}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
