// @ts-nocheck
import React from "react";
import { resolveImageUrl, storyToTopic } from "../../utils/teacherStories";
import { narrativeModeLabel } from "../../utils/myStoriesUtils";
import { storyQuizExclusions } from "../../utils/quizExclusions";
import { buildApprovedMaterial, storyQuizNeedsReview } from "../../utils/quizApprovedMaterial";

function StoryItemActionGroup({ story, onTogglePublish, onEdit, onExport, onDelete }) {
  const closeMenu = (event, action) => { action(); event.currentTarget.closest("details")?.removeAttribute("open"); };
  return <div className="custom-story-item-actions">
    <button type="button" className="btn-publish-custom-story" onClick={() => onTogglePublish(story.id)}>{story.published ? "Unpublish" : "Publish"}</button>
    <button type="button" className="btn-edit-custom-story" onClick={() => onEdit(story)}>Edit</button>
    <details className="custom-story-item-menu"><summary aria-label="More actions">⋯</summary><div className="custom-story-item-menu-list" role="menu">
      <button type="button" role="menuitem" className="btn-export-custom-story" onClick={(event) => closeMenu(event, () => onExport(story))}>Export</button>
      <button type="button" role="menuitem" className="btn-delete-custom-story" onClick={(event) => closeMenu(event, () => onDelete(story.id))}>Delete</button>
    </div></details>
  </div>;
}

function StoryRubric({ rubricScores }) {
  const labels = { focus: "Focus", narrative: "Narrative elements", plot: "Five-stage plot", wordChoice: "Word choice", conventions: "Conventions" };
  return <section className="teacher-material-rubric" aria-label="Material rubric score"><h4>Rubric evaluation</h4>
    {(["easy", "medium", "hard"] as const).map((level) => {
      const score = rubricScores?.[level] as Record<string, unknown> | undefined;
      return <div key={level} className="teacher-material-rubric-level"><strong>{level[0].toUpperCase() + level.slice(1)}</strong><div className="teacher-material-rubric-grid">
        {(["focus", "narrative", "plot", "wordChoice", "conventions"] as const).map((key) => <span key={key}><b>{labels[key]}</b> {String(score?.[key] ?? "-")}/10</span>)}
      </div><p className="teacher-material-rubric-total">Total: {String(score?.total ?? "-")}/50</p></div>;
    })}
    <a href="https://doi.org/10.1080/09588221.2025.2561608" target="_blank" rel="noreferrer">Research rubric reference</a>
  </section>;
}

function StoryLibraryItem({ story, ...actions }) {
  const quizNeedsReview = storyQuizNeedsReview(story, buildApprovedMaterial(storyToTopic(story, "easy"), storyQuizExclusions(story)), "easy");
  return <article className="custom-story-item"><div className="custom-story-item-header"><div><strong>
    {story.lessonNumber != null && <span className="topic-lesson-badge">Lesson {story.lessonNumber}{story.lessonSubOrder != null && `-${story.lessonSubOrder}`}</span>}{story.title}
  </strong>{quizNeedsReview && <span className="quiz-needs-review-badge" title="Quiz material has changed since it was last approved — check Quiz Review before students see it.">⚙️ Quiz needs review</span>}
  <span>{story.published ? "Published" : "Draft"}{" - "}{narrativeModeLabel(story.narrativeMode)}</span></div>
  <StoryItemActionGroup story={story} {...actions} /></div>
  <p>{story.learningGoal}</p>{story.rubricScores && <StoryRubric rubricScores={story.rubricScores} />}
  <div className="custom-story-frame-strip">{story.frames.map((frame, index) => <div className="custom-story-mini-frame" key={index}>
    {frame.imageUrl ? <img src={resolveImageUrl(frame.imageUrl)} alt={`${story.title} frame ${index + 1}`} /> : <span>{index + 1}</span>}
  </div>)}</div>
  </article>;
}

export default function StoryBuilderLibrary({ customStories, filteredCustomStories, lessonNumbersInUse, hasStoriesWithoutLesson,
  lessonFilter, onLessonFilterChange, importError, importNotice, onImport, onTogglePublish, onEdit, onExport, onDelete }) {
  return <div className="custom-story-library" aria-label="Saved custom stories"><div className="custom-story-library-header"><h3>Teacher Story Library</h3>
    {(lessonNumbersInUse.length > 0 || hasStoriesWithoutLesson) && <select className="custom-story-lesson-filter" aria-label="Filter stories by lesson" value={lessonFilter} onChange={(event) => onLessonFilterChange(event.target.value)}>
      <option value="all">All lessons</option>{lessonNumbersInUse.map((lessonNumber) => <option key={lessonNumber} value={String(lessonNumber)}>Lesson {lessonNumber}</option>)}{hasStoriesWithoutLesson && <option value="others">Others</option>}
    </select>}
    <label className="btn-import-custom-story">Import story<input type="file" accept="application/json,.json" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) onImport(file); }} /></label>
  </div>
  {importError && <div className="teacher-form-alert" role="alert">{importError}</div>}{importNotice && <div className="teacher-form-success" role="status">{importNotice}</div>}
  {filteredCustomStories.length === 0 ? <div className="teacher-empty-panel"><strong>{customStories.length === 0 ? "No custom stories yet" : "No stories for this lesson"}</strong><p>{customStories.length === 0 ? "Add image links and prompts to prepare a reusable classroom speaking activity." : "Try a different lesson filter."}</p></div> :
    <div className="custom-story-list">{filteredCustomStories.map((story) => <StoryLibraryItem key={story.id} story={story} onTogglePublish={onTogglePublish} onEdit={onEdit} onExport={onExport} onDelete={onDelete} />)}</div>}
  </div>;
}
