// @ts-nocheck
import { BiText } from "../../components/BiLabel";
import { storyHasTierContent } from "../../utils/teacherStories";
import { useQuizReviewContext } from "./context";
import { useQuizGenerationActions } from "./generation-actions";
import { ReviewFilterBar } from "./review-chrome";
import { QuizReviewStory } from "./story-view";

export function QuizReviewPageView() {
  const { lessonGroups, lessonKey, setLessonKey, levels, level, setLevel, currentGroup, storyFilterId, setStoryFilterId, importInputRef } = useQuizReviewContext();
  const { onImportChange } = useQuizGenerationActions();
  return <main className="teacher-quiz-review">
    <input type="file" accept="application/json" ref={importInputRef} onChange={onImportChange} className="tqr-file-input" data-testid="tqr-import-input" />
    <ReviewFilterBar lessonGroups={lessonGroups} lessonKey={lessonKey} onLessonChange={setLessonKey} levels={levels} level={level} onLevelChange={setLevel} stories={currentGroup?.stories ?? []} storyFilterId={storyFilterId} onStoryChange={setStoryFilterId} />
    {!currentGroup && <p className="tqr-empty"><BiText zh="還沒有已發佈的故事。" pinyin="Hái méiyǒu yǐ fābù de gùshì." en="No published stories yet." /></p>}
    {currentGroup?.stories.filter((story) => storyFilterId === "all" || story.id === storyFilterId).map((story) => level !== "easy" && !storyHasTierContent(story, level) ? null : <QuizReviewStory key={story.id} story={story} />)}
  </main>;
}
