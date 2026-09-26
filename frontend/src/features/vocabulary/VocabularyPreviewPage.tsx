import { useEffect, useMemo, useState } from "react";
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

const VOCABULARY_PAGE_SIZE = 12;

interface VocabularyPreviewPageProps {
  topic: Topic;
  lessonLabel: string;
  onStartSpeaking: () => void;
}

export default function VocabularyPreviewPage({ topic, lessonLabel, onStartSpeaking }: VocabularyPreviewPageProps) {
  const items = useMemo(() => speakingVocabularyItems(topic), [topic]);
  const hasQuiz = topicHasQuiz(topic);
  const [pageIndex, setPageIndex] = useState(0);

  useEffect(() => {
    setPageIndex(0);
  }, [topic.id]);

  const pageCount = Math.max(1, Math.ceil(items.length / VOCABULARY_PAGE_SIZE));
  const activePageIndex = Math.min(pageIndex, pageCount - 1);
  const pageStart = activePageIndex * VOCABULARY_PAGE_SIZE;
  const visibleItems = items.slice(pageStart, pageStart + VOCABULARY_PAGE_SIZE);
  const hasPagination = items.length > VOCABULARY_PAGE_SIZE;

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
    <StudentPage
      layout="task"
      wide
      className="sa-vocab-preview-page"
      header={header}
      actions={{ primary: primaryAction }}
    >
      <div
        className={`sa-vocab-preview__grid${hasPagination ? " is-paginated" : ""}`}
        aria-label="Vocabulary preview"
      >
        {visibleItems.map((item, index) => (
          <StudentSection key={item.wordId} variant="panel" className="sa-vocab-preview__card">
            <div className="sa-vocab-preview__card-top">
              <span className="sa-vocab-preview__index" aria-label={`Word ${pageStart + index + 1}`}>
                {String(pageStart + index + 1).padStart(2, "0")}
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

      {hasPagination && (
        <nav className="sa-vocab-preview__pager" aria-label="Vocabulary pages">
          <StudentButton
            variant="secondary"
            size="sm"
            icon="arrow_back"
            aria-label="Previous vocabulary page"
            disabled={activePageIndex === 0}
            onClick={() => setPageIndex((current) => Math.max(0, current - 1))}
          >
            <span lang="zh-Hant">上一頁</span> · Previous
          </StudentButton>
          <span className="sa-vocab-preview__pager-status" role="status">
            {pageStart + 1}–{Math.min(pageStart + VOCABULARY_PAGE_SIZE, items.length)} of {items.length}
          </span>
          <StudentButton
            variant="secondary"
            size="sm"
            iconTrailing="arrow_forward"
            aria-label="Next vocabulary page"
            disabled={activePageIndex === pageCount - 1}
            onClick={() => setPageIndex((current) => Math.min(pageCount - 1, current + 1))}
          >
            <span lang="zh-Hant">下一頁</span> · Next
          </StudentButton>
        </nav>
      )}
    </StudentPage>
  );
}
