import { useMemo } from "react";
import type { Topic } from "@entities/topic";
import { speakingVocabularyItems } from "@entities/vocabulary";
import { topicStoryId } from "../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import BilingualWord from "@shared/ui/student/BilingualWord";
import "@shared/ui/student/layout.css";
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
    <div className="sa-page-container sa-page-container--vocab-preview">
      <StudentPageHeader
        eyebrowEn={`Study · ${lessonLabel} · Vocabulary Preview`}
        titleZh="生詞預習"
        titleEn={`${items.length} words`}
      />

      <div className="sa-vocab-preview__grid" aria-label="Vocabulary preview">
        {items.map((item, index) => (
          <StudentSection key={item.wordId} variant="panel" className="sa-vocab-preview__card">
            <div className="sa-vocab-preview__card-top">
              <span className="sa-vocab-preview__index" aria-label={`Word ${index + 1}`}>
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="sa-vocab-preview__audio">
                <StudentAudioControl
                  audioUrl={item.audioUrl}
                  label="Listen"
                />
              </div>
            </div>

            <div className="sa-vocab-preview__word-stage">
              <BilingualWord
                hanzi={item.word}
                pinyin={item.pinyin}
                size="display"
                className="sa-vocab-preview__word"
              />
            </div>

            <div className="sa-vocab-preview__card-footer">
              <span
                className="sa-vocab-preview__meaning"
                title={item.meaning ?? "Meaning not available"}
              >
                {item.meaning ?? "Meaning not available"}
              </span>
            </div>
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
