import { useMemo } from "react";
import type { Topic } from "../../components/content/topic-selector/types";
import { speakingVocabularyItems } from "../../utils/speakingVocabulary";
import { topicStoryId } from "../../utils/lessonGroups";
import { markPhaseSeen } from "../studyProgressFlags";
import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentButton from "../primitives/StudentButton";
import StudentAudioControl from "../primitives/StudentAudioControl";
import BilingualWord from "../primitives/BilingualWord";
import "../primitives/layout.css";
import "./VocabularyPreviewPage.css";

interface VocabularyPreviewPageProps {
  topic: Topic;
  lessonLabel: string;
  onStartSpeaking: () => void;
}

export default function VocabularyPreviewPage({ topic, lessonLabel, onStartSpeaking }: VocabularyPreviewPageProps) {
  const items = useMemo(() => speakingVocabularyItems(topic), [topic]);

  const handleStartSpeaking = () => {
    markPhaseSeen(topicStoryId(topic), "vocab");
    onStartSpeaking();
  };

  return (
    <div className="sa-page-container">
      <StudentPageHeader
        eyebrowEn={`Study · ${lessonLabel} · Vocabulary Preview`}
        titleZh="生詞預習"
        titleEn={`${items.length} words`}
      />

      <div className="sa-vocab-preview__grid">
        {items.map((item) => (
          <StudentSection key={item.wordId} variant="panel" className="sa-vocab-preview__card">
            <BilingualWord hanzi={item.word} pinyin={item.pinyin} gloss={item.meaning} size="inline" />
            <StudentAudioControl
              audioUrl={item.audioUrl}
              fallbackText={item.word}
              label="Listen"
              compact
            />
          </StudentSection>
        ))}
      </div>

      <div className="sa-vocab-preview__footer">
        <StudentButton variant="primary" size="lg" iconTrailing="arrow_forward" onClick={handleStartSpeaking}>
          Start Speaking
        </StudentButton>
      </div>
    </div>
  );
}
