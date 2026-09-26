import { useEffect, useState } from "react";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentButton from "@shared/ui/student/StudentButton";
import BilingualWord from "@shared/ui/student/BilingualWord";
import "./SpeechSelfEvaluation.css";

export type SelfEvalLevel = "good" | "ok" | "bad";

interface SpeechSelfEvaluationProps {
  targetText: string;
  pinyin?: string;
  translation?: string;
  modelAudioUrl?: string;
  audioBlob?: Blob | null;
  meaning: SelfEvalLevel | null;
  pronunciation: SelfEvalLevel | null;
  onMeaningChange: (value: SelfEvalLevel) => void;
  onPronunciationChange: (value: SelfEvalLevel) => void;
  onContinue: () => void;
  onSkip: () => void;
  onRecordAgain: () => void;
}

export default function SpeechSelfEvaluation({
  targetText,
  pinyin,
  translation,
  modelAudioUrl,
  audioBlob,
  meaning,
  pronunciation,
  onMeaningChange,
  onPronunciationChange,
  onContinue,
  onSkip,
  onRecordAgain,
}: SpeechSelfEvaluationProps) {
  const [recordedAudioUrl, setRecordedAudioUrl] = useState<string>();

  useEffect(() => {
    if (!audioBlob || audioBlob.size === 0) {
      setRecordedAudioUrl(undefined);
      return;
    }
    const url = URL.createObjectURL(audioBlob);
    setRecordedAudioUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audioBlob]);

  return (
    <section className="sa-self-evaluation" aria-label="Self evaluation">
      <div className="sa-self-evaluation__heading">
        <div>
          <p className="sa-self-evaluation__eyebrow">Before your result</p>
          <h2>How did you do?</h2>
          <p>Listen once, then choose the answer that feels closest to this attempt.</p>
        </div>
        <span className="sa-self-evaluation__step">1 / 2</span>
      </div>

      <div className="sa-self-evaluation__target">
        <BilingualWord hanzi={targetText} pinyin={pinyin} gloss={translation} size="display" />
        <div className="sa-self-evaluation__audio" aria-label="Listen to the model and your recording">
          <StudentAudioControl audioUrl={modelAudioUrl} label="Model" />
          <StudentAudioControl audioUrl={recordedAudioUrl} label="Your recording" />
        </div>
      </div>

      <SelfEvalRow label="Meaning" value={meaning} onChange={onMeaningChange} />
      <SelfEvalRow label="Pronunciation" value={pronunciation} onChange={onPronunciationChange} />

      <div className="sa-self-evaluation__hint" role="note">
        Your answers are saved with this attempt and are not used to change the AI score.
      </div>

      <div className="sa-self-evaluation__actions">
        <StudentButton variant="secondary" icon="replay" onClick={onRecordAgain}>
          Record again
        </StudentButton>
        <StudentButton variant="subtle" onClick={onSkip}>
          Skip self-evaluation
        </StudentButton>
        <StudentButton
          variant="primary"
          iconTrailing="arrow_forward"
          disabled={!meaning || !pronunciation}
          onClick={onContinue}
        >
          See result
        </StudentButton>
      </div>
    </section>
  );
}

function SelfEvalRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: SelfEvalLevel | null;
  onChange: (value: SelfEvalLevel) => void;
}) {
  const options: Array<{ level: SelfEvalLevel; text: string }> = [
    { level: "good", text: "Good" },
    { level: "ok", text: "OK" },
    { level: "bad", text: "Needs work" },
  ];

  return (
    <div className="sa-self-evaluation__row">
      <span className="sa-self-evaluation__label">{label}</span>
      <div className="sa-self-evaluation__options" role="group" aria-label={`${label} self-evaluation`}>
        {options.map((option) => (
          <button
            key={option.level}
            type="button"
            className={`sa-self-evaluation__option ${value === option.level ? "is-selected" : ""}`}
            aria-pressed={value === option.level}
            onClick={() => onChange(option.level)}
          >
            {option.text}
          </button>
        ))}
      </div>
    </div>
  );
}
