import { describe, expect, it } from "vitest";
import { serializeAudioRecord } from "./audioRecords";

describe("serializeAudioRecord", () => {
  it("preserves optional conversation identity fields", () => {
    const stored = serializeAudioRecord({
      id: "audio-1",
      audioBlob: new Blob(["audio"], { type: "audio/webm" }),
      timestamp: "2026-09-22T00:00:00.000Z",
      duration: 2,
      transcription: "你好",
      model: "webspeech",
      topicId: "topic-1",
      imageUrl: "/scene.png",
      imageIndex: 0,
      conversationId: "conversation-1",
      turnId: "student-1",
      turnIndex: 1,
    });

    expect(stored).toMatchObject({
      conversationId: "conversation-1",
      turnId: "student-1",
      turnIndex: 1,
    });
  });
});
