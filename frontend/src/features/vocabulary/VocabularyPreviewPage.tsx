import { useMemo } from "react";
import type { Topic } from "@entities/topic";
import { speakingVocabularyItems, topicHasQuiz } from "@entities/vocabulary";
import { topicStoryId } from "../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import BilingualWord from "@shared/ui/student/BilingualWord";
import "./VocabularyPreviewPage.css";

interface VocabularyPreviewPageProps {
  topic: Topic;
  lessonLabel: string;
  onStartSpeaking: () => void;
}

export default function VocabularyPreviewPage({ topic, lessonLabel, onStartSpeaking }: VocabularyPreviewPageProps) {
  const items = useMemo(() => speakingVocabularyItems(topic), [topic]);
  const hasQuiz = topicHasQuiz(topic);

  const handleStartSpeaking = () => {
    markPhaseSeen(topicStoryId(topic), "vocab");
    onStartSpeaking();
  };

  const header = (
    <StudentPageHeader
      eyebrowZh={`學習 · ${lessonLabel} · 生詞預習`}
      eyebrowEn={`Study · ${lessonLabel} · Vocabulary Preview`}
      titleZh="生詞預習"
      titleEn={`${items.length} words`}
    />
  );

  const primaryAction = (
    <StudentButton variant="primary" size="lg" iconTrailing="arrow_forward" onClick={handleStartSpeaking}>
      {hasQuiz
        ? <><span lang="zh-Hant">開始測驗</span> · Start quiz</>
        : <><span lang="zh-Hant">開始口說練習</span> · Start speaking</>}
    </StudentButton>
  );

  if (items.length === 0) {
    return (
      <StudentPage
        layout="task"
        header={header}
        state="empty"
        emptyTitle={<><span lang="zh-Hant">本課沒有生詞</span> · This lesson has no vocabulary</>}
        emptyAction={primaryAction}
      />
    );
  }

  return (
    <StudentPage layout="task" wide header={header} actions={{ primary: primaryAction }}>
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
    </StudentPage>
  );
}
