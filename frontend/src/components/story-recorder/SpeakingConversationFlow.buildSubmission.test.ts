import { describe, expect, it } from "vitest";
import { buildConversationSubmission } from "./SpeakingConversationFlow";
import type { SceneSubmission } from "../../services/database";
import type { Topic } from "./StoryRecorder/storyContent";

const topic: Topic = {
  id: "conversation-topic",
  name: "Afternoon tea",
  images: ["/scene.png"],
  vocabulary: {},
  difficultyLevel: "easy",
};

const scenes: SceneSubmission[] = [
  { sceneIndex: 0, imageUrl: "/scene.png", transcription: "你好！", vocabUsed: [], vocabMissing: [], vocabScore: 0, toneAccuracy: 90, pronScore: 90, conversationId: "conversation:conversation-topic", turnId: "student-1", turnIndex: 1 },
  { sceneIndex: 0, imageUrl: "/scene.png", transcription: "我很好。", vocabUsed: [], vocabMissing: [], vocabScore: 0, toneAccuracy: 85, pronScore: 85, conversationId: "conversation:conversation-topic", turnId: "student-2", turnIndex: 3 },
];

describe("buildConversationSubmission", () => {
  it("carries every completed turn's result as one scenes array", () => {
    const submission = buildConversationSubmission(topic, "student-1", "Test Student", scenes, () => 1_700_000_000_000);

    expect(submission.storyId).toBe("conversation-topic");
    expect(submission.storyTitle).toBe("Afternoon tea");
    expect(submission.studentId).toBe("student-1");
    expect(submission.studentName).toBe("Test Student");
    expect(submission.scenes).toBe(scenes);
    expect(submission.scenes).toHaveLength(2);
  });

  it("derives a deterministic id and timestamp from the injected clock", () => {
    const submission = buildConversationSubmission(topic, "student-1", "Test Student", scenes, () => 1_700_000_000_000);
    expect(submission.id).toBe("submission-1700000000000");
    expect(submission.submittedAt).toBe(new Date(1_700_000_000_000).toISOString());
  });
});
