import { describe, expect, it } from "vitest";
import {
  groupTopicsByLesson,
  isLessonGroupUnlocked,
  isStoryFinished,
  isStoryUnlockedInLesson,
  lessonCompletion,
  lessonHasOrderedStories,
  lessonTitle,
  topicStoryId,
} from "./lessonGroups";
import type { Topic } from "../components/TopicSelector";

// No images/vocabulary, so topicHasQuiz is false and these stories are
// finished on submission alone — the tests that care about the ⭐⭐⭐ half of
// the rule build quiz-capable topics with quizTopic() instead.
const topic = (
  id: string,
  lessonNumber: number | null,
  sourceId?: string,
  lessonSubOrder?: number | null,
): Topic =>
  ({
    id,
    lessonNumber,
    lessonSubOrder: lessonSubOrder ?? null,
    images: [],
    vocabulary: {},
    ...(sourceId ? { sourceStory: { id: sourceId } } : {}),
  }) as unknown as Topic;

/** A story with one glossed word — enough for collectQuizEntries to build a
 * real quiz, so the ⭐⭐ requirement applies to it. */
const quizTopic = (id: string, lessonNumber: number | null, sourceId?: string): Topic =>
  ({
    ...topic(id, lessonNumber, sourceId),
    images: ["scene.png"],
    vocabulary: { 0: ["書"] },
    vocabularyTranslation: { 0: ["book"] },
  }) as unknown as Topic;

const noStars = () => 0;
const oneStar = () => 1;
const twoStars = () => 2;
const threeStars = () => 3;

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

  it("sorts a lesson's topics by lessonSubOrder once every story in it has one", () => {
    const groups = groupTopicsByLesson([
      topic("teacher-c", 5, "c", 3),
      topic("teacher-a", 5, "a", 1),
      topic("teacher-b", 5, "b", 2),
    ]);
    expect(groups[0].topics.map((t) => t.id)).toEqual(["teacher-a", "teacher-b", "teacher-c"]);
  });

  it("keeps ordered stories ahead of legacy stories without a sub-order", () => {
    const groups = groupTopicsByLesson([
      topic("teacher-legacy", 5, "legacy"), // no sub-order
      topic("teacher-b", 5, "b", 2),
      topic("teacher-a", 5, "a", 1),
    ]);
    expect(groups[0].topics.map((t) => t.id)).toEqual([
      "teacher-a",
      "teacher-b",
      "teacher-legacy",
    ]);
  });
});

describe("lessonHasOrderedStories", () => {
  it("is true only once every topic in the group has a lessonSubOrder", () => {
    const ordered = { lessonNumber: 5, topics: [topic("a", 5, "a", 1), topic("b", 5, "b", 2)] };
    const partial = { lessonNumber: 5, topics: [topic("a", 5, "a", 1), topic("b", 5, "b")] };
    const empty = { lessonNumber: 5, topics: [] };
    expect(lessonHasOrderedStories(ordered)).toBe(true);
    expect(lessonHasOrderedStories(partial)).toBe(false);
    expect(lessonHasOrderedStories(empty)).toBe(false);
  });
});

describe("isStoryUnlockedInLesson", () => {
  it("still locks the next story when legacy order metadata is incomplete", () => {
    const group = { lessonNumber: 5, topics: [topic("a", 5, "a"), topic("b", 5, "b")] };
    expect(isStoryUnlockedInLesson(group, 0, new Set())).toBe(true);
    expect(isStoryUnlockedInLesson(group, 1, new Set())).toBe(false);
    expect(isStoryUnlockedInLesson(group, 1, new Set(["a"]))).toBe(true);
  });

  it("always opens the first story in an ordered lesson", () => {
    const group = groupTopicsByLesson([topic("a", 5, "a", 1), topic("b", 5, "b", 2)])[0];
    expect(isStoryUnlockedInLesson(group, 0, new Set())).toBe(true);
  });

  it("needs the previous story submitted — not ⭐⭐, just submitted", () => {
    const group = groupTopicsByLesson([topic("a", 5, "a", 1), topic("b", 5, "b", 2)])[0];
    expect(isStoryUnlockedInLesson(group, 1, new Set())).toBe(false);
    expect(isStoryUnlockedInLesson(group, 1, new Set(["a"]))).toBe(true);
  });

  it("checks only the immediately preceding story in a 3-story chain", () => {
    const group = groupTopicsByLesson([
      topic("a", 5, "a", 1),
      topic("b", 5, "b", 2),
      topic("c", 5, "c", 3),
    ])[0];
    expect(isStoryUnlockedInLesson(group, 2, new Set(["a"]))).toBe(false);
    expect(isStoryUnlockedInLesson(group, 2, new Set(["b"]))).toBe(true);
  });
});

describe("topicStoryId", () => {
  it("prefers the raw teacher-story id progress is tracked under", () => {
    expect(topicStoryId(topic("teacher-x", 1, "x"))).toBe("x");
    expect(topicStoryId(topic("plain-id", 1))).toBe("plain-id");
  });
});

describe("isStoryFinished", () => {
  it("needs a submission before anything else", () => {
    expect(isStoryFinished(quizTopic("teacher-a", 5, "a"), new Set(), threeStars)).toBe(false);
  });

  it("needs ⭐⭐⭐ on top of the submission when the story has a quiz", () => {
    const t = quizTopic("teacher-a", 5, "a");
    expect(isStoryFinished(t, new Set(["a"]), noStars)).toBe(false);
    expect(isStoryFinished(t, new Set(["a"]), () => 1)).toBe(false);
    expect(isStoryFinished(t, new Set(["a"]), twoStars)).toBe(false);
    expect(isStoryFinished(t, new Set(["a"]), threeStars)).toBe(true);
  });

  it("finishes a quiz-less story on submission alone, so it can't wall off the book", () => {
    expect(isStoryFinished(topic("teacher-a", 5, "a"), new Set(["a"]), noStars)).toBe(true);
  });
});

describe("lessonCompletion", () => {
  it("counts submitted stories by their tracked id", () => {
    const group = {
      lessonNumber: 5,
      topics: [topic("teacher-a", 5, "a"), topic("teacher-b", 5, "b")],
    };
    expect(lessonCompletion(group, new Set(["a"]), noStars)).toEqual({ done: 1, total: 2 });
    expect(lessonCompletion(group, new Set(), noStars)).toEqual({ done: 0, total: 2 });
  });

  it("does not count a submitted story that hasn't earned ⭐⭐⭐", () => {
    const group = {
      lessonNumber: 5,
      topics: [quizTopic("teacher-a", 5, "a"), quizTopic("teacher-b", 5, "b")],
    };
    expect(lessonCompletion(group, new Set(["a", "b"]), noStars)).toEqual({
      done: 0,
      total: 2,
    });
    expect(lessonCompletion(group, new Set(["a", "b"]), oneStar)).toEqual({
      done: 0,
      total: 2,
    });
    expect(lessonCompletion(group, new Set(["a", "b"]), twoStars)).toEqual({
      done: 0,
      total: 2,
    });
    expect(lessonCompletion(group, new Set(["a", "b"]), threeStars)).toEqual({
      done: 2,
      total: 2,
    });
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
    expect(isLessonGroupUnlocked(groups, 0, none, noStars)).toBe(true);
    expect(isLessonGroupUnlocked(groups, 3, none, noStars)).toBe(true);
  });

  it("locks each later lesson until the previous existing lesson is finished", () => {
    const none = new Set<string>();
    expect(isLessonGroupUnlocked(groups, 1, none, noStars)).toBe(false);
    expect(isLessonGroupUnlocked(groups, 2, none, noStars)).toBe(false);

    // Finishing lesson 5 opens lesson 7 (the next *existing* lesson — no
    // phantom lesson 6 in the chain), but not lesson 9.
    const after5 = new Set(["a"]);
    expect(isLessonGroupUnlocked(groups, 1, after5, noStars)).toBe(true);
    expect(isLessonGroupUnlocked(groups, 2, after5, noStars)).toBe(false);

    const after7 = new Set(["a", "b"]);
    expect(isLessonGroupUnlocked(groups, 2, after7, noStars)).toBe(true);
  });

  it("needs EVERY story in the previous lesson, not just one", () => {
    const multi = groupTopicsByLesson([
      topic("teacher-a1", 5, "a1"),
      topic("teacher-a2", 5, "a2"),
      topic("teacher-b", 7, "b"),
    ]);
    expect(isLessonGroupUnlocked(multi, 1, new Set(["a1"]), noStars)).toBe(false);
    expect(isLessonGroupUnlocked(multi, 1, new Set(["a1", "a2"]), noStars)).toBe(true);
  });

  it("holds the next lesson shut until the previous lesson's quizzes hit ⭐⭐⭐", () => {
    const quizzed = groupTopicsByLesson([
      quizTopic("teacher-a", 5, "a"),
      quizTopic("teacher-b", 7, "b"),
    ]);
    const submitted = new Set(["a"]);
    expect(isLessonGroupUnlocked(quizzed, 1, submitted, () => 1)).toBe(false);
    expect(isLessonGroupUnlocked(quizzed, 1, submitted, twoStars)).toBe(false);
    expect(isLessonGroupUnlocked(quizzed, 1, submitted, threeStars)).toBe(true);
  });

  it("is false for an out-of-range index", () => {
    expect(isLessonGroupUnlocked(groups, 99, new Set(), noStars)).toBe(false);
  });
});
