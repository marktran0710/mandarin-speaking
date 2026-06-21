import { useEffect, useState } from "react";
import { canUseDatabase, createCustomStory, listCustomStories } from "./database";
import { loadCustomStories, loadPublishedTeacherTopics, saveCustomStories, storyToTopic } from "./utils/teacherStories";
import "./TopicSelector.css";
import { BiLabel, BiText } from "./components/BiLabel";
import "./components/BiLabel.css";

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
}

interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic) => void;
}

export const TOPICS: Topic[] = [];

export function SkillFocusLabel({ skillFocus }: { skillFocus: string }) {
  if (skillFocus === "Teacher published activity") {
    return <BiLabel zh="老師發布的活動" en="Teacher published activity" />;
  }
  return <>{skillFocus}</>;
}

export function getTopicVocabulary(topic: Topic, imageIndex: number): string[] {
  return topic.vocabulary[imageIndex] || [];
}

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const [topics, setTopics] = useState<Topic[]>(() => loadPublishedTeacherTopics());
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(() => {
    const initial = loadPublishedTeacherTopics();
    return initial[0] ?? null;
  });
  const [loading, setLoading] = useState(canUseDatabase());

  useEffect(() => {
    if (!canUseDatabase()) return;
    listCustomStories()
      .then(async (dbStories) => {
        // Merge: push any localStorage-only stories up to the DB so they're never lost
        const localStories = loadCustomStories();
        const dbIds = new Set(dbStories.map((s) => s.id));
        const localOnly = localStories.filter((s) => !dbIds.has(s.id));
        if (localOnly.length > 0) {
          await Promise.allSettled(localOnly.map((s) => createCustomStory(s)));
          // Re-fetch after uploading missing stories
          const merged = await listCustomStories();
          saveCustomStories(merged);
          const published = merged
            .filter((s) => s.published)
            .map((s) => storyToTopic(s as any));
          setTopics(published);
          setSelectedTopic((prev) => {
            if (prev) return published.find((t) => t.id === prev.id) ?? published[0] ?? null;
            return published[0] ?? null;
          });
          return;
        }
        // DB is source of truth — only overwrite localStorage if DB has stories
        if (dbStories.length > 0) {
          saveCustomStories(dbStories);
        }
        const published = (dbStories.length > 0 ? dbStories : localStories)
          .filter((s) => s.published)
          .map((s) => storyToTopic(s as any));
        setTopics(published);
        setSelectedTopic((prev) => {
          if (prev) return published.find((t) => t.id === prev.id) ?? published[0] ?? null;
          return published[0] ?? null;
        });
      })
      .catch((err) => console.error("Failed to load topics from backend:", err))
      .finally(() => setLoading(false));
  }, []);

  const chooseTopic = (topic: Topic) => {
    setSelectedTopic(topic);
  };

  if (loading) {
    return (
      <div className="topic-selector">
        <div className="empty-state">
          <div className="empty-icon">⏳</div>
          <h2><BiLabel zh="正在載入活動…" en="Loading activities…" /></h2>
        </div>
      </div>
    );
  }

  if (topics.length === 0) {
    return (
      <div className="topic-selector">
        <section className="learning-hero">
          <div className="learning-hero-copy">
            <p className="platform-kicker"><BiLabel zh="真實生活口語練習" en="Real-life speaking practice" /></p>
            <h1><BiLabel zh="選擇一個日常情境" en="Choose a Daily Situation" /></h1>
            <p>
              <BiText zh="你的老師會在這裡發布口語練習活動。請稍後再回來查看！" en="Your teacher will publish speaking activities here. Check back once materials are ready!" />
            </p>
          </div>
        </section>

        <div className="empty-state">
          <div className="empty-icon">📚</div>
          <h2><BiLabel zh="目前還沒有活動" en="No Activities Yet" /></h2>
          <p>
            <BiText zh="你的老師將會建立並發布口語練習活動，準備好後會顯示在這裡。" en="Your teacher will create and publish speaking activities. They'll appear here when ready." />
          </p>
        </div>
      </div>
    );
  }

  const topic = selectedTopic ?? topics[0];
  const totalScenes = topic.images.length;
  const totalWords = Object.values(topic.vocabulary).flat().length;

  return (
    <div className="topic-selector">
      <section className="learning-hero">
        <div className="learning-hero-copy">
          <p className="platform-kicker"><BiLabel zh="真實生活口語練習" en="Real-life speaking practice" /></p>
          <h1><BiLabel zh="選擇一個日常情境" en="Choose a Daily Situation" /></h1>
          <p>
            <BiText
              zh="選擇學生日常生活中可能遇到的真實情境，研究六張相連的圖片提示，準備實用的普通話片語，並為每個提示錄音，獲得 Praat 韻律分析與 Gemini 語言回饋。"
              en="Select a real situation students may meet in daily life, study the six connected picture cues, prepare useful Mandarin phrases, and record each cue for Praat prosody and Gemini language feedback."
            />
          </p>
        </div>

        <div className="learning-objectives" aria-label="Learning objectives">
          <div>
            <strong>1</strong>
            <span><BiLabel zh="規劃故事" en="Plan the story" /></span>
          </div>
          <div>
            <strong>2</strong>
            <span><BiLabel zh="錄製普通話語音" en="Record Mandarin speech" /></span>
          </div>
          <div>
            <strong>3</strong>
            <span><BiLabel zh="檢視發音與語言回饋" en="Review pronunciation and language feedback" /></span>
          </div>
        </div>
      </section>

      <section className="activity-layout">
        <aside className="activity-sidebar" aria-label="Story topics">
          <div className="sidebar-heading">
            <p className="platform-kicker"><BiLabel zh="活動選單" en="Activity menu" /></p>
            <h2><BiLabel zh="老師發布的主題" en="Teacher published topics" /></h2>
          </div>

          <div className="topic-list">
            {topics.map((t) => (
              <button
                type="button"
                key={t.id}
                className={`topic-row ${topic.id === t.id ? "selected" : ""}`}
                onClick={() => chooseTopic(t)}
              >
                <span>
                  <strong>{t.name}</strong>
                  <small><SkillFocusLabel skillFocus={t.skillFocus} /></small>
                </span>
                <em>{t.level}</em>
              </button>
            ))}
          </div>
        </aside>

        <section className="activity-preview" aria-label="Selected activity">
          <p className="platform-kicker"><BiLabel zh="已選模組" en="Selected module" /></p>

          <div className="topic-summary-card">
            <div className="topic-summary-top">
              <div>
                <h2 className="topic-summary-title">{topic.name}</h2>
                <span className="module-badge">{topic.level}</span>
              </div>
            </div>

            <p className="topic-summary-desc">{topic.description}</p>

            <div className="topic-summary-meta">
              <div className="topic-meta-item">
                <span className="topic-meta-icon">🎬</span>
                <span><BiLabel zh={`${totalScenes} 個場景`} en={`${totalScenes} scenes`} /></span>
              </div>
              <div className="topic-meta-item">
                <span className="topic-meta-icon">📝</span>
                <span><BiLabel zh={`${totalWords} 個詞彙`} en={`${totalWords} vocabulary words`} /></span>
              </div>
              <div className="topic-meta-item">
                <span className="topic-meta-icon">🎯</span>
                <span><SkillFocusLabel skillFocus={topic.skillFocus} /></span>
              </div>
            </div>

            <button
              type="button"
              className="start-activity-btn"
              onClick={() => onTopicSelect?.(topic)}
            >
              <BiLabel zh="開始這個活動 →" en="Start this activity" />
            </button>
          </div>
        </section>
      </section>
    </div>
  );
}
