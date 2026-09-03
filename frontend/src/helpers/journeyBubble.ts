import type { Topic } from "../components/TopicSelector";
import {
  groupTopicsByLesson,
  isLessonGroupUnlocked,
  lessonCompletion,
} from "../utils/lessonGroups";
import { loadSubmittedStoryIds } from "../utils/storyLevelProgress";

export function getJourneyBubbleTargetIds(
  storyTopics: Topic[],
  quizStoryTopics: Topic[],
): string[] | undefined {
  const groups = groupTopicsByLesson(storyTopics);
  const submittedIds = loadSubmittedStoryIds();
  const nowGroup = groups.find(
    (group, index) =>
      group.lessonNumber !== null &&
      isLessonGroupUnlocked(groups, index, submittedIds) &&
      lessonCompletion(group, submittedIds).done < group.topics.length,
  );
  if (!nowGroup) return undefined;
  const quizIds = new Set(quizStoryTopics.map((topic) => topic.id));
  return nowGroup.topics.map((topic) => topic.id).filter((id) => quizIds.has(id));
}
