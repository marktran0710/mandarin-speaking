import { useEffect, useState } from "react";
import {
  canUseDatabase,
  createCustomStory,
  listCustomStories,
  listStorySubmissions,
} from "../services/database";
import { loadBestLocalStars, loadLocalStars, practiceUnlocked } from "../utils/quizTiers";
import {
  type StoryDifficultyLevel,
  loadCustomStories,
  loadPublishedTeacherTopics,
  saveCustomStories,
  storyHasTierContent,
  storyToTopic,
} from "../utils/teacherStories";
import {
  groupTopicsByLesson,
  isLessonGroupUnlocked,
  isStoryUnlockedInLesson,
  lessonCompletion,
  lessonTitle,
  type LessonGroup,
} from "../utils/lessonGroups";
import {
  isStoryLevelUnlocked,
  loadSubmittedLevels,
  loadSubmittedStoryIds,
  mergeSubmittedStoryLevels,
} from "../utils/storyLevelProgress";
import { topicHasQuiz } from "../utils/topicQuiz";
import { getStudentId, getStudentName, isAdminSession } from "../utils/studentSession";
import "./TopicSelector.css";
import { BiLabel, BiText } from "./BiLabel";
import StudentIcon, { type StudentIconName } from "./StudentIcon";
import "./BiLabel.css";
import type { Topic, TopicSelectorProps } from "./topic-selector/types";
export type { Topic, TopicStartOptions, VocabGroup } from "./topic-selector/types";

export const TOPICS: Topic[] = [];

function isStoryModeTopic(_topic: Topic): boolean {
  return true;
}

export function SkillFocusLabel({ skillFocus }: { skillFocus: string }) {
  if (skillFocus === "Teacher published activity") {
    return <BiLabel k="teacher_published_activity" />;
  }
  return <>{skillFocus}</>;
}

export function getTopicVocabulary(topic: Topic, imageIndex: number): string[] {
  return topic.vocabulary[imageIndex] || [];
}

const LEVEL_ICONS: Record<StoryDifficultyLevel, StudentIconName> = {
  easy: "seedling",
  medium: "sprout",
  hard: "tree",
};

const LEVEL_COPY: Record<StoryDifficultyLevel, { zh: string; en: string }> = {
  easy: { zh: "簡單", en: "Easy" },
  medium: { zh: "中等", en: "Medium" },
  hard: { zh: "困難", en: "Hard" },
};

export default function TopicSelector({ onTopicSelect, onLevelSelect }: TopicSelectorProps) {
  const [topics, setTopics] = useState<Topic[]>(() =>
    loadPublishedTeacherTopics().filter(isStoryModeTopic),
  );
  const [loading, setLoading] = useState(canUseDatabase());
  // Which table-of-contents row is open: a lesson number, "other" for the
  // unassigned group, or null for the contents screen itself.
  const [openLesson, setOpenLesson] = useState<number | "other" | null>(null);

  useEffect(() => {
    if (!canUseDatabase()) return;
    let cancelled = false;
    const studentId = getStudentId();
    const studentName = getStudentName();
    const submissions = listStorySubmissions(undefined, { studentId, studentName }).catch(() => null);
    const hydrateSubmittedLevels = async () => {
      const serverSubmissions = await submissions;
      if (!cancelled && serverSubmissions) {
        mergeSubmittedStoryLevels(serverSubmissions, { studentId, studentName });
      }
    };

    listCustomStories()
      .then(async (dbStories) => {
        const localStories = loadCustomStories();
        const dbIds = new Set(dbStories.map((s) => s.id));
        const localOnly = localStories.filter((s) => !dbIds.has(s.id));
        if (localOnly.length > 0) {
          await Promise.allSettled(localOnly.map((s) => createCustomStory(s)));
          const merged = await listCustomStories();
          saveCustomStories(merged);
          const published = merged
            .filter((s) => s.published)
            .map((s) => storyToTopic(s as any, "easy", "approved"))
            .filter(isStoryModeTopic);
          await hydrateSubmittedLevels();
          if (cancelled) return;
          setTopics(published);
          return;
        }
        if (dbStories.length > 0) {
          saveCustomStories(dbStories);
        }
        const published = (dbStories.length > 0 ? dbStories : localStories)
          .filter((s) => s.published)
          .map((s) => storyToTopic(s as any, "easy", "approved"))
          .filter(isStoryModeTopic);
        await hydrateSubmittedLevels();
        if (cancelled) return;
        setTopics(published);
      })
      .catch((err) => console.error("Failed to load topics from backend:", err))
      .finally(() => setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="topic-selector">
        <div className="empty-state">
          <div className="empty-icon"><StudentIcon name="spark" size={28} /></div>
          <h2><BiLabel k="loading_activities" /></h2>
        </div>
      </div>
    );
  }

  if (topics.length === 0) {
    return (
      <div className="topic-selector">
        <section className="ts-hero">
          <div className="ts-hero-copy">
            <h1><BiLabel k="choose_a_daily_situation" align="left" /></h1>
            <p><BiText k="your_teacher_will_publish_speaking_activ" /></p>
          </div>
        </section>
        <div className="empty-state">
          <div className="empty-icon"><StudentIcon name="stories" size={28} /></div>
          <h2><BiLabel k="no_activities_yet" align="center" /></h2>
          <p><BiText k="your_teacher_will_create_and_publish_spe" /></p>
        </div>
      </div>
    );
  }

  const groups = groupTopicsByLesson(topics);
  const submittedIds = loadSubmittedStoryIds();
  // "You are here": the first unlocked numbered lesson that still has
  // unsubmitted stories — it gets the gold ring and the 繼續 chip.
  const nowIndex = groups.findIndex(
    (group, index) =>
      group.lessonNumber !== null &&
      isLessonGroupUnlocked(groups, index, submittedIds) &&
      lessonCompletion(group, submittedIds).done < group.topics.length,
  );

  // The per-story 🌱🌿🌳 tier track: which difficulty levels this story
  // offers, and for each whether it's been submitted, is open, or still
  // locked behind the previous tier. Only teacher stories carry tiers.
  // Was a status chip (not a button) on whichever level the card's primary
  // button already opened, since two controls landing on the same screen
  // read as one too many. Reverted at the user's request: with only two of
  // the three cells actually clickable, the row didn't look disabled, it
  // looked broken — the user reported "can't click Easy" as a bug, not as
  // an intentional label. All three are buttons again, Easy included.
  const renderTierTrack = (t: Topic, activityUnlocked: boolean) => {
    const story = t.sourceStory;
    if (!story) return null;
    const submittedLevels = loadSubmittedLevels(story.id);
    const levels = (["easy", "medium", "hard"] as const).filter(
      (level) => level === "easy" || storyHasTierContent(story, level),
    );
    return (
      <div
        className={`ts-tier-track${onLevelSelect ? " ts-tier-track-interactive" : ""}`}
        aria-label="Difficulty levels"
      >
        {levels.map((level) => {
          const state = !activityUnlocked
            ? "lock"
            : submittedLevels[level]
            ? "done"
            : isStoryLevelUnlocked(story.id, level)
              ? "open"
              : "lock";
          const tierTopic = storyToTopic(story, level, "approved");
          const needsQuiz =
            topicHasQuiz(tierTopic) &&
            !isAdminSession() &&
            !practiceUnlocked(loadLocalStars(tierTopic.id));
          const copy = LEVEL_COPY[level];
          const content = (
            <>
              <StudentIcon name={LEVEL_ICONS[level]} size={20} />
              <BiLabel zh={copy.zh} en={copy.en} align="center" />
            </>
          );
          if (!onLevelSelect) {
            return (
              <span key={level} className={`ts-tier-cell ts-tier-${state}`}>
                {content}
              </span>
            );
          }
          return (
            <button
              key={level}
              type="button"
              className={`ts-tier-cell ts-tier-${state}`}
              disabled={state === "lock"}
              aria-label={`${copy.en} difficulty${state === "done" ? ", completed" : state === "lock" ? activityUnlocked ? ", locked" : ", locked until the previous activity is completed" : needsQuiz ? ", vocabulary quiz required" : ""}`}
              onClick={(event) => {
                event.stopPropagation();
                onLevelSelect(t, level, needsQuiz ? { startAtQuiz: true } : undefined);
              }}
            >
              {content}
            </button>
          );
        })}
      </div>
    );
  };

  const renderTopicCard = (t: Topic, group: LessonGroup, index: number) => {
    const totalScenes = t.images.length;
    const totalWords = Object.values(t.vocabulary).flat().length;
    const previewImage = t.images[0];
    const unlocked = isStoryUnlockedInLesson(group, index, submittedIds);
    const hasQuiz = topicHasQuiz(t);
    const subLabel =
      group.lessonNumber != null && t.lessonSubOrder != null
        ? `${group.lessonNumber}-${t.lessonSubOrder}`
        : null;
    // isStoryUnlockedInLesson only needs the previous story SUBMITTED, not
    // 3-starred — a card can sit locked right next to a 3-star quiz result
    // on the story before it, which reads as broken with no explanation.
    // The lesson row already tells the student why IT is locked
    // ("先完成第 X 課"); a story card had no equivalent, so a click on Easy
    // or Medium here did nothing and looked like a dead button.
    const previousTopic = !unlocked ? group.topics[index - 1] : undefined;

    return (
      <article key={t.id} className={`ts-card${unlocked ? "" : " ts-card-locked"}`}>
        {/* Image strip */}
        <div className="ts-card-image">
          {previewImage ? (
            <img src={previewImage} alt={t.name} />
          ) : (
            <div className="ts-card-image-placeholder" aria-hidden="true">
              <StudentIcon name="image" size={32} />
            </div>
          )}
          {subLabel && <span className="ts-card-lesson-badge">{subLabel}</span>}
          {totalScenes > 1 && (
            <span className="ts-card-scene-badge">
              <BiLabel zh={`${totalScenes} 部分`} en={`${totalScenes} scenes`} />
            </span>
          )}
        </div>

        {/* Body */}
        <div className="ts-card-body">
          <div className="ts-card-meta-row">
            <span className="ts-card-skill">
              <SkillFocusLabel skillFocus={t.skillFocus} />
            </span>
          </div>

          <h3 className="ts-card-title">{t.name}</h3>

          {t.description && (
            <p className="ts-card-desc">{t.description}</p>
          )}

          <div className="ts-card-stats">
            <span><StudentIcon name="image" size={14} /> <BiLabel zh={`${totalScenes} 部分`} en={`${totalScenes} scenes`} /></span>
            {totalWords > 0 && (
              <span><StudentIcon name="stories" size={14} /> <BiLabel zh={`${totalWords} 詞`} en={`${totalWords} words`} /></span>
            )}
            {totalWords > 0 && (
              // Earned quiz stars for this story (this device's
              // localStorage — the same source the quiz itself seeds
              // from, so the card always matches what the student
              // last saw in the quiz).
              <span
                className="ts-card-stars"
                aria-label={`${loadBestLocalStars(t.id)} of 3 quiz stars earned`}
              >
                {Array.from({ length: 3 }, (_, starIndex) => (
                  <StudentIcon
                    key={starIndex}
                    name="star"
                    size={14}
                    className={starIndex < loadBestLocalStars(t.id) ? "is-earned" : "is-empty"}
                  />
                ))}
              </span>
            )}
          </div>

          {onTopicSelect && unlocked && (
            <button
              type="button"
              className="ts-card-open"
              onClick={() => onTopicSelect(t, hasQuiz ? { startAtQuiz: true } : undefined)}
            >
              <BiLabel
                zh={hasQuiz ? "開始生詞測驗" : "開始故事"}
                en={hasQuiz ? "Start vocabulary quiz" : "Start story"}
              />
              <StudentIcon name="arrow-right" size={17} aria-hidden="true" />
            </button>
          )}

          {onTopicSelect && !unlocked && (
            <p className="ts-card-locked-note">
              <StudentIcon name="lock" size={14} />
              <BiLabel
                zh={previousTopic ? `先交 ${previousTopic.name}` : "先完成上一個故事"}
                en={previousTopic ? `Submit "${previousTopic.name}" first` : "Finish the previous story first"}
                align="left"
              />
            </p>
          )}

          {renderTierTrack(t, unlocked)}
        </div>
      </article>
    );
  };

  // ── Lesson table of contents, each row an accordion over its own
  // stories — no separate "screen 2" navigation. ─────────────────────────
  const numberedGroups = groups.filter((group) => group.lessonNumber !== null);
  const otherGroup = groups.find((group) => group.lessonNumber === null) ?? null;

  // Lessons threaded on the same tone-contour journey path used inside a
  // practice session, instead of a separate hand-rolled spine — one visual
  // language for "progress along a sequence" everywhere in the app, and the
  // path itself (position, dimming, the current stop's glow) carries the
  // "you need to finish N first" meaning without spelling it out per row.
  /** One wide row per lesson: the lesson's own first scene image on the
   * left, its name in the middle, progress or the reason it is locked on
   * the right. The image is what makes a row recognisable at a glance, and
   * a locked lesson's image is desaturated so its state reads before any
   * text does. */
  const renderLessonRow = (group: LessonGroup, numberedIndex: number) => {
    const index = groups.indexOf(group);
    const unlocked = isLessonGroupUnlocked(groups, index, submittedIds);
    const { done, total } = lessonCompletion(group, submittedIds);
    const finished = total > 0 && done === total;
    const isNow = index === nowIndex;
    const title = lessonTitle(group.lessonNumber!);
    const previousNumber =
      numberedIndex > 0 ? numberedGroups[numberedIndex - 1].lessonNumber : null;
    const isOpen = openLesson === group.lessonNumber;
    const cover = group.topics.find((topic) => topic.images?.[0])?.images?.[0];
    const toggle = () =>
      setOpenLesson((current) => (current === group.lessonNumber ? null : group.lessonNumber!));

    return (
      <div className="ts-lesson-block" key={group.lessonNumber!}>
        <button
          type="button"
          className={`ts-lesson-row${unlocked ? "" : " is-locked"}${isNow ? " is-now" : ""}${finished ? " is-done" : ""}`}
          disabled={!unlocked}
          aria-expanded={unlocked ? isOpen : undefined}
          onClick={unlocked ? toggle : undefined}
        >
          <span className="ts-lesson-cover">
            {cover ? <img src={cover} alt="" /> : <span className="ts-lesson-cover-fallback" aria-hidden="true">{group.lessonNumber}</span>}
          </span>

          <span className="ts-lesson-body">
            <span className="ts-lesson-kicker">
              {`第 ${group.lessonNumber} 課`}
            </span>
            <BiLabel {...title} block align="left" />
          </span>

          <span className="ts-lesson-status">
            {!unlocked ? (
              <span className="ts-lesson-locked">
                <StudentIcon name="lock" size={14} />
                <BiLabel
                  zh={`先完成第 ${previousNumber} 課`}
                  en={`Finish Lesson ${previousNumber} first`}
                  align="left"
                />
              </span>
            ) : (
              <>
                <span className="ts-lesson-progress">
                  {finished ? (
                    <BiLabel zh="已完成" en="Complete" />
                  ) : (
                    <BiLabel zh={`${done}/${total} 個故事`} en={`${done}/${total} stories`} />
                  )}
                </span>
              <span className="ts-lesson-chevron" aria-hidden="true">
                <StudentIcon name={isOpen ? "chevron-up" : "chevron-down"} size={16} />
              </span>
              </>
            )}
          </span>
        </button>

        {isOpen && (
          <div className="ts-lesson-expanded">
            <div className="ts-grid">
              {group.topics.map((t, i) => renderTopicCard(t, group, i))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="topic-selector">
      <div className="ts-container">
      <header className="ts-toc-head">
        <div>
          <h1 className="ts-toc-title">
            目錄 <span className="ts-lesson-sub">Mùlù · Contents</span>
          </h1>
        </div>
        <div className="ts-book-chip">
          <img className="ts-book-cover" src="/textbook-cover.jpg" alt="" aria-hidden="true" />
          <span className="ts-book-name">
            時代華語 第一冊
            <span className="ts-lesson-sub">Modern Chinese · Book 1</span>
          </span>
        </div>
      </header>

      <div className="ts-lesson-list">
        {numberedGroups.map((group, numberedIndex) => renderLessonRow(group, numberedIndex))}
      </div>

      {otherGroup && (
        <div className="ts-other-block">
          <p className="ts-other-label">
            <BiLabel zh="其他" en="More practice" />
          </p>
          <div className="ts-lesson">
            <div
              className="ts-lesson-card"
              role="button"
              tabIndex={0}
              aria-expanded={openLesson === "other"}
              onClick={() => setOpenLesson((current) => (current === "other" ? null : "other"))}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setOpenLesson((current) => (current === "other" ? null : "other"));
                }
              }}
            >
              <div className="ts-num-tile ts-tile-other">
                <StudentIcon name="spark" size={24} />
              </div>
              <div className="ts-lesson-main">
                <div className="ts-lesson-title">
                  {otherGroup.topics.length === 1
                    ? otherGroup.topics[0].name
                    : `${otherGroup.topics.length} 個故事`}
                </div>
                <p className="ts-lesson-sub">
                  <BiLabel
                    zh="還沒有課號的故事"
                    en="Stories without a lesson yet"
                    align="left"
                  />
                </p>
              </div>
              <div className="ts-lesson-side">
                <span className="ts-side-chip ts-chip-open" aria-hidden="true">
                  <StudentIcon name={openLesson === "other" ? "chevron-up" : "chevron-down"} size={16} />
                </span>
              </div>
            </div>
          </div>
          {openLesson === "other" && (
            <div className="ts-lesson-expanded">
              <div className="ts-grid">
                {otherGroup.topics.map((t, i) => renderTopicCard(t, otherGroup, i))}
              </div>
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
}
