import { describe, expect, it } from "vitest";
import {
  groupTopicsByLesson,
  isLessonGroupUnlocked,
  lessonCompletion,
  lessonTitle,
  topicStoryId,
} from "./lessonGroups";
import type { Topic } from "../components/TopicSelector";

const topic = (id: string, lessonNumber: number | null, sourceId?: string): Topic =>
  ({
    id,
    lessonNumber,
    ...(sourceId ? { sourceStory: { id: sourceId } } : {}),
  }) as unknown as Topic;

describe("lessonTitle", () => {
  it("returns the Book 1 title for known lessons", () => {
    expect(lessonTitle(5)).toEqual({
      zh: "我的錢包在哪裡？",
      pinyin: "Wǒ de qiánbāo zài nǎlǐ?",
      en: "Where Is My Wallet?",
    });
  });

  it("falls back to 第N課 for numbers outside the book", () => {
    expect(lessonTitle(42)).toEqual({
      zh: "第 42 課",
      pinyin: "Dì 42 kè",
      en: "Lesson 42",
    });
  });
});

describe("groupTopicsByLesson", () => {
  it("groups by lesson number ascending with 其他 (null) last", () => {
    const groups = groupTopicsByLesson([
      topic("a", 7),
      topic("b", 5),
      topic("c", null),
      topic("d", 5),
    ]);
    expect(groups.map((g) => g.lessonNumber)).toEqual([5, 7, null]);
    expect(groups[0].topics.map((t) => t.id)).toEqual(["b", "d"]);
    expect(groups[2].topics.map((t) => t.id)).toEqual(["c"]);
  });

  it("omits the 其他 group when every topic has a lesson", () => {
    const groups = groupTopicsByLesson([topic("a", 1)]);
    expect(groups.map((g) => g.lessonNumber)).toEqual([1]);
  });

  it("returns no groups for no topics", () => {
    expect(groupTopicsByLesson([])).toEqual([]);
  });
});

describe("topicStoryId", () => {
  it("prefers the raw teacher-story id progress is tracked under", () => {
    expect(topicStoryId(topic("teacher-x", 1, "x"))).toBe("x");
    expect(topicStoryId(topic("plain-id", 1))).toBe("plain-id");
  });
});

describe("lessonCompletion", () => {
  it("counts submitted stories by their tracked id", () => {
    const group = {
      lessonNumber: 5,
      topics: [topic("teacher-a", 5, "a"), topic("teacher-b", 5, "b")],
    };
    expect(lessonCompletion(group, new Set(["a"]))).toEqual({ done: 1, total: 2 });
    expect(lessonCompletion(group, new Set())).toEqual({ done: 0, total: 2 });
  });
});

describe("isLessonGroupUnlocked", () => {
  const groups = groupTopicsByLesson([
    topic("teacher-a", 5, "a"),
    topic("teacher-b", 7, "b"),
    topic("teacher-c", 9, "c"),
    topic("teacher-d", null, "d"),
  ]);

  it("always opens the first numbered lesson and 其他", () => {
    const none = new Set<string>();
    expect(isLessonGroupUnlocked(groups, 0, none)).toBe(true);
    expect(isLessonGroupUnlocked(groups, 3, none)).toBe(true);
  });

  it("locks each later lesson until the previous existing lesson has a submitted story", () => {
    const none = new Set<string>();
    expect(isLessonGroupUnlocked(groups, 1, none)).toBe(false);
    expect(isLessonGroupUnlocked(groups, 2, none)).toBe(false);

    // Submitting lesson 5's story opens lesson 7 (the next *existing*
    // lesson — no phantom lesson 6 in the chain), but not lesson 9.
    const after5 = new Set(["a"]);
    expect(isLessonGroupUnlocked(groups, 1, after5)).toBe(true);
    expect(isLessonGroupUnlocked(groups, 2, after5)).toBe(false);

    const after7 = new Set(["a", "b"]);
    expect(isLessonGroupUnlocked(groups, 2, after7)).toBe(true);
  });

  it("is false for an out-of-range index", () => {
    expect(isLessonGroupUnlocked(groups, 99, new Set())).toBe(false);
  });
});
