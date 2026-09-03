import JourneyBubble from "./JourneyBubble";

type AppJourneyBubbleProps = {
  visible: boolean;
  studentName: string;
  studentId?: string;
  storyCount: number;
  storyTitles: Record<string, string>;
  targetIds?: string[];
  refreshToken: string;
  onJumpToStory: (topicId: string) => void;
};

export default function AppJourneyBubble({
  visible,
  studentName,
  studentId,
  storyCount,
  storyTitles,
  targetIds,
  refreshToken,
  onJumpToStory,
}: AppJourneyBubbleProps) {
  if (!visible) return null;
  return (
    <JourneyBubble
      studentName={studentName}
      studentId={studentId}
      storyCount={storyCount}
      storyTitles={storyTitles}
      targetIds={targetIds}
      refreshToken={refreshToken}
      onJumpToStory={onJumpToStory}
    />
  );
}
