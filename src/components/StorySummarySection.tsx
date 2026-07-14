import type { ReactNode } from "react";
import type { SceneSubmission, StoryFeedback } from "../services/database";
import StoryFeedbackCard from "./StoryFeedbackCard";
import JourneyPath, { type JourneyStopStatus } from "./JourneyPath";
import { BiLabel } from "./BiLabel";
import type { Topic } from "./StoryRecorder";

/** Scene-stop data shared with the practice header's journey path — everything
 * but the per-caller `onClick`, which this section supplies itself. */
export interface JourneyStopBase {
  key: number;
  img: string;
  idx: number;
  status: JourneyStopStatus;
  thumbnail: string;
  label: ReactNode;
  badge?: string;
}

interface StorySummarySectionProps {
  topic: Topic;
  journeyStopsBase: JourneyStopBase[];
  storySubmitted: boolean;
  storyFeedbackResult: {
    concatenatedAudioUrl?: string | null;
    storyFeedback?: StoryFeedback | null;
  } | null;
  sceneRecordings: Record<number, SceneSubmission>;
  submitError: string | null;
  allScenesRecorded: boolean;
  completedSceneCount: number;
  totalScenes: number;
  onSubmitStory: () => void;
  /** A journey stop was clicked — jump back to that scene in practice. */
  onJourneyStopClick: (idx: number, img: string) => void;
}

export default function StorySummarySection({
  topic,
  journeyStopsBase,
  storySubmitted,
  storyFeedbackResult,
  sceneRecordings,
  submitError,
  allScenesRecorded,
  completedSceneCount,
  totalScenes,
  onSubmitStory,
  onJourneyStopClick,
}: StorySummarySectionProps) {
  return (
    <>
      <JourneyPath
        stops={journeyStopsBase.map((stop) => ({
          ...stop,
          onClick: () => onJourneyStopClick(stop.idx, stop.img),
        }))}
      />

      {storySubmitted ? (
        <>
          <div className="story-submit-panel story-submit-success">
            <span className="story-submit-icon">✓</span>
            <div>
              <p className="story-submit-title">
                <BiLabel k="story_submitted" />
              </p>
              <p className="story-submit-hint">
                <BiLabel
                  zh={`你的老師現在可以看全部 ${totalScenes} 個場景。`}
                  pinyin={`Nǐ de lǎoshī xiànzài kěyǐ kàn quánbù ${totalScenes} ge chǎngjǐng.`}
                  en={`Your teacher can now review all ${totalScenes} scenes.`}
                />
              </p>
            </div>
          </div>
          <StoryFeedbackCard
            feedback={storyFeedbackResult?.storyFeedback}
            concatenatedAudioUrl={storyFeedbackResult?.concatenatedAudioUrl}
            scenes={Object.values(sceneRecordings)}
          />
        </>
      ) : (
        <div className="story-submit-panel">
          <div className="story-submit-progress">
            {topic.images.map((_, si) => (
              <div
                key={si}
                className={`story-submit-dot ${sceneRecordings[si] ? "done" : "pending"}`}
                title={`場景 ${si + 1}${sceneRecordings[si] ? " ✓ 已完成" : " — 還沒錄音 not yet recorded"} Scene ${si + 1}`}
              />
            ))}
          </div>
          <p className="story-submit-label">
            {allScenesRecorded ? (
              <BiLabel k="all_scenes_recorded_ready_to_submit" />
            ) : (
              <BiLabel
                zh={`已錄 ${completedSceneCount} / ${totalScenes} 個場景`}
                pinyin={`Yǐ lù ${completedSceneCount} / ${totalScenes} ge chǎngjǐng`}
                en={`${completedSceneCount} of ${totalScenes} scenes recorded`}
              />
            )}
          </p>
          {submitError && <p className="story-submit-error">{submitError}</p>}
          <button
            className="btn-submit-story"
            disabled={!allScenesRecorded}
            onClick={onSubmitStory}
          >
            <BiLabel k="submit_story_to_teacher" />
          </button>
        </div>
      )}
    </>
  );
}
