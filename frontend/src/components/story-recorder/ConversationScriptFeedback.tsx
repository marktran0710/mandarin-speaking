import { scoreScriptChunks } from "../../utils/scriptAlignment";
import type { PraatMetrics } from "./StoryRecorder/types";

export type ResponseTokenState = "passed" | "pronunciation_attention" | "mismatch" | "unmeasured";

interface ScriptToken {
  char: string;
  state: ResponseTokenState;
}

/** Dual Speaking Modes plan, Epic 7: reuses the same alignment engine the
 * legacy Story Practice results screen already uses (scoreScriptChunks) -
 * no second NLP matching algorithm - forcing character-level chunks via
 * its explicitChunks parameter, since Mandarin text has no word spaces and
 * this app has no text segmenter to invent one from scratch. Character
 * granularity also maps naturally onto tone/pronunciation feedback, which
 * is inherently syllable-based. */
export function deriveResponseTokenStates(
  targetScript: string,
  praatMetrics: PraatMetrics | null,
): ScriptToken[] {
  const characters = Array.from(targetScript);
  if (!praatMetrics) return characters.map((char) => ({ char, state: "unmeasured" }));

  const recognizedText = praatMetrics.recognized_text ?? praatMetrics.transcription ?? "";
  const chunks = scoreScriptChunks(targetScript, recognizedText, praatMetrics.word_prosody, characters);
  return chunks.map((chunk): ScriptToken => {
    let state: ResponseTokenState;
    if (chunk.mismatch) state = "mismatch";
    else if (chunk.tokens.length === 0) state = "unmeasured";
    else if (chunk.passed) state = "passed";
    else state = "pronunciation_attention";
    return { char: chunk.text, state };
  });
}

const STATE_DETAIL: Record<ResponseTokenState, string> = {
  passed: "Matched and pronunciation passed",
  pronunciation_attention: "Tone or pronunciation needs attention",
  mismatch: "Not detected in your response",
  unmeasured: "Not confidently measured",
};

interface ConversationScriptFeedbackProps {
  targetScript: string;
  praatMetrics: PraatMetrics | null;
  /** Task-critical pedagogical rule: false shows the script neutrally
   * (record → self-evaluation → THEN feedback) - a colored script before
   * self-evaluation would tell the learner the result before they
   * self-assess. */
  revealed: boolean;
}

/** Presentation-only: all scoring comes from deriveResponseTokenStates. */
export default function ConversationScriptFeedback({
  targetScript,
  praatMetrics,
  revealed,
}: ConversationScriptFeedbackProps) {
  if (!revealed) {
    return (
      <p className="conversation-turn-card__text conversation-script-feedback conversation-script-feedback--neutral" lang="zh-Hant">
        {targetScript}
      </p>
    );
  }

  const tokens = deriveResponseTokenStates(targetScript, praatMetrics);
  return (
    <p
      className="conversation-turn-card__text conversation-script-feedback conversation-script-feedback--revealed"
      lang="zh-Hant"
      aria-label="Your response, scored word by word"
    >
      {tokens.map((token, index) => (
        <span
          key={index}
          className={`conversation-script-feedback__token conversation-script-feedback__token--${token.state}`}
          title={STATE_DETAIL[token.state]}
        >
          {token.char}
        </span>
      ))}
    </p>
  );
}
