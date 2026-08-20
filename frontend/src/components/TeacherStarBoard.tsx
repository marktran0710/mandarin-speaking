import { getTopicLabel } from "../utils/myStoriesUtils";
import type { StudentAssessment } from "../utils/studentAssessment";

export default function TeacherStarBoard({ assessments }: { assessments: StudentAssessment[] }) {
  const storyIds = Array.from(new Set(
    assessments.flatMap((assessment) => assessment.quiz.tierAttemptStoryIds),
  )).sort();

  return (
    <section className="teacher-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Star ladder</p>
          <h2>Class Star Board</h2>
        </div>
        <span className="queue-count">{assessments.length}</span>
      </div>
      {storyIds.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No tier attempts yet</strong>
          <p>Story stars will appear here after students start a tiered vocabulary quiz.</p>
        </div>
      ) : (
        <div className="star-board-scroll">
          <table className="star-board-table">
            <thead>
              <tr>
                <th scope="col">Student</th>
                {storyIds.map((storyId) => (
                  <th scope="col" key={storyId} title={storyId}>
                    {getTopicLabel(storyId)}
                  </th>
                ))}
                <th scope="col">Total</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((assessment) => {
                const total = storyIds.reduce(
                  (sum, storyId) => sum + (assessment.quiz.starsByStory[storyId] ?? 0),
                  0,
                );
                return (
                  <tr key={assessment.studentId}>
                    <th scope="row">{assessment.studentName}</th>
                    {storyIds.map((storyId) => {
                      const earned = assessment.quiz.starsByStory[storyId] ?? 0;
                      return (
                        <td key={storyId} aria-label={`${earned} of 3 stars`}>
                          {earned > 0 ? "★".repeat(earned) : "—"}
                        </td>
                      );
                    })}
                    <td className="star-board-total">★ {total}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
