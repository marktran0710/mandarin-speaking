import type { Topic } from "../components/TopicSelector";

/** The lesson picker is the table of contents of 時代華語 第一冊 (Modern
 * Chinese Book 1) — the textbook every story in this app is grounded in.
 * Titles are hardcoded here (with a 第N課 fallback for numbers outside the
 * book) rather than authored per story, so every story tagged lesson 5
 * files under the same heading no matter which teacher created it. */
export interface LessonTitle {
  zh: string;
  pinyin: string;
  en: string;
}

export const BOOK1_LESSON_TITLES: Record<number, LessonTitle> = {
  1: { zh: "新同學", pinyin: "Xīn tóngxué", en: "The New Classmate" },
  2: { zh: "你幾點去學校？", pinyin: "Nǐ jǐ diǎn qù xuéxiào?", en: "What Time Do You Go to School?" },
  3: { zh: "買生日禮物", pinyin: "Mǎi shēngrì lǐwù", en: "Buying Birthday Gifts" },
  4: { zh: "你要咖啡還是茶？", pinyin: "Nǐ yào kāfēi háishì chá?", en: "Would You Like Coffee or Tea?" },
  5: { zh: "我的錢包在哪裡？", pinyin: "Wǒ de qiánbāo zài nǎlǐ?", en: "Where Is My Wallet?" },
  6: { zh: "週末去打網球吧！", pinyin: "Zhōumò qù dǎ wǎngqiú ba!", en: "Let's Play Tennis This Weekend!" },
  7: { zh: "怎麼到飯店去？", pinyin: "Zěnme dào fàndiàn qù?", en: "How Do We Get to the Hotel?" },
  8: { zh: "這條裙子真好看", pinyin: "Zhè tiáo qúnzi zhēn hǎokàn", en: "This Skirt Is Very Beautiful" },
  9: { zh: "我的中文課", pinyin: "Wǒ de Zhōngwén kè", en: "My Chinese Class" },
  10: { zh: "最近感冒的人很多", pinyin: "Zuìjìn gǎnmào de rén hěn duō", en: "Many People Got Colds Recently" },
  11: { zh: "你們是怎麼認識的？", pinyin: "Nǐmen shì zěnme rènshì de?", en: "How Did You Meet Each Other?" },
  12: { zh: "你想做什麼工作？", pinyin: "Nǐ xiǎng zuò shénme gōngzuò?", en: "What Job Do You Want to Do?" },
  13: { zh: "用手機上網", pinyin: "Yòng shǒujī shàngwǎng", en: "Get on the Internet with a Cell Phone" },
  14: { zh: "跨年活動", pinyin: "Kuànián huódòng", en: "New Year's Eve Celebration" },
  15: { zh: "十二生肖", pinyin: "Shí'èr shēngxiào", en: "The Chinese Animal Zodiac" },
};

export function lessonTitle(lessonNumber: number): LessonTitle {
  return (
    BOOK1_LESSON_TITLES[lessonNumber] ?? {
      zh: `第 ${lessonNumber} 課`,
      pinyin: `Dì ${lessonNumber} kè`,
      en: `Lesson ${lessonNumber}`,
    }
  );
}

/** One row of the table of contents: a numbered book lesson, or the
 * trailing 其他 group (lessonNumber null) holding stories that haven't been
 * assigned a lesson — kept visible and never locked, so no story ever
 * disappears from students just because it lacks a number. */
export interface LessonGroup {
  lessonNumber: number | null;
  topics: Topic[];
}

/** The id submission progress is tracked under (markStoryLevelSubmitted
 * keys on the raw teacher-story id, not the tier-suffixed topic id). */
export function topicStoryId(topic: Topic): string {
  return topic.sourceStory?.id ?? topic.id;
}

/** Groups topics into table-of-contents rows: numbered lessons ascending,
 * then one 其他 group for unassigned topics (omitted when empty). */
export function groupTopicsByLesson(topics: Topic[]): LessonGroup[] {
  const numbered = new Map<number, Topic[]>();
  const unassigned: Topic[] = [];
  for (const topic of topics) {
    if (topic.lessonNumber != null) {
      const list = numbered.get(topic.lessonNumber) ?? [];
      list.push(topic);
      numbered.set(topic.lessonNumber, list);
    } else {
      unassigned.push(topic);
    }
  }
  const groups: LessonGroup[] = [...numbered.entries()]
    .sort(([a], [b]) => a - b)
    .map(([lessonNumber, groupTopics]) => ({ lessonNumber, topics: groupTopics }));
  if (unassigned.length > 0) {
    groups.push({ lessonNumber: null, topics: unassigned });
  }
  return groups;
}

/** How many of this lesson's stories have been submitted (at any tier). */
export function lessonCompletion(
  group: LessonGroup,
  submittedStoryIds: ReadonlySet<string>,
): { done: number; total: number } {
  const done = group.topics.filter((topic) =>
    submittedStoryIds.has(topicStoryId(topic)),
  ).length;
  return { done, total: group.topics.length };
}

/** Sequential lesson lock, following the lessons that actually exist (a
 * published 5→7→9 chain locks 7 behind 5, not behind a nonexistent 6):
 * the first numbered lesson is always open, each later one opens once the
 * previous numbered lesson has at least one submitted story, and the 其他
 * group is always open. */
export function isLessonGroupUnlocked(
  groups: LessonGroup[],
  index: number,
  submittedStoryIds: ReadonlySet<string>,
): boolean {
  const group = groups[index];
  if (!group) return false;
  if (group.lessonNumber === null) return true;
  if (index === 0) return true;
  const previous = groups[index - 1];
  // Defensive: numbered groups always precede 其他, so previous is numbered.
  return lessonCompletion(previous, submittedStoryIds).done >= 1;
}
