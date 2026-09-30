import { useCallback, useEffect, useMemo, useState } from "react";
import type { Topic } from "@entities/topic";
import { topicWithReferenceData, type StoryReferenceData } from "@entities/story";
import { canUseDatabase, getStoryReferenceData } from "../../services/database";

export type StoryReferenceDataStatus = "ready" | "loading" | "error";

/** Lesson-time pitch data for the open topic.
 *
 * The student story list omits the per-sentence pitch curves/contours (~77% of
 * its payload); Story Speaking and Conversation need them to show the model
 * voice and to score against it. Load them once per opened lesson and hand
 * back the topic with that data overlaid. Callers that record audio must wait
 * for "ready" - scoring without the reference would silently degrade.
 */
export function useStoryReferenceData(topic: Topic | null) {
  const storyId = topic?.sourceStory?.id ?? null;
  // A full-list topic already carries the data; nothing to fetch.
  const alreadyLoaded = Boolean(topic?.sentenceReferenceCurves || topic?.sentenceModelContours);
  const needsFetch = Boolean(storyId) && !alreadyLoaded && canUseDatabase();
  const [loaded, setLoaded] = useState<{ storyId: string; data: StoryReferenceData } | null>(null);
  const [failedFor, setFailedFor] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!needsFetch || !storyId) return;
    let cancelled = false;
    setFailedFor(null);
    getStoryReferenceData(storyId)
      .then((data) => { if (!cancelled) setLoaded({ storyId, data }); })
      .catch(() => { if (!cancelled) setFailedFor(storyId); });
    return () => { cancelled = true; };
  }, [needsFetch, storyId, attempt]);

  const data = loaded && loaded.storyId === storyId ? loaded.data : null;
  const merged = useMemo(
    () => (topic && data ? topicWithReferenceData(topic, data) : topic),
    [topic, data],
  );
  const status: StoryReferenceDataStatus = !needsFetch || data
    ? "ready"
    : failedFor === storyId ? "error" : "loading";
  const retry = useCallback(() => setAttempt((count) => count + 1), []);

  return { topic: merged, status, retry };
}
