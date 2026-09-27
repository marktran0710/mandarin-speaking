import { useEffect, useMemo, useRef, useState } from "react";
import type { PraatMetrics, WordProsody } from "@entities/speech";
import MiniContourChart from "../../components/pitch/MiniContourChart";
import PraatTimeline from "../../components/pitch/PraatTimeline";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import { scriptMismatchTokens, splitTeacherScriptIntoPhrases } from "./scriptAlignment";
import "./SpeechResultReview.css";

interface SpeechResultReviewProps {
  targetScript: string;
  transcript?: string;
  metrics: PraatMetrics;
  audioBlob?: Blob | null;
  audioUrl?: string;
  meaningPassed: boolean;
}

interface ScriptUnit {
  text: string;
  word?: WordProsody;
}

export default function SpeechResultReview({
  targetScript,
  transcript,
  metrics,
  audioBlob,
  audioUrl,
  meaningPassed,
}: SpeechResultReviewProps) {
  const words = metrics.word_prosody ?? [];
  const units = useMemo(() => buildScriptUnits(targetScript, words), [targetScript, words]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [selectedPhrase, setSelectedPhrase] = useState<string | null>(null);
  const [recordingUrl, setRecordingUrl] = useState<string>();
  const selectedWord = selectedIndex === null ? undefined : words[selectedIndex];
  const aiFeedback = getAiFeedback(metrics);

  useEffect(() => {
    if (!audioBlob || audioBlob.size === 0 || audioUrl) {
      setRecordingUrl(undefined);
      return;
    }
    const url = URL.createObjectURL(audioBlob);
    setRecordingUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audioBlob, audioUrl]);

  return (
    <section className="sa-result-review" aria-label="口說結果">
      <div className="sa-result-review__heading">
        <div>
          <p className="sa-result-review__eyebrow"><StudentSystemText k="yourRecording" /></p>
          <h2><StudentSystemText k="seeRecordingShows" /></h2>
          <p className="sa-result-review__subheading"><StudentSystemText k="listenReviewPractice" /></p>
        </div>
        <StudentAudioControl audioUrl={audioUrl || recordingUrl} labelKey="playRecording" />
      </div>

      <div className="sa-result-review__summary" aria-label="Result summary">
        <ResultBadge label="Meaning" ok={meaningPassed} />
      </div>

      <div className="sa-result-review__script" aria-label="Word by word script">
        {units.map((unit, index) => (
          <button
            key={`${unit.text}-${index}`}
            type="button"
            className="sa-script-token"
            disabled={!unit.word}
            aria-label={`${unit.text}: 選擇以比較`}
            aria-pressed={selectedIndex === unit.word?.index}
            onClick={() => {
              if (unit.word) {
                setSelectedIndex(unit.word.index);
                setSelectedPhrase(null);
              }
            }}
          >
            <span lang="zh-Hant">{unit.text}</span>
          </button>
        ))}
      </div>

      {splitTeacherScriptIntoPhrases(targetScript).length > 0 && (
        <div className="sa-result-review__phrases" aria-label="Phrase result">
          <span>View phrase</span>
          {splitTeacherScriptIntoPhrases(targetScript).map((phrase) => (
            <button
              key={phrase}
              type="button"
              className={selectedPhrase === phrase ? "is-selected" : ""}
              aria-pressed={selectedPhrase === phrase}
              onClick={() => {
                setSelectedIndex(null);
                setSelectedPhrase((current) => current === phrase ? null : phrase);
              }}
            >
              <span lang="zh-Hant">{phrase}</span>
            </button>
          ))}
        </div>
      )}

      <p className="sa-result-review__transcript">
        <span>You said</span>
        <strong lang="zh-Hant">{transcript?.trim() || "No transcript available"}</strong>
      </p>
      {scriptMismatchTokens(targetScript, transcript).length > 0 && (
        <p className="sa-result-review__content-note" role="status">
          <StudentIcon name="info" size={16} role="meaningful" label="Content note" />
          The script portions not heard clearly: <strong lang="zh-Hant">{scriptMismatchTokens(targetScript, transcript).join(" · ")}</strong>. This affects content matching, not the tone color above.
        </p>
      )}

      {selectedWord ? (
        <WordDetail word={selectedWord} audioBlob={audioBlob} />
      ) : selectedPhrase ? (
        <PhraseDetail phrase={selectedPhrase} metrics={metrics} audioBlob={audioBlob} />
      ) : (
        <p className="sa-result-review__prompt">Select a word to see its tone shape and timing.</p>
      )}

      {aiFeedback && (
        <div className="sa-result-review__coach">
          <StudentIcon name="school" size={18} role="meaningful" label="AI coach" />
          <div>
            <strong>AI Coach</strong>
            <p>{aiFeedback}</p>
          </div>
        </div>
      )}
    </section>
  );
}

function WordDetail({ word, audioBlob }: { word: WordProsody; audioBlob?: Blob | null }) {
  const [open, setOpen] = useState(false);
  const hasPitch = (word.user_curve?.length ?? 0) > 1 || (word.pitch_contour?.length ?? 0) > 1;
  const referenceLabel = word.reference_source === "real_voice" ? "teacher recording" : "standard tone shape";

  return (
    <div className="sa-result-review__detail">
      <div className="sa-result-review__detail-heading">
        <div>
          <span className="sa-result-review__detail-label">Selected word</span>
          <strong lang="zh-Hant">{word.token}</strong>
        </div>
        <SegmentPlayButton audioBlob={audioBlob} start={word.start_time} end={word.end_time} label="Play word" />
      </div>
      {hasPitch ? (
        <div className="sa-result-review__mini-chart">
          <MiniContourChart
            actual={word.pitch_contour ?? []}
            reference={word.reference_contour}
            userCurve={word.user_curve}
            targetCurve={word.target_curve}
          />
          <p>Your pitch compared with the {referenceLabel}.</p>
        </div>
      ) : (
        <p className="sa-result-review__empty">There is not enough pitch evidence for this word.</p>
      )}
      <button type="button" className="sa-result-review__disclosure" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span>{open ? "Hide" : "Show"} Praat timeline</span>
        <StudentIcon name={open ? "expand_less" : "expand_more"} size={16} role="decorative" />
      </button>
      {open && (
        <div className="sa-result-review__timeline">
          <PraatTimeline
            audioBlob={audioBlob}
            pitchContour={word.pitch_contour ?? []}
            wordProsody={[word]}
            transcription={word.token}
            showReferenceOverlay={(word.reference_contour?.length ?? 0) > 1}
            useFallbackWordSegments={false}
          />
        </div>
      )}
    </div>
  );
}

function PhraseDetail({ phrase, metrics, audioBlob }: { phrase: string; metrics: PraatMetrics; audioBlob?: Blob | null }) {
  const phraseWords = wordsForPhrase(phrase, metrics.word_prosody ?? []);
  return (
    <div className="sa-result-review__detail">
      <div className="sa-result-review__detail-heading">
        <div>
          <span className="sa-result-review__detail-label">Selected phrase</span>
          <strong lang="zh-Hant">{phrase}</strong>
        </div>
        <SegmentPlayButton
          audioBlob={audioBlob}
          start={phraseWords[0]?.start_time}
          end={phraseWords[phraseWords.length - 1]?.end_time}
          label="Play phrase"
        />
      </div>
      <PraatTimeline
        audioBlob={audioBlob}
        pitchContour={metrics.pitch_contour ?? []}
        wordProsody={phraseWords}
        transcription={phrase}
        showReferenceOverlay={phraseWords.some((word) => (word.reference_contour?.length ?? 0) > 1)}
        useFallbackWordSegments={false}
      />
    </div>
  );
}

function wordsForPhrase(phrase: string, words: WordProsody[]): WordProsody[] {
  const compactPhrase = compact(phrase).join("");
  let cursor = 0;
  return words.filter((word) => {
    const token = compact(word.token).join("");
    if (!token) return false;
    const found = compactPhrase.indexOf(token, cursor);
    if (found < 0) return false;
    cursor = found + token.length;
    return true;
  });
}

function SegmentPlayButton({
  audioBlob,
  start,
  end,
  label,
}: {
  audioBlob?: Blob | null;
  start?: number;
  end?: number;
  label: string;
}) {
  const [url, setUrl] = useState<string>();
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!audioBlob || audioBlob.size === 0) {
      setUrl(undefined);
      return;
    }
    const nextUrl = URL.createObjectURL(audioBlob);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [audioBlob]);

  const available = Boolean(url && start !== undefined && end !== undefined && end > start);
  const onClick = () => {
    if (!available || !url) return;
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, start ?? 0);
    setPlaying(true);
    void audio.play().catch(() => setPlaying(false));
  };

  return (
    <>
      <StudentButton variant="secondary" size="sm" icon={playing ? "graphic_eq" : "play_arrow"} disabled={!available} onClick={onClick}>
        {available ? label : "Segment unavailable"}
      </StudentButton>
      {url && (
        <audio
          ref={(element) => {
            if (element) {
              audioRef.current = element;
              element.onended = () => setPlaying(false);
              element.ontimeupdate = () => {
                if (end !== undefined && element.currentTime >= end) {
                  element.pause();
                  setPlaying(false);
                }
              };
            }
          }}
          src={url}
          preload="metadata"
          className="sa-result-review__hidden-audio"
        />
      )}
    </>
  );
}

function ResultBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`sa-result-badge ${ok ? "is-correct" : "is-attention"}`}>
      <StudentIcon name={ok ? "check_circle" : "change_history"} size={16} role="decorative" />
      {label}: {ok ? "clear" : "needs attention"}
    </span>
  );
}

function getAiFeedback(metrics: PraatMetrics): string {
  const corrective = metrics.ai_feedback?.corrective_feedback;
  const feedback = corrective?.hint?.trim()
    || metrics.ai_feedback?.pronunciation_note?.feedback?.trim()
    || metrics.ai_feedback?.coherence?.feedback?.trim()
    || metrics.feedback?.trim()
    || "";
  if (feedback) return feedback;
  const provenance = metrics.feedback_provenance;
  if (provenance?.executed_provider) {
    return `Feedback from ${provenance.executed_provider}${provenance.fallback_used ? " (fallback)" : ""}. ${provenance.pronunciation_source === "praat_acoustic_measurements" ? "Pronunciation is grounded in Praat measurements." : "Pronunciation guidance is based on the local analysis."}`;
  }
  return "";
}

function compact(value: string): string[] {
  return Array.from(value.normalize("NFKC")).filter((char) => /[\p{L}\p{N}]/u.test(char));
}

function buildScriptUnits(script: string, words: WordProsody[]): ScriptUnit[] {
  const scriptChars = Array.from(script);
  const compactIndexes: number[] = [];
  scriptChars.forEach((char, index) => { if (/[\p{L}\p{N}]/u.test(char)) compactIndexes.push(index); });
  const compactScript = compactIndexes.map((index) => scriptChars[index]).join("");
  const assignments = new Map<number, WordProsody>();
  let cursor = 0;

  words.forEach((word) => {
    const token = compact(word.token).join("");
    if (!token) return;
    const found = compactScript.indexOf(token, cursor);
    if (found < 0) return;
    for (let offset = 0; offset < token.length; offset += 1) {
      const originalIndex = compactIndexes[found + offset];
      if (originalIndex !== undefined) assignments.set(originalIndex, word);
    }
    cursor = found + token.length;
  });

  const units: ScriptUnit[] = [];
  scriptChars.forEach((char, index) => {
    const word = assignments.get(index);
    const previous = units[units.length - 1];
    if (word && previous?.word?.index === word.index) {
      previous.text += char;
    } else {
      units.push({ text: char, word });
    }
  });
  return units;
}
