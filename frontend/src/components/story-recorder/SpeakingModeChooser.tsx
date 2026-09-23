import { BiLabel, BiText } from "../ui/BiLabel";
import AppButton from "../ui/AppButton";
import "./SpeakingModeChooser.css";

interface SpeakingModeChooserProps {
  exchangeCount: number;
  onChooseStory: () => void;
  onChooseConversation: () => void;
}

/** Dual Speaking Modes plan, Epic 4: Conversation Practice is a second
 * Speaking mode, not a silent replacement for Story Practice - shown only
 * when a story actually has conversation content (StoryRecorder.tsx keeps
 * every legacy, conversation-less story on its unchanged direct path). */
export default function SpeakingModeChooser({
  exchangeCount,
  onChooseStory,
  onChooseConversation,
}: SpeakingModeChooserProps) {
  return (
    <section className="speaking-mode-chooser" aria-label="Choose a speaking activity">
      <header className="speaking-mode-chooser__header">
        <h2><BiLabel zh="選擇口說練習" pinyin="Xuǎnzé kǒushuō liànxí" en="Choose how to practise" /></h2>
      </header>
      <div className="speaking-mode-chooser__options">
        <article className="speaking-mode-chooser__card">
          <span className="speaking-mode-chooser__icon" aria-hidden="true">🎙</span>
          <h3><BiLabel zh="故事練習" pinyin="Gùshì liànxí" en="Story Practice" /></h3>
          <p><BiText zh="依照故事場景逐一練習口說。" en="Practise each scene using the story script." /></p>
          <AppButton onClick={onChooseStory}>
            <BiLabel zh="開始" en="Start" />
          </AppButton>
        </article>
        <article className="speaking-mode-chooser__card">
          <span className="speaking-mode-chooser__icon" aria-hidden="true">💬</span>
          <h3><BiLabel zh="對話練習" pinyin="Duìhuà liànxí" en="Conversation Practice" /></h3>
          <p><BiText zh="聆聽角色並輪流回應。" en="Listen to the character and respond turn by turn." /></p>
          {exchangeCount > 0 && (
            <p className="speaking-mode-chooser__meta">
              <BiLabel en={`${exchangeCount} exchange${exchangeCount === 1 ? "" : "s"}`} zh={`${exchangeCount} 個對話`} />
            </p>
          )}
          <AppButton onClick={onChooseConversation}>
            <BiLabel zh="開始" en="Start" />
          </AppButton>
        </article>
      </div>
    </section>
  );
}
