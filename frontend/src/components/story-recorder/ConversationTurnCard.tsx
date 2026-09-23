import type { ReactNode } from "react";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import type { PraatMetrics } from "./StoryRecorder/types";
import ConversationScriptFeedback from "./ConversationScriptFeedback";
import AppButton from "../ui/AppButton";
import { BiLabel } from "../ui/BiLabel";

interface ConversationTurnCardProps {
  turn: ConversationTurn;
  children?: ReactNode;
  onSystemComplete?: () => void;
  /** Student turn only (Epic 7): the latest analysis to score the target
   * script against, and whether self-evaluation has happened yet - a
   * colored script before self-evaluation would tell the learner the
   * result before they self-assess, so this stays neutral until true. */
  responseFeedback?: { praatMetrics: PraatMetrics | null; revealed: boolean };
}

export default function ConversationTurnCard({
  turn,
  children,
  onSystemComplete,
  responseFeedback,
}: ConversationTurnCardProps) {
  const isSystem = turn.speaker === "system";
  const targetScript = turn.targetText || turn.text;
  return (
    <section
      className={`conversation-turn-card conversation-turn-card--${turn.speaker}`}
      aria-label={isSystem ? "System turn" : "Your turn"}
    >
      <div className="conversation-turn-card__eyebrow">
        <span aria-hidden="true">{isSystem ? "◉" : "◎"}</span>
        <BiLabel
          zh={isSystem ? "系統示範" : "換你說"}
          pinyin={isSystem ? "Xìtǒng shìfàn" : "Huàn nǐ shuō"}
          en={isSystem ? "System" : "Your turn"}
        />
      </div>
      {isSystem ? (
        <p className="conversation-turn-card__text" lang="zh-Hant">
          {turn.text}
        </p>
      ) : (
        <ConversationScriptFeedback
          targetScript={targetScript}
          praatMetrics={responseFeedback?.praatMetrics ?? null}
          revealed={responseFeedback?.revealed ?? false}
        />
      )}
      {turn.pinyin && <p className="conversation-turn-card__pinyin">{turn.pinyin}</p>}
      {turn.translation && <p className="conversation-turn-card__translation">{turn.translation}</p>}
      {isSystem ? (
        <div className="conversation-turn-card__audio">
          {turn.audioUrl ? (
            <audio
              controls
              preload="metadata"
              src={turn.audioUrl}
              aria-label="System turn audio"
              onEnded={onSystemComplete}
            />
          ) : (
            <p className="conversation-turn-card__missing-audio" role="status">
              No system audio is available for this turn.
            </p>
          )}
          <AppButton tone="secondary" size="sm" onClick={onSystemComplete}>
            {turn.audioUrl ? "I’m ready to respond" : "Continue"}
          </AppButton>
        </div>
      ) : children ? (
        <div className="conversation-turn-card__response">{children}</div>
      ) : null}
    </section>
  );
}
