import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import { getStoryReferenceData } from "../../services/database";
import { useStoryReferenceData } from "./useStoryReferenceData";

vi.mock("../../services/database", () => ({
  canUseDatabase: () => true,
  getStoryReferenceData: vi.fn(),
}));

const curves = JSON.stringify({ "你": [0.5, 0.4] });

function topicFor(storyId: string, extra: Partial<Topic> = {}): Topic {
  return {
    id: `teacher-${storyId}`,
    name: storyId,
    images: [],
    prompts: [],
    vocabulary: {},
    sourceStory: { id: storyId, title: storyId, frames: [] },
    ...extra,
  } as Topic;
}

beforeEach(() => {
  vi.mocked(getStoryReferenceData).mockReset();
});

describe("useStoryReferenceData", () => {
  it("is loading until the pitch data arrives, then overlays it on the topic", async () => {
    vi.mocked(getStoryReferenceData).mockResolvedValue({ storyId: "s1", frames: [{ sentenceReferenceCurves: curves }] });
    const topic = topicFor("s1");
    const { result } = renderHook(() => useStoryReferenceData(topic));

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.topic?.sentenceReferenceCurves?.[0]).toEqual({ 你: [0.5, 0.4] });
    expect(getStoryReferenceData).toHaveBeenCalledTimes(1);
  });

  it("does not fetch when the topic already carries its pitch data or there is no topic", () => {
    const loaded = topicFor("s2", { sentenceReferenceCurves: { 0: { 你: [1] } } });
    const first = renderHook(() => useStoryReferenceData(loaded));
    expect(first.result.current.status).toBe("ready");
    const none = renderHook(() => useStoryReferenceData(null));
    expect(none.result.current).toMatchObject({ status: "ready", topic: null });
    expect(getStoryReferenceData).not.toHaveBeenCalled();
  });

  it("reports an error and retries on request", async () => {
    vi.mocked(getStoryReferenceData).mockRejectedValueOnce(new Error("down"));
    const topic = topicFor("s3");
    const { result } = renderHook(() => useStoryReferenceData(topic));
    await waitFor(() => expect(result.current.status).toBe("error"));

    vi.mocked(getStoryReferenceData).mockResolvedValue({ storyId: "s3", frames: [{}] });
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(getStoryReferenceData).toHaveBeenCalledTimes(2);
  });

  it("does not show another lesson's pitch data after switching stories", async () => {
    vi.mocked(getStoryReferenceData).mockImplementation(async (id: string) => ({
      storyId: id,
      frames: [{ sentenceReferenceCurves: id === "a" ? curves : JSON.stringify({ 好: [9] }) }],
    }));
    const { result, rerender } = renderHook(({ topic }) => useStoryReferenceData(topic), {
      initialProps: { topic: topicFor("a") },
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    rerender({ topic: topicFor("b") });
    expect(result.current.status).toBe("loading");
    expect(result.current.topic?.sentenceReferenceCurves).toBeUndefined();
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.topic?.sentenceReferenceCurves?.[0]).toEqual({ 好: [9] });
  });
});
