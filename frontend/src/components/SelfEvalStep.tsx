import { useState } from "react";
import { BiLabel } from "./BiLabel";
import AppButton from "./AppButton";
import {
  SELF_EVAL_LEVELS,
  SELF_EVAL_EMOJI,
  type SelfEvalLevel,
} from "../utils/selfEvalComparison";
import "./SelfEvalStep.css";

const LEVEL_LABEL: Record<SelfEvalLevel, { zh: string; en: string }> = {
  good: { zh: "很好", en: "Good" },
  ok: { zh: "普通", en: "OK" },
  bad: { zh: "不太好", en: "Not great" },
};

function EmojiPicker({
  legend,
  value,
  onChange,
  groupLabel,
}: {
  legend: React.ReactNode;
  value: SelfEvalLevel | null;
  onChange: (level: SelfEvalLevel) => void;
  groupLabel: string;
}) {
  return (
    <fieldset className="self-eval-question">
      <legend className="self-eval-question-legend">{legend}</legend>
      <div className="self-eval-emoji-row" role="radiogroup" aria-label={groupLabel}>
        {SELF_EVAL_LEVELS.map((level) => (
          <button
            key={level}
            type="button"
            role="radio"
            aria-checked={value === level}
            className={`self-eval-emoji-btn${value === level ? " is-selected" : ""}`}
            onClick={() => onChange(level)}
          >
            <span aria-hidden="true" className="self-eval-emoji">
              {SELF_EVAL_EMOJI[level]}
            </span>
            <span className="self-eval-emoji-caption">
              <BiLabel zh={LEVEL_LABEL[level].zh} en={LEVEL_LABEL[level].en} />
            </span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/** A quick self-check the student answers right after listening back to a
 * recording that just cleared the scene, before seeing the system's own
 * verdict — so their self-perception isn't anchored by the system's answer.
 * Fires only once per accepted attempt; skippable, never blocks progress. */
export default function SelfEvalStep({
  onSubmit,
  onSkip,
}: {
  onSubmit: (levels: {
    content: SelfEvalLevel;
    pronunciation: SelfEvalLevel;
  }) => void;
  onSkip: () => void;
}) {
  const [content, setContent] = useState<SelfEvalLevel | null>(null);
  const [pronunciation, setPronunciation] = useState<SelfEvalLevel | null>(
    null,
  );
  const canSubmit = content !== null && pronunciation !== null;

  return (
    <div className="sfc-step-panel self-eval-step">
      <p className="self-eval-lead">
        <BiLabel
          zh="錄音完成了！在看系統回饋之前，你覺得自己說得怎麼樣？"
          pinyin="Lùyīn wánchéng le! Zài kàn xìtǒng huíkuì zhīqián, nǐ juéde zìjǐ shuō de zěnmeyàng?"
          en="Recording done! Before you see the system's feedback, how do you think you did?"
        />
      </p>

      <EmojiPicker
        legend={<BiLabel zh="意思對嗎？" pinyin="Yìsi duì ma?" en="Was the meaning right?" />}
        value={content}
        onChange={setContent}
        groupLabel="Self-rating for meaning"
      />

      <EmojiPicker
        legend={<BiLabel zh="發音和聲調呢？" pinyin="Fāyīn hé shēngdiào ne?" en="How about pronunciation and tones?" />}
        value={pronunciation}
        onChange={setPronunciation}
        groupLabel="Self-rating for pronunciation"
      />

      <div className="sfc-step-cta-row">
        <AppButton
          tone="primary"
          className="sfc-btn-next sfc-step-cta"
          disabled={!canSubmit}
          onClick={() => {
            if (content && pronunciation) onSubmit({ content, pronunciation });
          }}
        >
          <BiLabel zh="看系統回饋" en="See system feedback" /> →
        </AppButton>
        <button type="button" className="self-eval-skip" onClick={onSkip}>
          <BiLabel zh="跳過" en="Skip" />
        </button>
      </div>
    </div>
  );
}
