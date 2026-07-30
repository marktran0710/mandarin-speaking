import { useMemo, useState } from "react";
import {
  updateSubmissionReview,
  type StorySubmission,
} from "../services/database";
import { resolveImageUrl } from "../utils/teacherStories";
import StoryFeedbackCard from "./StoryFeedbackCard";

type SubmissionSort = "needs-review" | "newest" | "oldest";

function submittedTime(submission: StorySubmission) {
  const time = Date.parse(submission.submittedAt);
  return Number.isNaN(time) ? 0 : time;
}

export default function TeacherSubmissionsView({
  submissions,
  onReviewUpdate,
}: {
  submissions: StorySubmission[];
  onReviewUpdate: (updated: StorySubmission) => void;
}) {
  const [studentFilter, setStudentFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SubmissionSort>("needs-review");
  const [overrides, setOverrides] = useState<Record<string, StorySubmission>>({});
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});
  const [openNotes, setOpenNotes] = useState<Record<string, boolean>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState("");

  const displayedSubmissions = submissions.map(
    (submission) => overrides[submission.id] ?? submission,
  );
  const students = useMemo(
    () => Array.from(new Set(displayedSubmissions.map((submission) => submission.studentName))).sort(),
    [displayedSubmissions],
  );
  const filteredSubmissions = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return displayedSubmissions
      .filter((submission) =>
        studentFilter === "all" || submission.studentName === studentFilter,
      )
      .filter((submission) => {
        if (!normalizedSearch) return true;
        return [submission.storyTitle, submission.studentName].some((value) =>
          value.toLowerCase().includes(normalizedSearch),
        );
      })
      .sort((a, b) => {
        if (sort === "oldest") return submittedTime(a) - submittedTime(b);
        if (sort === "newest") return submittedTime(b) - submittedTime(a);

        const reviewDifference =
          (a.reviewStatus === "reviewed" ? 1 : 0) -
          (b.reviewStatus === "reviewed" ? 1 : 0);
        return reviewDifference || submittedTime(b) - submittedTime(a);
      });
  }, [displayedSubmissions, search, sort, studentFilter]);

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
            <h2>Submitted Stories</h2>
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
    <>
      <section className="teacher-panel quiz-analytics-filters-panel">
        <div className="quiz-analytics-filters">
          <label>
            Student
            <select value={studentFilter} onChange={(event) => setStudentFilter(event.target.value)}>
              <option value="all">All students</option>
              {students.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          <label>
            Search submissions
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Story or student"
            />
          </label>
          <label>
            Sort
            <select value={sort} onChange={(event) => setSort(event.target.value as SubmissionSort)}>
              <option value="needs-review">Needs review first</option>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
        </div>
      </section>

      <section className="teacher-panel teacher-submissions-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Student story submissions</p>
            <h2>Submitted Stories</h2>
          </div>
          <span className="queue-count">{submissions.length}</span>
        </div>
        {reviewError && <p className="story-submission-review-error" role="alert">{reviewError}</p>}
        {filteredSubmissions.length === 0 ? (
          <div className="teacher-empty-panel">
            <strong>No submissions match this filter</strong>
            <p>Try a different student or search term.</p>
          </div>
        ) : (
          <div className="story-submission-list">
            {filteredSubmissions.map((sub) => {
              const reviewStatus = sub.reviewStatus ?? "pending";
              const noteDraft = noteDrafts[sub.id] ?? sub.teacherNote ?? "";
              const noteIsOpen = openNotes[sub.id];
              const isSaving = savingId === sub.id;

              return (
                <div key={sub.id} className="story-submission-card">
                  <div className="story-submission-header">
                    <div>
                      <p className="story-submission-student">{sub.studentName}</p>
                      <p className="story-submission-title">{sub.storyTitle}</p>
                    </div>
                    <div className="story-submission-review-actions">
                      <span className={`submission-review-badge submission-review-${reviewStatus}`}>
                        {reviewStatus === "reviewed" ? "Reviewed" : "Pending review"}
                      </span>
                      <span className="story-submission-date">
                        {new Date(sub.submittedAt).toLocaleString()}
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
                        className="story-submission-note-button"
                        onClick={() => setOpenNotes((previous) => ({ ...previous, [sub.id]: !noteIsOpen }))}
                      >
                        {noteIsOpen ? "Hide note" : sub.teacherNote ? "Edit note" : "Add note"}
                      </button>
                    </div>
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
                  {sub.teacherNote && !noteIsOpen && (
                    <p className="story-submission-note">Teacher note: {sub.teacherNote}</p>
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
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
