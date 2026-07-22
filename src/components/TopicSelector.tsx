import { useEffect, useState } from "react";
import { canUseDatabase, createCustomStory, listCustomStories } from "../services/database";
import { loadLocalStars } from "../utils/quizTiers";
import {
  type CustomTeacherStory,
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
  lessonCompletion,
  lessonTitle,
  topicStoryId,
  type LessonGroup,
} from "../utils/lessonGroups";
import {
  isStoryLevelUnlocked,
  loadSubmittedLevels,
  loadSubmittedStoryIds,
} from "../utils/storyLevelProgress";
import "./TopicSelector.css";
import { BiLabel, BiText } from "./BiLabel";
import "./BiLabel.css";

export interface VocabGroup {
  name: string;
  words: string[];
}

export interface Topic {
  id: string;
  name: string;
  description: string;
  skillFocus: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
  // Handy, easy-to-learn-and-reuse phrases for this scene (replaces the old
  // single whole-story "grammar pattern" note) — same word/translation shape
  // as vocabulary, aligned by index.
  phrases?: Record<number, string[]>;
  phrasesTranslation?: Record<number, string[]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  // AI-generated wrong-but-plausible translations per word (aligned by
  // index with vocabulary[scene]), used as the vocab quiz's multiple-choice
  // distractors instead of unrelated filler words. Optional — older stories
  // without generated distractors still get a quiz via the old fallback.
  vocabularyDistractors?: Record<number, string[][]>;
  // AI-generated fill-in-the-blank (cloze) candidates per word — each word's
  // entry is a list of {sentence, distractors} options, grown the same way
  // vocabularyDistractors is. Optional, same graceful fallback as above.
  vocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  // AI-generated synonym candidates per word — each word's entry is a list
  // of {synonym, distractors} options, grown the same way vocabularyCloze
  // is. Optional, same graceful fallback as above.
  vocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenScripts?: Record<number, string>;
  linear?: boolean;
  lessonNumber?: number | null;
  narrativeMode?: "story" | "describe" | "listen_retell";
  firstFrameIsExample?: boolean;
  // Which easy/medium/hard tier this Topic was built at, plus a reference to
  // the raw multi-tier story it came from — lets a level picker re-derive a
  // Topic at a different tier, and lets progress tracking know what to mark
  // as done on submit. Absent for topics that aren't teacher-authored.
  difficultyLevel?: StoryDifficultyLevel;
  sourceStory?: CustomTeacherStory;
}

interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic) => void;
}

export const TOPICS: Topic[] = [];

/** Only "story" mode topics belong in the normal training flow — "describe" and
 * "listen_retell" topics have their own dedicated pages. */
function isStoryModeTopic(topic: Topic): boolean {
  return (topic.narrativeMode ?? "story") === "story";
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

// Lesson number tiles rotate through the four tone colors, matching the
// palette's tone-per-color convention (T4 violet, T2 green, T1 blue, T3
// amber) so consecutive lessons never share a tile color.
const TILE_CLASSES = ["ts-tile-seal", "ts-tile-jade", "ts-tile-tone1", "ts-tile-gold"];

function tileClass(group: LessonGroup): string {
  if (group.lessonNumber === null) return "ts-tile-other";
  return TILE_CLASSES[(group.lessonNumber - 1) % TILE_CLASSES.length];
}

const LEVEL_ICONS: Record<StoryDifficultyLevel, string> = {
  easy: "🌱",
  medium: "🌿",
  hard: "🌳",
};

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const [topics, setTopics] = useState<Topic[]>(() =>
    loadPublishedTeacherTopics().filter(isStoryModeTopic),
  );
  const [loading, setLoading] = useState(canUseDatabase());
  // Which table-of-contents row is open: a lesson number, "other" for the
  // unassigned group, or null for the contents screen itself.
  const [openLesson, setOpenLesson] = useState<number | "other" | null>(null);

  useEffect(() => {
    if (!canUseDatabase()) return;
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
            .map((s) => storyToTopic(s as any))
            .filter(isStoryModeTopic);
          setTopics(published);
          return;
        }
        if (dbStories.length > 0) {
          saveCustomStories(dbStories);
        }
        const published = (dbStories.length > 0 ? dbStories : localStories)
          .filter((s) => s.published)
          .map((s) => storyToTopic(s as any))
          .filter(isStoryModeTopic);
        setTopics(published);
      })
      .catch((err) => console.error("Failed to load topics from backend:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="topic-selector">
        <div className="empty-state">
          <div className="empty-icon">⏳</div>
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
            <p className="platform-kicker"><BiLabel k="real_life_speaking_practice" /></p>
            <h1><BiLabel k="choose_a_daily_situation" /></h1>
            <p><BiText k="your_teacher_will_publish_speaking_activ" /></p>
          </div>
        </section>
        <div className="empty-state">
          <div className="empty-icon">📚</div>
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

  const openGroup =
    openLesson === null
      ? null
      : (groups.find((group) =>
          openLesson === "other"
            ? group.lessonNumber === null
            : group.lessonNumber === openLesson,
        ) ?? null);

  // The per-story 🌱🌿🌳 tier track: which difficulty levels this story
  // offers, and for each whether it's been submitted, is open, or still
  // locked behind the previous tier. Only teacher stories carry tiers.
  const renderTierTrack = (t: Topic) => {
    const story = t.sourceStory;
    if (!story) return null;
    const submittedLevels = loadSubmittedLevels(story.id);
    const levels = (["easy", "medium", "hard"] as const).filter(
      (level) => level === "easy" || storyHasTierContent(story, level),
    );
    return (
      <div className="ts-tier-track" aria-label="Difficulty levels">
        {levels.map((level) => {
          const state = submittedLevels[level]
            ? "done"
            : isStoryLevelUnlocked(story.id, level)
              ? "open"
              : "lock";
          return (
            <span key={level} className={`ts-tier-cell ts-tier-${state}`}>
              {LEVEL_ICONS[level]}
            </span>
          );
        })}
      </div>
    );
  };

  const renderTopicCard = (t: Topic) => {
    const totalScenes = t.images.length;
    const totalWords = Object.values(t.vocabulary).flat().length;
    const previewImage = t.images[0];

    return (
      <article key={t.id} className="ts-card">
        {/* Image strip */}
        <div className="ts-card-image">
          {previewImage ? (
            <img src={previewImage} alt={t.name} />
          ) : (
            <div className="ts-card-image-placeholder">🎬</div>
          )}
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
                aria-label={`${loadLocalStars(t.id)} of 3 quiz stars earned`}
              >
                {"⭐".repeat(loadLocalStars(t.id))}
                {"☆".repeat(3 - loadLocalStars(t.id))}
              </span>
            )}
          </div>

          {renderTierTrack(t)}
        </div>

        {/* Footer */}
        <div className="ts-card-footer">
          <button
            type="button"
            className="ts-card-btn"
            onClick={() => onTopicSelect?.(t)}
          >
            <BiLabel k="start_this_activity" />
            <span className="ts-card-btn-arrow">→</span>
          </button>
        </div>
      </article>
    );
  };

  // ── Screen 2: one lesson's stories ────────────────────────────────────
  if (openGroup) {
    const title =
      openGroup.lessonNumber !== null ? lessonTitle(openGroup.lessonNumber) : null;
    const { done, total } = lessonCompletion(openGroup, submittedIds);
    return (
      <div className="topic-selector">
        <button
          type="button"
          className="ts-crumb"
          onClick={() => setOpenLesson(null)}
        >
          ← <BiLabel zh="目錄" pinyin="Mùlù" en="Contents" />
        </button>

        <header className="ts-detail-head">
          <div className={`ts-num-tile ${tileClass(openGroup)}`}>
            {openGroup.lessonNumber !== null ? (
              <>
                <span className="ts-num-tile-label">LESSON</span>
                <span className="ts-num-tile-n">{openGroup.lessonNumber}</span>
              </>
            ) : (
              <span className="ts-num-tile-n">✦</span>
            )}
          </div>
          <div className="ts-detail-title">
            {title ? (
              <>
                <h2>{title.zh}</h2>
                <p className="ts-lesson-sub">
                  {`Dì ${openGroup.lessonNumber} kè · ${title.en}`}
                </p>
              </>
            ) : (
              <>
                <h2>其他練習</h2>
                <p className="ts-lesson-sub">Qítā liànxí · More practice — anytime</p>
              </>
            )}
          </div>
          <div className="ts-detail-progress">
            <div className="ts-story-dots">
              {openGroup.topics.map((t) => (
                <span
                  key={t.id}
                  className={`ts-story-dot ${
                    submittedIds.has(topicStoryId(t)) ? "is-done" : ""
                  }`}
                />
              ))}
            </div>
            <span className="ts-lesson-sub">
              {`${done}/${total} `}完成
            </span>
          </div>
        </header>

        <div className="ts-grid">{openGroup.topics.map(renderTopicCard)}</div>
      </div>
    );
  }

  // ── Screen 1: the table of contents ───────────────────────────────────
  const numberedGroups = groups.filter((group) => group.lessonNumber !== null);
  const otherGroup = groups.find((group) => group.lessonNumber === null) ?? null;

  return (
    <div className="topic-selector">
      <header className="ts-toc-head">
        <div>
          <p className="platform-kicker"><BiLabel k="real_life_speaking_practice" /></p>
          <h1 className="ts-toc-title">
            目錄 <span className="ts-lesson-sub">Mùlù · Contents</span>
          </h1>
        </div>
        <div className="ts-book-chip">
          <span className="ts-book-cover" aria-hidden="true">時代華語</span>
          <span className="ts-book-name">
            時代華語 第一冊
            <span className="ts-lesson-sub">Modern Chinese · Book 1</span>
          </span>
        </div>
      </header>

      <div className="ts-toc">
        {numberedGroups.map((group, numberedIndex) => {
          const index = groups.indexOf(group);
          const unlocked = isLessonGroupUnlocked(groups, index, submittedIds);
          const { done, total } = lessonCompletion(group, submittedIds);
          const finished = total > 0 && done === total;
          const isNow = index === nowIndex;
          const title = lessonTitle(group.lessonNumber!);
          const previousNumber =
            numberedIndex > 0 ? numberedGroups[numberedIndex - 1].lessonNumber : null;
          const state = finished ? "is-done" : isNow ? "is-now" : unlocked ? "is-open" : "is-locked";
          const isLast = numberedIndex === numberedGroups.length - 1;

          return (
            <div key={group.lessonNumber} className={`ts-lesson ${state}${isLast ? " ts-lesson-last" : ""}`}>
              <div
                className="ts-lesson-card"
                role={unlocked ? "button" : undefined}
                tabIndex={unlocked ? 0 : undefined}
                aria-disabled={!unlocked}
                onClick={unlocked ? () => setOpenLesson(group.lessonNumber!) : undefined}
                onKeyDown={
                  unlocked
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setOpenLesson(group.lessonNumber!);
                        }
                      }
                    : undefined
                }
              >
                <div className={`ts-num-tile ${unlocked ? tileClass(group) : "ts-tile-locked"}`}>
                  <span className="ts-num-tile-label">LESSON</span>
                  <span className="ts-num-tile-n">{group.lessonNumber}</span>
                </div>
                <div className="ts-lesson-main">
                  <div className="ts-lesson-title">{title.zh}</div>
                  <p className="ts-lesson-sub">{`Dì ${group.lessonNumber} kè · ${title.en}`}</p>
                </div>
                <div className="ts-lesson-side">
                  {unlocked && (
                    <div className="ts-story-dots">
                      {group.topics.map((t) => (
                        <span
                          key={t.id}
                          className={`ts-story-dot ${
                            submittedIds.has(topicStoryId(t)) ? "is-done" : ""
                          }`}
                        />
                      ))}
                    </div>
                  )}
                  {finished ? (
                    <span className="ts-side-chip ts-chip-done">
                      ✓ <BiLabel zh="完成" pinyin="wánchéng" en="done" />
                    </span>
                  ) : isNow ? (
                    <span className="ts-side-chip ts-chip-now">
                      ▶ <BiLabel zh="繼續" pinyin="jìxù" en="continue" />
                    </span>
                  ) : !unlocked ? (
                    <span className="ts-side-chip ts-chip-lock">
                      🔒{" "}
                      <BiLabel
                        zh={`先完成第 ${previousNumber} 課`}
                        pinyin={`xiān wánchéng dì ${previousNumber} kè`}
                        en={`finish Lesson ${previousNumber} first`}
                      />
                    </span>
                  ) : (
                    <span className="ts-side-chip ts-chip-open">
                      {done}/{total} 完成
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {otherGroup && (
        <div className="ts-other-block">
          <p className="ts-other-label">
            其他 Qítā · <BiLabel zh="" en="More practice" />
          </p>
          <div className="ts-lesson ts-lesson-last is-open">
            <div
              className="ts-lesson-card"
              role="button"
              tabIndex={0}
              onClick={() => setOpenLesson("other")}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setOpenLesson("other");
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
                <span className="ts-side-chip ts-chip-open">
                  <BiLabel zh="隨時可以練" pinyin="suíshí kěyǐ liàn" en="anytime" />
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
