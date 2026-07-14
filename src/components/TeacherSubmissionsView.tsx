import type { StorySubmission } from "../services/database";
import { resolveImageUrl } from "../utils/teacherStories";
import StoryFeedbackCard from "./StoryFeedbackCard";

export default function TeacherSubmissionsView({
  submissions,
}: {
  submissions: StorySubmission[];
}) {
  return (
    <section className="teacher-panel teacher-submissions-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Student story submissions</p>
          <h2>Submitted Stories</h2>
        </div>
        <span className="queue-count">{submissions.length}</span>
      </div>
      {submissions.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No submissions yet</strong>
          <p>Students will appear here after they complete and submit all scenes of a story.</p>
        </div>
      ) : (
        <div className="story-submission-list">
          {submissions.map((sub) => (
            <div key={sub.id} className="story-submission-card">
              <div className="story-submission-header">
                <div>
                  <p className="story-submission-student">{sub.studentName}</p>
                  <p className="story-submission-title">{sub.storyTitle}</p>
                </div>
                <span className="story-submission-date">
                  {new Date(sub.submittedAt).toLocaleString()}
                </span>
              </div>
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
                        <span key={w} className="sss-chip sss-chip-used">✓ {w}</span>
                      ))}
                      {(scene.vocabMissing ?? []).map(w => (
                        <span key={w} className="sss-chip sss-chip-missing">✗ {w}</span>
                      ))}
                    </div>
                    {scene.audioUrl && (
                      <audio controls src={resolveImageUrl(scene.audioUrl)} className="sss-audio" />
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
          ))}
        </div>
      )}
    </section>
  );
}
