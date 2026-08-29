import { useMemo, useState } from "react";
import {
  updateSubmissionReview,
  type StorySubmission,
} from "../services/database";
import { resolveImageUrl } from "../utils/teacherStories";
import { SELF_EVAL_EMOJI } from "../utils/selfEvalComparison";
import StoryFeedbackCard from "./StoryFeedbackCard";
import Icon from "../shared/ui/Icon";

function submittedTime(submission: StorySubmission) {
  const time = Date.parse(submission.submittedAt);
  return Number.isNaN(time) ? 0 : time;
}

/** One number for the whole submission — the average of every scene's
 * vocab/tone/prosody score — so a teacher can judge "how did this go"
 * without opening it. The per-scene breakdown is still there, just behind
 * the Details toggle. */
function overallScore(submission: StorySubmission): number {
  const scores = submission.scenes.flatMap((scene) => [scene.vocabScore, scene.toneAccuracy, scene.pronScore]);
  if (scores.length === 0) return 0;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
}

export default function TeacherSubmissionsView({
  submissions,
  onReviewUpdate,
}: {
  submissions: StorySubmission[];
  onReviewUpdate: (updated: StorySubmission) => void;
}) {
  // One control. The sort dropdown always wanted "needs review first", and
  // the search box duplicated the student dropdown beside it.
  const [studentFilter, setStudentFilter] = useState("all");
  const PAGE_SIZE = 8;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [overrides, setOverrides] = useState<Record<string, StorySubmission>>({});
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});
  const [openNotes, setOpenNotes] = useState<Record<string, boolean>>({});
  // Every row starts collapsed to one scannable line — scenes, audio, and
  // feedback only render once a teacher asks to see them.
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState("");

  const displayedSubmissions = submissions.map(
    (submission) => overrides[submission.id] ?? submission,
  );
  const students = useMemo(
    () => Array.from(new Set(displayedSubmissions.map((submission) => submission.studentName))).sort(),
    [displayedSubmissions],
  );
  const filteredSubmissions = useMemo(
    () =>
      displayedSubmissions
        .filter((submission) => studentFilter === "all" || submission.studentName === studentFilter)
        // Unmarked work first, newest within each group.
        .sort((a, b) => {
          const reviewDifference =
            (a.reviewStatus === "reviewed" ? 1 : 0) - (b.reviewStatus === "reviewed" ? 1 : 0);
          return reviewDifference || submittedTime(b) - submittedTime(a);
        }),
    [displayedSubmissions, studentFilter],
  );
  const pagedSubmissions = filteredSubmissions.slice(0, visibleCount);
  const hasMoreSubmissions = visibleCount < filteredSubmissions.length;

  async function saveReview(
    submission: StorySubmission,
    status: "pending" | "reviewed",
    note: string | null,
  ) {
    const optimistic = { ...submission, reviewStatus: status, teacherNote: note };
    setReviewError("");
    setOverrides((previous) => ({ ...previous, [submission.id]: optimistic }));
    setSavingId(submission.id);

    try {
      const updated = await updateSubmissionReview(submission.id, status, note);
      setOverrides((previous) => ({ ...previous, [submission.id]: updated }));
      onReviewUpdate(updated);
    } catch {
      setOverrides((previous) => ({ ...previous, [submission.id]: submission }));
      setReviewError("Could not save this submission's review status. Please try again.");
    } finally {
      setSavingId(null);
    }
  }

  if (submissions.length === 0) {
    return (
      <section className="teacher-panel teacher-submissions-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Student story submissions</p>
            <h2>Submissions</h2>
          </div>
          <span className="queue-count">0</span>
        </div>
        <div className="teacher-empty-panel">
          <strong>No submissions yet</strong>
          <p>Students will appear here after they complete and submit all scenes of a story.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="teacher-panel teacher-submissions-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Student story submissions</p>
          <h2>Submissions</h2>
        </div>
        <div className="story-submission-header-right">
          <label className="story-submission-filter">
            Student
            <select
              value={studentFilter}
              onChange={(event) => {
                setStudentFilter(event.target.value);
                setVisibleCount(PAGE_SIZE);
              }}
            >
              <option value="all">All students</option>
              {students.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          <span className="queue-count">{submissions.length}</span>
        </div>
      </div>
      {reviewError && <p className="story-submission-review-error" role="alert">{reviewError}</p>}
      {filteredSubmissions.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No submissions from this student yet</strong>
          <p>Pick another student, or choose "All students".</p>
        </div>
      ) : (
        <div className="story-submission-list">
          {pagedSubmissions.map((sub) => {
            const reviewStatus = sub.reviewStatus ?? "pending";
            const noteDraft = noteDrafts[sub.id] ?? sub.teacherNote ?? "";
            const noteIsOpen = openNotes[sub.id];
            const isSaving = savingId === sub.id;
            const isExpanded = Boolean(expandedIds[sub.id]);

            return (
              <div key={sub.id} className="story-submission-row-wrap">
                <div className="story-submission-row">
                  <span className={`submission-review-badge submission-review-${reviewStatus}`}>
                    {reviewStatus === "reviewed" ? "Reviewed" : "Pending review"}
                  </span>
                  <div className="story-submission-row-primary">
                    <strong>{sub.studentName}</strong>
                    <span className="story-submission-row-story">{sub.storyTitle}</span>
                  </div>
                  <span className="story-submission-row-score">{overallScore(sub)}%</span>
                  <span className="story-submission-row-date">
                    {new Date(sub.submittedAt).toLocaleDateString()}
                  </span>
                  <button
                    type="button"
                    className="story-submission-review-button"
                    disabled={isSaving}
                    onClick={() =>
                      void saveReview(
                        sub,
                        reviewStatus === "pending" ? "reviewed" : "pending",
                        sub.teacherNote ?? null,
                      )
                    }
                  >
                    {reviewStatus === "pending" ? "Mark reviewed" : "Mark pending"}
                  </button>
                  <button
                    type="button"
                    className="story-submission-toggle"
                    aria-expanded={isExpanded}
                    onClick={() => setExpandedIds((previous) => ({ ...previous, [sub.id]: !isExpanded }))}
                  >
                    {isExpanded ? "Hide" : "Details"}
                    <Icon name="chevron-down" size={14} />
                  </button>
                </div>

                {isExpanded && (
                  <div className="story-submission-detail">
                    <div className="story-submission-note-row">
                      {sub.teacherNote && !noteIsOpen && (
                        <p className="story-submission-note">Teacher note: {sub.teacherNote}</p>
                      )}
                      <button
                        type="button"
                        className="story-submission-note-button"
                        onClick={() => setOpenNotes((previous) => ({ ...previous, [sub.id]: !noteIsOpen }))}
                      >
                        {noteIsOpen ? "Hide note" : sub.teacherNote ? "Edit note" : "Add note"}
                      </button>
                    </div>
                    {noteIsOpen && (
                      <div className="story-submission-note-editor">
                        <label>
                          Teacher note for {sub.studentName}
                          <textarea
                            value={noteDraft}
                            onChange={(event) =>
                              setNoteDrafts((previous) => ({ ...previous, [sub.id]: event.target.value }))
                            }
                          />
                        </label>
                        <button
                          type="button"
                          className="story-submission-review-button"
                          disabled={isSaving}
                          onClick={() => void saveReview(sub, reviewStatus, noteDraft.trim() || null)}
                        >
                          Save note
                        </button>
                      </div>
                    )}
                    <div className="story-submission-scenes">
                      {sub.scenes.map((scene) => (
                        <div key={scene.sceneIndex} className="story-submission-scene">
                          <div className="sss-header">
                            <span className="sss-scene-num">Scene {scene.sceneIndex + 1}</span>
                            <span className="sss-score" title="Vocab / Tone / Character-by-character prosody">
                              Vocab {scene.vocabScore}% · Tone {scene.toneAccuracy}% · Prosody {scene.pronScore}%
                            </span>
                          </div>
                          {(scene.selfEvalContent || scene.selfEvalPronunciation) && (
                            <p
                              className="sss-self-eval"
                              title="Student's own rating, given before they saw this scene's results"
                            >
                              Self-eval:
                              {scene.selfEvalContent && (
                                <> {SELF_EVAL_EMOJI[scene.selfEvalContent]} meaning</>
                              )}
                              {scene.selfEvalContent && scene.selfEvalPronunciation && " ·"}
                              {scene.selfEvalPronunciation && (
                                <> {SELF_EVAL_EMOJI[scene.selfEvalPronunciation]} pronunciation</>
                              )}
                            </p>
                          )}
                          {scene.transcription && (
                            <p className="sss-transcription" lang="zh-TW">"{scene.transcription}"</p>
                          )}
                          <div className="sss-vocab-row">
                            {(scene.vocabUsed ?? []).map(w => (
                              <span key={w} className="sss-chip sss-chip-used" lang="zh-Hant">✓ {w}</span>
                            ))}
                            {(scene.vocabMissing ?? []).map(w => (
                              <span key={w} className="sss-chip sss-chip-missing" lang="zh-Hant">✗ {w}</span>
                            ))}
                          </div>
                          {scene.audioUrl && (
                            <audio
                              controls
                              src={resolveImageUrl(scene.audioUrl)}
                              className="sss-audio"
                              aria-label={`Scene ${scene.sceneIndex + 1} recording`}
                            />
                          )}
                        </div>
                      ))}
                    </div>
                    {(sub.concatenatedAudioUrl || sub.storyFeedback) && (
                      <StoryFeedbackCard
                        feedback={sub.storyFeedback}
                        concatenatedAudioUrl={sub.concatenatedAudioUrl}
                        scenes={sub.scenes}
                      />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {hasMoreSubmissions && (
        <button
          type="button"
          className="teacher-refresh-btn"
          onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
        >
          Load more
        </button>
      )}
    </section>
  );
}
