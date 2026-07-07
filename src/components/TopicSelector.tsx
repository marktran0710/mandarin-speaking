import { useEffect, useState } from "react";
import { canUseDatabase, createCustomStory, listCustomStories } from "../services/database";
import { loadCustomStories, loadPublishedTeacherTopics, saveCustomStories, storyToTopic } from "../utils/teacherStories";
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
  level: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
  grammarPatterns?: Record<number, string>;
  grammarExamples?: Record<number, string>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenScripts?: Record<number, string>;
  linear?: boolean;
  lessonNumber?: number | null;
  narrativeMode?: "story" | "describe" | "listen_retell";
  firstFrameIsExample?: boolean;
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

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const [topics, setTopics] = useState<Topic[]>(() =>
    loadPublishedTeacherTopics().filter(isStoryModeTopic),
  );
  const [loading, setLoading] = useState(canUseDatabase());

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

  return (
    <div className="topic-selector">
      {/* ── Hero ── */}
      <section className="ts-hero">
        <div className="ts-hero-copy">
          <p className="platform-kicker"><BiLabel k="real_life_speaking_practice" /></p>
          <h1><BiLabel k="choose_a_daily_situation" /></h1>
          <p><BiText k="select_a_real_situation_students_may_mee" /></p>
        </div>
        <div className="ts-steps" aria-label="Learning steps">
          <div className="ts-step">
            <span className="ts-step-num ts-step-1">1</span>
            <span><BiLabel k="plan_the_story" /></span>
          </div>
          <div className="ts-step">
            <span className="ts-step-num ts-step-2">2</span>
            <span><BiLabel k="record_mandarin_speech" /></span>
          </div>
          <div className="ts-step">
            <span className="ts-step-num ts-step-3">3</span>
            <span><BiLabel k="review_pronunciation_and_language_feedba" /></span>
          </div>
        </div>
      </section>

      {/* ── Topic card grid ── */}
      <section className="ts-grid-section">
        <div className="ts-grid-header">
          <p className="platform-kicker"><BiLabel k="activity_menu" /></p>
          <h2><BiLabel k="teacher_published_topics" /></h2>
          <span className="ts-topic-count">
            <BiLabel
              zh={`${topics.length} 個活動`}
              en={`${topics.length} activit${topics.length === 1 ? "y" : "ies"}`}
            />
          </span>
        </div>

        <div className="ts-grid">
          {topics.map((t) => {
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
                      <BiLabel zh={`${totalScenes} 場景`} en={`${totalScenes} scenes`} />
                    </span>
                  )}
                  {t.lessonNumber != null && (
                    <span className="ts-card-lesson-badge">L{t.lessonNumber}</span>
                  )}
                </div>

                {/* Body */}
                <div className="ts-card-body">
                  <div className="ts-card-meta-row">
                    <span className="ts-card-level">{t.level}</span>
                    <span className="ts-card-skill">
                      <SkillFocusLabel skillFocus={t.skillFocus} />
                    </span>
                  </div>

                  <h3 className="ts-card-title">{t.name}</h3>

                  {t.description && (
                    <p className="ts-card-desc">{t.description}</p>
                  )}

                  <div className="ts-card-stats">
                    <span>🎬 <BiLabel zh={`${totalScenes} 場景`} en={`${totalScenes} scenes`} /></span>
                    {totalWords > 0 && (
                      <span>📝 <BiLabel zh={`${totalWords} 詞`} en={`${totalWords} words`} /></span>
                    )}
                  </div>
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
          })}
        </div>
      </section>
    </div>
  );
}
