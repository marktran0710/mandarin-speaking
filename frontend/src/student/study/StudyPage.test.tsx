import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Topic } from "../../components/content/topic-selector/types";
import StudyPage from "./StudyPage";

function topic(id: string, name: string, lessonSubOrder: number): Topic {
  return {
    id,
    name,
    description: "rì cháng huì huà",
    skillFocus: "conversation",
    images: [],
    vocabulary: {},
    lessonNumber: 5,
    lessonSubOrder,
  };
}

describe("StudyPage", () => {
  it("renders the study hub layout and keeps lesson actions usable", () => {
    const onOpenTopic = vi.fn();
    const topics = [
      topic("s1", "我們去喝下午茶", 1),
      topic("s2", "週末有什麼安排？", 2),
      topic("s3", "我的房間", 3),
      topic("s4", "週末去買東西", 4),
    ];

    render(
      <StudyPage
        topics={topics}
        statusByStoryId={{
          s1: { status: "completed" },
          s2: { status: "in-progress" },
          s3: { status: "not-started" },
          s4: { status: "locked" },
        }}
        onOpenTopic={onOpenTopic}
      />,
    );

    expect(screen.getByRole("heading", { name: /第5課.*日常會話/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /課程目錄/ })).toHaveTextContent("4 課元");
    expect(screen.getByText("重點生詞")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "繼續" })).toBeInTheDocument();
    expect(screen.getByText("未開啟")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "預覽" }));
    expect(onOpenTopic).toHaveBeenCalledWith(topics[2]);
  });
});
