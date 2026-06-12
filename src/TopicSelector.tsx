import { useState } from "react";
import { loadPublishedTeacherTopics } from "./utils/teacherStories";
import "./TopicSelector.css";

export interface Topic {
  id: string;
  name: string;
  description: string;
  skillFocus: string;
  level: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
}

interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic) => void;
}

export const TOPICS: Topic[] = [];

export function getTopicVocabulary(topic: Topic, imageIndex: number): string[] {
  return topic.vocabulary[imageIndex] || [];
}

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const topics = loadPublishedTeacherTopics();

  if (topics.length === 0) {
    return (
      <div className="topic-selector">
        <section className="learning-hero">
          <div className="learning-hero-copy">
            <p className="platform-kicker">Real-life speaking practice</p>
            <h1>Choose a Daily Situation</h1>
            <p>
              Your teacher will publish speaking activities here. Check back once
              materials are ready!
            </p>
          </div>
        </section>

        <div className="empty-state">
          <div className="empty-icon">📚</div>
          <h2>No Activities Yet</h2>
          <p>
            Your teacher will create and publish speaking activities. They'll
            appear here when ready.
          </p>
        </div>
      </div>
    );
  }

  const [selectedTopic, setSelectedTopic] = useState<Topic>(topics[0]);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);

  const selectedImage = selectedTopic.images[selectedImageIndex];
  const selectedWords = getTopicVocabulary(selectedTopic, selectedImageIndex);

  const chooseTopic = (topic: Topic) => {
    setSelectedTopic(topic);
    setSelectedImageIndex(0);
  };

  return (
    <div className="topic-selector">
      <section className="learning-hero">
        <div className="learning-hero-copy">
          <p className="platform-kicker">Real-life speaking practice</p>
          <h1>Choose a Daily Situation</h1>
          <p>
            Select a real situation students may meet in daily life, study the
            six connected picture cues, prepare useful Mandarin phrases, and
            record each cue for Praat prosody and Gemini language feedback.
          </p>
        </div>

        <div className="learning-objectives" aria-label="Learning objectives">
          <div>
            <strong>1</strong>
            <span>Plan the story</span>
          </div>
          <div>
            <strong>2</strong>
            <span>Record Mandarin speech</span>
          </div>
          <div>
            <strong>3</strong>
            <span>Review pronunciation and language feedback</span>
          </div>
        </div>
      </section>

      <section className="activity-layout">
        <aside className="activity-sidebar" aria-label="Story topics">
          <div className="sidebar-heading">
            <p className="platform-kicker">Activity menu</p>
            <h2>Teacher published topics</h2>
          </div>

          <div className="topic-list">
            {topics.map((topic) => (
              <button
                type="button"
                key={topic.id}
                className={`topic-row ${
                  selectedTopic.id === topic.id ? "selected" : ""
                }`}
                onClick={() => chooseTopic(topic)}
              >
                <span>
                  <strong>{topic.name}</strong>
                  <small>{topic.skillFocus}</small>
                </span>
                <em>{topic.level}</em>
              </button>
            ))}
          </div>
        </aside>

        <section className="activity-preview" aria-label="Selected activity">
          <div className="preview-header">
            <div>
              <p className="platform-kicker">Selected module</p>
              <h2>{selectedTopic.name}</h2>
              <p>{selectedTopic.description}</p>
            </div>
            <div className="module-badge">{selectedTopic.level}</div>
          </div>

          <div className="preview-grid">
            <div className="main-prompt-card">
              <img
                src={selectedImage}
                alt={`${selectedTopic.name} story part ${
                  selectedImageIndex + 1
                }`}
              />
              <div className="prompt-number">
                Story part {selectedImageIndex + 1} of{" "}
                {selectedTopic.images.length}
              </div>
            </div>

            <div className="prompt-planning-panel">
              <div className="planning-block">
                <h3>Speaking goals</h3>
                <ul>
                  <li>Describe the real situation clearly.</li>
                  <li>Use useful phrases for daily communication.</li>
                  <li>Revise each cue after feedback.</li>
                </ul>
              </div>

              <div className="planning-block">
                <h3>Vocabulary support</h3>
                <div className="vocabulary-chips">
                  {selectedWords.map((word) => (
                    <span key={word}>{word}</span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                className="start-activity-btn"
                onClick={() => onTopicSelect?.(selectedTopic)}
              >
                Start recording this activity
              </button>
            </div>
          </div>

          <div className="prompt-strip" aria-label="Story sequence prompts">
            {selectedTopic.images.map((image, index) => (
              <button
                type="button"
                key={image}
                className={`prompt-thumb ${
                  selectedImageIndex === index ? "active" : ""
                }`}
                onClick={() => setSelectedImageIndex(index)}
              >
                <img src={image} alt={`Story part ${index + 1}`} />
                <span>Part {index + 1}</span>
              </button>
            ))}
          </div>
        </section>
      </section>
    </div>
  );
}
