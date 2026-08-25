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
import JourneyPath, { type JourneyStop } from "./JourneyPath";
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

const LEVEL_COPY: Record<StoryDifficultyLevel, { zh: string; pinyin: string; en: string }> = {
  easy: { zh: "簡單", pinyin: "Jiǎndān", en: "Easy" },
  medium: { zh: "中等", pinyin: "Zhōngděng", en: "Medium" },
  hard: { zh: "困難", pinyin: "Kùnnán", en: "Hard" },
};

export default function TopicSelector({ onLevelSelect }: TopicSelectorProps) {
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
            <h1><BiLabel k="choose_a_daily_situation" /></h1>
            <p><BiText k="your_teacher_will_publish_speaking_activ" /></p>
          </div>
        </section>
        <div className="empty-state">
          <div className="empty-icon"><StudentIcon name="stories" size={28} /></div>
          <h2><BiLabel k="no_activities_yet" /></h2>
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
              <BiLabel zh={copy.zh} pinyin={copy.pinyin} en={copy.en} />
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
    const subLabel =
      group.lessonNumber != null && t.lessonSubOrder != null
        ? `${group.lessonNumber}-${t.lessonSubOrder}`
        : null;

    return (
      <article key={t.id} className={`ts-card${unlocked ? "" : " ts-card-locked"}`}>
        {/* Image strip */}
        <div className="ts-card-image">
          {previewImage ? (
            <img src={previewImage} alt={t.name} />
          ) : (
            <div className="ts-card-image-placeholder">🎬</div>
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
            <span>🎬 <BiLabel zh={`${totalScenes} 部分`} en={`${totalScenes} scenes`} /></span>
            {totalWords > 0 && (
              <span>📝 <BiLabel zh={`${totalWords} 詞`} en={`${totalWords} words`} /></span>
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
                {"⭐".repeat(loadBestLocalStars(t.id))}
                {"☆".repeat(3 - loadBestLocalStars(t.id))}
              </span>
            )}
          </div>

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
  const journeyStops: JourneyStop[] = numberedGroups.map((group, numberedIndex) => {
    const index = groups.indexOf(group);
    const unlocked = isLessonGroupUnlocked(groups, index, submittedIds);
    const { done, total } = lessonCompletion(group, submittedIds);
    const finished = total > 0 && done === total;
    const isNow = index === nowIndex;
    const title = lessonTitle(group.lessonNumber!);
    const previousNumber =
      numberedIndex > 0 ? numberedGroups[numberedIndex - 1].lessonNumber : null;
    const isOpen = openLesson === group.lessonNumber;

    return {
      key: group.lessonNumber!,
      status: finished ? "done" : isNow ? "current" : "upcoming",
      fallbackLabel: group.lessonNumber,
      label: (
        <span className="ts-journey-label">
          <span className="ts-journey-title">{title.zh}</span>
          <span className="ts-lesson-sub">{`Dì ${group.lessonNumber} kè · ${title.en}`}</span>
        </span>
      ),
      badge: !unlocked ? (
        <span aria-label={`Locked — finish Lesson ${previousNumber} first`}>🔒</span>
      ) : (
        <span aria-hidden="true">
          {!finished ? `${done}/${total} ` : ""}
          {isOpen ? "▴" : "▾"}
        </span>
      ),
      onClick: unlocked
        ? () => setOpenLesson((current) => (current === group.lessonNumber ? null : group.lessonNumber!))
        : undefined,
      disabled: !unlocked,
      ariaExpanded: unlocked ? isOpen : undefined,
      expanded: isOpen ? (
        <div className="ts-lesson-expanded">
          <div className="ts-grid">
            {group.topics.map((t, i) => renderTopicCard(t, group, i))}
          </div>
        </div>
      ) : undefined,
    };
  });

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

      <div className="ts-lesson-journey">
        <JourneyPath stops={journeyStops} orientation="vertical" />
      </div>

      {otherGroup && (
        <div className="ts-other-block">
          <p className="ts-other-label">
            其他 Qítā · <BiLabel zh="" en="More practice" />
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
                <span className="ts-num-tile-n">✦</span>
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
                    pinyin="Hái méiyǒu kèhào de gùshi"
                    en="Stories without a lesson yet"
                  />
                </p>
              </div>
              <div className="ts-lesson-side">
                <span className="ts-side-chip ts-chip-open" aria-hidden="true">
                  {openLesson === "other" ? "▴" : "▾"}
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
