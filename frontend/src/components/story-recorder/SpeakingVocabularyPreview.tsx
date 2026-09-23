import ScenePracticeWord from "../speaking-flow-card/ScenePracticeWord";
import { BiLabel, BiText } from "../ui/BiLabel";
import AppButton from "../ui/AppButton";
import type { SpeakingVocabularyPreviewItem } from "../../utils/speakingVocabulary";
import "./SpeakingVocabularyPreview.css";

interface SpeakingVocabularyPreviewProps {
  items: SpeakingVocabularyPreviewItem[];
  onStart: () => void;
  onBack?: () => void;
}

/** One-Time Vocabulary Preview plan, Epic C: a quick, ungraded refresh of
 * the exact words the student already passed in the vocabulary quiz -
 * shown once before Story Practice's scenes, never a second assessment.
 * No quiz buttons, no BKT/mastery status, no correctness of any kind. */
export default function SpeakingVocabularyPreview({ items, onStart, onBack }: SpeakingVocabularyPreviewProps) {
  return (
    <section className="speaking-vocabulary-preview" aria-label="Vocabulary preview">
      {onBack && (
        <button type="button" className="speaking-vocabulary-preview__back" onClick={onBack}>
          ← <BiLabel zh="返回" en="Back" />
        </button>
      )}
      <header className="speaking-vocabulary-preview__header">
        <h2><BiLabel zh="生詞預覽" pinyin="Shēngcí yùlǎn" en="Vocabulary Preview" /></h2>
        <p className="speaking-vocabulary-preview__count">
          <BiLabel en={`${items.length} word${items.length === 1 ? "" : "s"}`} zh={`${items.length} 個生詞`} />
        </p>
        <p>
          <BiText
            zh="你已經在生詞測驗中練習過這些字。開始口說練習前，再看一次。"
            en="You've already practised these words in the vocabulary quiz. Review them once before you start speaking."
          />
        </p>
      </header>
      <ul className="speaking-vocabulary-preview__grid">
        {items.map((item) => (
          <li key={item.wordId} className="speaking-vocabulary-preview__item">
            <span className="speaking-vocabulary-preview__word" lang="zh-Hant">{item.word}</span>
            {item.pinyin && <span className="speaking-vocabulary-preview__pinyin">{item.pinyin}</span>}
            <span className="speaking-vocabulary-preview__meaning">
              {item.pos && <span className="speaking-vocabulary-preview__pos">{item.pos} · </span>}
              {item.meaning}
            </span>
            <ScenePracticeWord word={item.word} audioUrl={item.audioUrl} />
          </li>
        ))}
      </ul>
      <footer className="speaking-vocabulary-preview__footer">
        <AppButton onClick={onStart}>
          <BiLabel zh="開始口說" en="Start Speaking" />
        </AppButton>
      </footer>
    </section>
  );
}
