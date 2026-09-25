/**
 * Vocabulary Research Policy Layer, Epic 1: the progression-policy
 * abstraction and completion adapter.
 *
 * This module introduces the concept only - nothing in the real app calls
 * getVocabularyGateState yet. StoryRecorder, TopicSelector, lessonGroups.ts,
 * StudentSidebar and MyStoriesPage all keep reading stars/lessonGroups.ts
 * directly, unchanged, exactly as before this Epic. The production adapter
 * below is a thin wrapper around that same existing logic (isStoryFinished,
 * practiceUnlocked) - not a reimplementation - so it can never quietly
 * diverge from what production actually does. See
 * vocabularyProgression.test.ts for the tests proving that equivalence.
 *
 * The research adapter has no behavior yet (round-coverage completion is
 * Epic 3's job) - calling it throws rather than silently returning
 * plausible-looking but wrong data.
 */
import type { Topic } from "@entities/topic";
import { isStoryFinished, type StarsForTopic } from "./lessonGroups";
import { PRACTICE_UNLOCK_STARS, loadLocalStars, practiceUnlocked } from "@entities/vocabulary";
import { loadSubmittedStoryIds } from "./storyLevelProgress";
import { topicHasQuiz } from "@entities/vocabulary";

export type VocabularyProgressionPolicy = "production_accuracy" | "research_coverage";

export interface VocabularyGateState {
  /** The vocabulary quiz ladder itself is done (independent of submission). */
  coreRoundsCompleted: boolean;
  /** Speaking practice is available for this story right now. */
  speakingUnlocked: boolean;
  /** Matches lessonGroups.ts's isStoryFinished: submitted AND core complete
   * (or submitted alone when the story has no quiz at all). */
  storyVocabularyComplete: boolean;
  /** Short human-readable progress, e.g. "3 / 3". */
  progressDisplay: string;
}

function productionGateState(
  topic: Topic,
  submittedStoryIds: ReadonlySet<string>,
  starsFor: StarsForTopic,
): VocabularyGateState {
  const stars = starsFor(topic);
  const hasQuiz = topicHasQuiz(topic);
  return {
    coreRoundsCompleted: !hasQuiz || stars >= PRACTICE_UNLOCK_STARS,
    speakingUnlocked: practiceUnlocked(stars),
    storyVocabularyComplete: isStoryFinished(topic, submittedStoryIds, starsFor),
    progressDisplay: `${Math.min(stars, PRACTICE_UNLOCK_STARS)} / ${PRACTICE_UNLOCK_STARS}`,
  };
}

/** Not implemented until Epic 3 (research core progression). Throws rather
 * than returning plausible-but-wrong data, since nothing should be able to
 * reach this path yet - no student has an active research participation
 * (Epic 2 hasn't shipped an assignment engine), and no caller wires this in
 * before Epic 3 anyway. */
function researchGateState(): VocabularyGateState {
  throw new Error(
    "research_coverage progression is not implemented until Epic 3 - " +
      "getVocabularyGateState should not be called with this policy yet.",
  );
}

/** Pure form: takes already-known stars/submission data instead of reading
 * localStorage itself, so it's directly testable and reusable once a
 * research adapter needs a different data source (e.g. server-side round
 * coverage) instead of local stars. */
export function vocabularyGateStateFor(
  policy: VocabularyProgressionPolicy,
  topic: Topic,
  submittedStoryIds: ReadonlySet<string>,
  starsFor: StarsForTopic,
): VocabularyGateState {
  if (policy === "research_coverage") return researchGateState();
  return productionGateState(topic, submittedStoryIds, starsFor);
}

/** Convenience wrapper reading the same local-storage sources the rest of
 * the app already reads (loadSubmittedStoryIds, loadLocalStars) - the
 * production default when no research context is in play. */
export function getVocabularyGateState(
  topic: Topic,
  policy: VocabularyProgressionPolicy = "production_accuracy",
): VocabularyGateState {
  return vocabularyGateStateFor(
    policy,
    topic,
    loadSubmittedStoryIds(),
    (t) => loadLocalStars(t.sourceStory?.id ?? t.id),
  );
}
