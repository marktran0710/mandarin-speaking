import { useEffect, useState } from "react";
import {
  canUseDatabase,
  createCustomStory,
  getVocabQuizReviewQueue,
  listCustomStories,
  listStorySubmissions,
} from "../../services/database";
import { getCachedResearchContext } from "../../utils/researchContext";
import { getResearchProbesDue, getResearchReviewSession } from "../../services/api/vocabulary-research";
import LearningCheck from "./LearningCheck";
import { loadLocalStars } from "../../utils/quizTiers";
import {
  loadCustomStories,
  loadPublishedTeacherTopics,
  saveCustomStories,
  storyToTopic,
} from "../../utils/teacherStories";
import {
  groupTopicsByLesson,
  isLessonGroupUnlocked,
  isStoryFinished,
  isStoryUnlockedInLesson,
  lessonCompletion,
  lessonTitle,
  type LessonGroup,
} from "../../utils/lessonGroups";
import {
  loadSubmittedStoryIds,
  mergeSubmittedStoryLevels,
} from "../../utils/storyLevelProgress";
import { getStudentId, getStudentName } from "../../utils/studentSession";
import "./TopicSelector.css";
import { BiLabel, BiText } from "../ui/BiLabel";
import StudentIcon from "../navigation/StudentIcon";
import StudentPageHeader from "../navigation/StudentPageHeader";
import {
  StudentSection,
  StudentSectionBody,
  StudentSectionHeader,
} from "../student-workspace/student-layout";
import { StudentGrid, StudentStack } from "../student-workspace/student-layout";
import "../ui/BiLabel.css";
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

export default function TopicSelector({ onTopicSelect, publishedTopics }: TopicSelectorProps) {
  const [topics, setTopics] = useState<Topic[]>(() =>
    (publishedTopics ?? loadPublishedTeacherTopics()).filter(isStoryModeTopic),
  );
  const [loading, setLoading] = useState(publishedTopics === undefined && canUseDatabase());
  // Backend submission hydration updates localStorage, which is the source
  // used by the lesson progress calculations below. Bump a local revision so
  // those calculations rerun when the async merge completes.
  const [, bumpProgressRevision] = useState(0);
  // Which table-of-contents row is open: a lesson number, "other" for the
  // unassigned group, or null for the contents screen itself.
  const [openLesson, setOpenLesson] = useState<number | "other" | null>(null);

  useEffect(() => {
    let cancelled = false;
    const studentId = getStudentId();
    const studentName = getStudentName();
    const hydrateSubmittedLevels = async () => {
      if (!canUseDatabase()) return;
      const serverSubmissions = await listStorySubmissions(undefined, { studentId, studentName }).catch(() => null);
      if (!cancelled && serverSubmissions) {
        if (mergeSubmittedStoryLevels(serverSubmissions, { studentId, studentName })) {
          bumpProgressRevision((revision) => revision + 1);
        }
      }
    };

    if (publishedTopics !== undefined) {
      setTopics(publishedTopics.filter(isStoryModeTopic));
      setLoading(false);
      void hydrateSubmittedLevels();
      return () => {
        cancelled = true;
      };
    }
    if (!canUseDatabase()) return;
    const submissions = listStorySubmissions(undefined, { studentId, studentName }).catch(() => null);

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
          const serverSubmissions = await submissions;
          if (!cancelled && serverSubmissions && mergeSubmittedStoryLevels(serverSubmissions, { studentId, studentName })) {
            bumpProgressRevision((revision) => revision + 1);
          }
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
        const serverSubmissions = await submissions;
        if (!cancelled && serverSubmissions && mergeSubmittedStoryLevels(serverSubmissions, { studentId, studentName })) {
          bumpProgressRevision((revision) => revision + 1);
        }
        if (cancelled) return;
        setTopics(published);
      })
      .catch((err) => console.error("Failed to load topics from backend:", err))
      .finally(() => setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [publishedTopics]);

  // "You are here" — hoisted above the loading/empty early returns below
  // (a hook needs a stable call order every render) so the pending-review
  // fetch and the dashboard's continue card can share one computation.
  const groups = groupTopicsByLesson(topics);
  const submittedIds = loadSubmittedStoryIds();
  const nowIndex = groups.findIndex(
    (group, index) =>
      group.lessonNumber !== null &&
      isLessonGroupUnlocked(groups, index, submittedIds) &&
      lessonCompletion(group, submittedIds).done < group.topics.length,
  );
  const numberedGroups = groups.filter((group) => group.lessonNumber !== null);
  const otherGroup = groups.find((group) => group.lessonNumber === null) ?? null;
  const continueGroup =
    groups[nowIndex] ?? numberedGroups[0] ?? otherGroup ?? null;
  const continueTopic =
    continueGroup?.topics.find((topic) => !isStoryFinished(topic, submittedIds)) ??
    continueGroup?.topics[0] ??
    null;
  const isContinueFallback = nowIndex < 0;

  // A gentle, non-blocking nudge: how many weak/due words are waiting for
  // the lesson the student would resume next. Best-effort — a slow or
  // failed fetch just means no badge, never a blocked continue button.
  const [pendingReviewCount, setPendingReviewCount] = useState(0);
  useEffect(() => {
    const studentId = getStudentId();
    if (!continueTopic || !studentId || !canUseDatabase()) {
      setPendingReviewCount(0);
      return;
    }
    let cancelled = false;
    // Epic 5, Task 5.8: an active research participant's dashboard hint
    // comes from the separate research retention queue, never production's
    // combined weak+due queue.
    if (getCachedResearchContext().active) {
      getResearchReviewSession()
        .then((session) => { if (!cancelled) setPendingReviewCount(session.wordIds.length); })
        .catch(() => { if (!cancelled) setPendingReviewCount(0); });
      return () => { cancelled = true; };
    }
    getVocabQuizReviewQueue(continueTopic.id, studentId, { includeAllWeak: true })
      .then((result) => { if (!cancelled) setPendingReviewCount(result.queue?.length ?? 0); })
      .catch(() => { if (!cancelled) setPendingReviewCount(0); });
    return () => { cancelled = true; };
  }, [continueTopic?.id]);

  // Epic 7, Task 7.8: a low-prominence "Learning Check" hint - never blocks
  // the continue button, and only ever appears for an active research
  // participant with something actually due right now.
  const [pendingProbeCount, setPendingProbeCount] = useState(0);
  const [showLearningCheck, setShowLearningCheck] = useState(false);
  useEffect(() => {
    if (!getCachedResearchContext().active) { setPendingProbeCount(0); return; }
    let cancelled = false;
    getResearchProbesDue()
      .then((session) => { if (!cancelled) setPendingProbeCount(session.questions.length); })
      .catch(() => { if (!cancelled) setPendingProbeCount(0); });
    return () => { cancelled = true; };
  }, [continueTopic?.id]);

  if (showLearningCheck) {
    return (
      <LearningCheck
        onDone={() => {
          setShowLearningCheck(false);
          setPendingProbeCount(0);
        }}
      />
    );
  }

  const pageHeader = (
    <StudentPageHeader
      eyebrow={{ zh: "課程", pinyin: "Kèchéng", en: "Lessons" }}
      title={{ zh: `歡迎回來，${getStudentName()}`, en: "Continue learning" }}
      lede={{ zh: "從上次停下的地方繼續", en: "Pick up right where you left off" }}
    />
  );

  if (loading) {
    return (
      <StudentStack className="topic-selector">
        {pageHeader}
        <StudentSection className="empty-state" variant="soft" aria-labelledby="ts-loading-title">
          <div className="empty-icon"><StudentIcon name="spark" size={28} /></div>
          <StudentSectionHeader headingId="ts-loading-title" title={<BiLabel k="loading_activities" />} />
        </StudentSection>
      </StudentStack>
    );
  }

  if (topics.length === 0) {
    return (
      <StudentStack className="topic-selector">
        {pageHeader}
        <StudentSection className="empty-state" variant="soft" aria-labelledby="ts-empty-title">
          <div className="empty-icon"><StudentIcon name="stories" size={28} /></div>
          <StudentSectionHeader
            headingId="ts-empty-title"
            title={<BiLabel k="no_activities_yet" align="center" />}
          />
          <p><BiText k="your_teacher_will_create_and_publish_spe" /></p>
        </StudentSection>
      </StudentStack>
    );
  }

  const renderTopicCard = (t: Topic, group: LessonGroup, index: number) => {
    const totalScenes = t.images.length;
    const totalWords = Object.values(t.vocabulary).flat().length;
    const earnedStars = loadLocalStars(t.id);
    const previewImage = t.images[0];
    const unlocked = isStoryUnlockedInLesson(group, index, submittedIds);
    const subLabel =
      group.lessonNumber != null && t.lessonSubOrder != null
        ? `${group.lessonNumber}-${t.lessonSubOrder}`
        : null;
    // A story now opens only once its predecessor is fully finished — all
    // three quiz rounds passed (⭐⭐⭐) AND speaking submitted. Surface that
    // predecessor on the locked card so the lock never reads as a dead button.
    const previousTopic = !unlocked ? group.topics[index - 1] : undefined;

    return (
      <article key={t.id} className={`ts-card${unlocked ? "" : " ts-card-locked"}`}>
        {/* Image strip */}
        <div className="ts-card-image">
          {previewImage ? (
            <img src={previewImage} alt={t.name} width={800} height={450} />
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
          <h3 className="ts-card-title">{t.name}</h3>

          <div className="ts-card-stats">
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
                aria-label={`${earnedStars} of 3 quiz stars earned`}
              >
                {Array.from({ length: 3 }, (_, starIndex) => (
                  <StudentIcon
                    key={starIndex}
                    name="star"
                    size={14}
                    className={starIndex < earnedStars ? "is-earned" : "is-empty"}
                  />
                ))}
              </span>
            )}
          </div>

          {onTopicSelect && unlocked && (
            <button
              type="button"
              className="ts-card-open"
              onClick={() => onTopicSelect(t)}
            >
              <BiLabel
                zh="選擇活動"
                en="Choose an activity"
              />
              <StudentIcon name="arrow-right" size={17} aria-hidden="true" />
            </button>
          )}

          {onTopicSelect && !unlocked && (
            <p className="ts-card-locked-note">
              <StudentIcon name="lock" size={14} />
              <BiLabel
                zh={previousTopic ? `先完成 ${previousTopic.name}（三關 + 口說）` : "先完成上一個故事"}
                en={previousTopic ? `Finish "${previousTopic.name}" first (3 rounds + speaking)` : "Finish the previous story first"}
                align="left"
              />
            </p>
          )}
        </div>
      </article>
    );
  };

  // Keep the lesson dashboard focused on the next activity and course index;
  // progress metrics belong to My learning and the persistent rail.
  const renderDashboard = () => {
    if (!continueTopic || !continueGroup) return null;

    const lessonNumber = continueGroup.lessonNumber;
    const openContinueTopic = () => {
      if (lessonNumber !== null) setOpenLesson(lessonNumber);
      onTopicSelect?.(continueTopic);
    };

    return (
      <>
        <StudentSection className="ts-dashboard ts-dash-continue" variant="soft" aria-labelledby="ts-continue-title">
          <StudentSectionHeader
            headingId="ts-continue-title"
            title={<BiLabel zh="繼續故事" en="Continue story" align="left" />}
          />
          <StudentSectionBody layout="split" className="ts-dash-continue-card">
          <div className="ts-dash-continue-copy">
            <span className="ts-dash-kicker">
              <BiLabel
                zh={isContinueFallback ? "從第一課開始" : `第${lessonNumber}課 · 進行中`}
                en={isContinueFallback ? "Start here" : `Lesson ${lessonNumber} · In progress`}
              />
            </span>
            <h2>{continueTopic.name}</h2>
            <p>{continueTopic.description || "繼續你的故事練習"}</p>
            {pendingReviewCount > 0 && (
              // A quiet heads-up, not a gate: rides along the existing
              // continue button rather than adding a second click target or
              // blocking the story itself.
              <p className="ts-dash-review-hint" role="status" aria-label={`${pendingReviewCount} words to review`}>
                <StudentIcon name="retry" size={14} aria-hidden="true" />
                <BiLabel
                  zh={`還有 ${pendingReviewCount} 個生詞待複習`}
                  pinyin="Hái yǒu shēngcí dài fùxí"
                  en={`${pendingReviewCount} word${pendingReviewCount === 1 ? "" : "s"} to review`}
                  align="left"
                />
              </p>
            )}
            {pendingProbeCount > 0 && (
              // Same "quiet heads-up" treatment as the review hint above -
              // its own button so starting it is a deliberate second click,
              // never something that hijacks "Continue story".
              <p className="ts-dash-review-hint" role="status" aria-label="Learning check available">
                <StudentIcon name="spark" size={14} aria-hidden="true" />
                <BiLabel zh="小測驗" pinyin="Xiǎo cèyàn" en="Learning Check" align="left" />
                <button type="button" className="ts-dash-probe-start" onClick={() => setShowLearningCheck(true)}>
                  <BiLabel zh="開始" en="Start" />
                </button>
              </p>
            )}
            <button type="button" className="ts-dash-continue-action" onClick={openContinueTopic}>
              <BiLabel zh="繼續學習" en="Continue story" />
              <StudentIcon name="arrow-right" size={17} aria-hidden="true" />
            </button>
          </div>
          <div className="ts-dash-continue-art" aria-hidden="true">
            {continueTopic.images[0] ? (
              <img src={continueTopic.images[0]} alt="" width={800} height={450} />
            ) : (
              <span className="ts-dash-continue-art-placeholder">
                <StudentIcon name="image" size={28} />
              </span>
            )}
          </div>
          </StudentSectionBody>
        </StudentSection>

        <StudentSection className="ts-dash-explainer" variant="plain" aria-labelledby="ts-dash-steps-title">
          <StudentSectionHeader
            headingId="ts-dash-steps-title"
            title={<BiLabel zh="三步開始" en="Three steps" align="left" />}
          />
          <StudentGrid columns={3} className="ts-dash-step-grid">
            <article className="ts-dash-step-card">
              <span className="ts-dash-icon-chip ts-dash-icon-chip-seal" aria-hidden="true">
                <StudentIcon name="image" size={22} />
              </span>
              <h3><BiLabel zh="看圖片" en="Look" align="left" /></h3>
              <p><BiText zh="先觀察畫面，找到故事線索。" en="Notice the scene and find the story clues." /></p>
            </article>
            <article className="ts-dash-step-card">
              <span className="ts-dash-icon-chip ts-dash-icon-chip-jade" aria-hidden="true">
                <StudentIcon name="microphone" size={22} />
              </span>
              <h3><BiLabel zh="說故事" en="Speak" align="left" /></h3>
              <p><BiText zh="用自己的話說出你看到的內容。" en="Tell what you see in your own words." /></p>
            </article>
            <article className="ts-dash-step-card">
              <span className="ts-dash-icon-chip ts-dash-icon-chip-tone1" aria-hidden="true">
                <StudentIcon name="idea" size={22} />
              </span>
              <h3><BiLabel zh="看回饋" en="Improve" align="left" /></h3>
              <p><BiText zh="看看回饋，知道下一步怎麼進步。" en="Use your feedback to choose the next step." /></p>
            </article>
          </StudentGrid>
        </StudentSection>
      </>
    );
  };

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
            {cover ? <img src={cover} alt="" width={800} height={450} /> : <span className="ts-lesson-cover-fallback" aria-hidden="true">{group.lessonNumber}</span>}
          </span>

          <span className="ts-lesson-body">
            <span className="ts-lesson-kicker-row">
              <span className="ts-lesson-kicker">
                {`第 ${group.lessonNumber} 課`}
              </span>
              {isNow && <span className="ts-lesson-now-tag">現在 NOW</span>}
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
            <StudentGrid columns={3} className="ts-grid">
              {group.topics.map((t, i) => renderTopicCard(t, group, i))}
            </StudentGrid>
          </div>
        )}
      </div>
    );
  };

  return (
    <StudentStack className="topic-selector">
      {pageHeader}
      {renderDashboard()}
      <StudentSection className="ts-catalogue" variant="plain" aria-labelledby="ts-catalogue-title">
        <StudentSectionHeader
          headingId="ts-catalogue-title"
          title={<BiLabel zh="目錄" pinyin="Mùlù" en="Contents" align="left" />}
          action={(
            <div className="ts-book-chip">
              <img className="ts-book-cover" src="/textbook-cover.jpg" alt="" aria-hidden="true" width={192} height={264} />
              <span className="ts-book-name">
                時代華語 第一冊
                <span className="ts-lesson-sub">Modern Chinese · Book 1</span>
              </span>
                </div>
          )}
        />
        <StudentSectionBody className="ts-catalogue-body">
          <div className="ts-lesson-list">
            {numberedGroups.map((group, numberedIndex) => renderLessonRow(group, numberedIndex))}
          </div>

          {otherGroup && (
            <section className="ts-other-block" aria-labelledby="ts-more-practice-title">
              <h3 id="ts-more-practice-title" className="ts-other-label">
            <BiLabel zh="其他" en="More practice" />
              </h3>
              <div className="ts-lesson">
            <button
              type="button"
              className="ts-lesson-card"
              aria-expanded={openLesson === "other"}
              onClick={() => setOpenLesson((current) => (current === "other" ? null : "other"))}
            >
              <span className="ts-num-tile ts-tile-other">
                <StudentIcon name="spark" size={24} />
              </span>
              <span className="ts-lesson-main">
                <span className="ts-lesson-title">
                  {otherGroup.topics.length === 1
                    ? otherGroup.topics[0].name
                    : `${otherGroup.topics.length} 個故事`}
                </span>
                <span className="ts-lesson-sub">
                  <BiLabel
                    zh="還沒有課號的故事"
                    en="Stories without a lesson yet"
                    align="left"
                  />
                </span>
              </span>
              <span className="ts-lesson-side">
                <span className="ts-side-chip ts-chip-open" aria-hidden="true">
                  <StudentIcon name={openLesson === "other" ? "chevron-up" : "chevron-down"} size={16} />
                </span>
              </span>
            </button>
            </div>
              {openLesson === "other" && (
                <div className="ts-lesson-expanded">
                  <StudentGrid columns={3} className="ts-grid">
                    {otherGroup.topics.map((t, i) => renderTopicCard(t, otherGroup, i))}
                  </StudentGrid>
                </div>
              )}
            </section>
          )}
        </StudentSectionBody>
      </StudentSection>
    </StudentStack>
  );
}
