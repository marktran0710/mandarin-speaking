import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { PraatMetrics, WordProsody } from "@entities/speech";
import MiniContourChart from "../../components/pitch/MiniContourChart";
import PraatTimeline from "../../components/pitch/PraatTimeline";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import { studentUiCopy, type StudentUiCopyKey } from "../../i18n/student-ui-copy";
import { scriptMismatchTokens, splitTeacherScriptIntoPhrases } from "./scriptAlignment";
import { buildModelOverlay, type ModelOverlay, type SentenceModelContour } from "./modelOverlay";
import ReferenceComparison from "./ReferenceComparison";
import "./SpeechResultReview.css";

// Both speaking flows show separate rubric scores unless explicitly disabled.
const SHOW_VOICE_RUBRIC_SCORES = import.meta.env.VITE_SHOW_VOICE_RUBRIC_SCORES !== "false";

interface SpeechResultReviewProps {
  targetScript: string;
  transcript?: string;
  metrics: PraatMetrics;
  audioBlob?: Blob | null;
  audioUrl?: string;
  meaningPassed: boolean;
  /** The scene's teacher model-voice shape, when one was recorded. */
  modelContour?: SentenceModelContour | null;
  /** Optional content rendered inside the review card after the feedback. */
  footer?: ReactNode;
}

interface ScriptUnit {
  text: string;
  word?: WordProsody;
}

export default function SpeechResultReview({
  targetScript: requestedTargetScript,
  transcript,
  metrics,
  audioBlob,
  audioUrl,
  meaningPassed,
  modelContour,
  footer,
}: SpeechResultReviewProps) {
  const pronunciation = metrics.pronunciation_evaluation;
  const targetScript = pronunciation?.target_text ?? requestedTargetScript;
  const words = metrics.word_prosody ?? [];
  const modelOverlay = useMemo(
    () => buildModelOverlay({
      contour: modelContour,
      targetScript,
      transcript,
      words,
      pitchContour: metrics.pitch_contour ?? [],
    }),
    [modelContour, targetScript, transcript, words, metrics.pitch_contour],
  );
  const units = useMemo(() => buildScriptUnits(targetScript, words), [targetScript, words]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [selectedPhrase, setSelectedPhrase] = useState<string | null>(null);
  const [recordingUrl, setRecordingUrl] = useState<string>();
  const selectedWord = selectedIndex === null ? undefined : words[selectedIndex];
  const aiFeedback = pronunciation?.feedback.summary ?? getAiFeedback(metrics);

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

      <div className="sa-result-review__summary" aria-label={studentUiCopy.resultStep.zh}>
        <ResultBadge ok={meaningPassed} />
      </div>

      {SHOW_VOICE_RUBRIC_SCORES && pronunciation?.dimensions && (
        <>
          <p className="sa-result-review__rubric-note"><StudentSystemText k="rubricResearchStatus" /></p>
          <div className="sa-result-review__rubrics" aria-label="Pronunciation dimensions">
            {Object.values(pronunciation.dimensions).map((dimension) => (
              <article key={dimension.key} className="sa-result-review__rubric">
                <strong><StudentSystemText k={dimension.key === "accuracy" ? "accuracyLabel" : dimension.key === "pronunciation" ? "pronunciationLabel" : dimension.key === "fluency" ? "fluencyLabel" : "prosodyLabel"} /></strong>
                <p>{dimension.score == null ? <StudentSystemText k="scoreNotAssessed" /> : <strong>{dimension.score}/5</strong>}</p>
                <p>{dimension.key === "accuracy" ? <StudentSystemText k="accuracyNotAssessed" /> : dimension.feedback || dimension.reason}</p>
                {dimension.key === "pronunciation" && (
                  <small>
                    {(dimension.pronunciation_errors?.length ?? 0) > 0 && `${dimension.pronunciation_errors?.length} segmental issues. `}
                    {(dimension.tone_errors?.length ?? 0) > 0 && `${dimension.tone_errors?.length} tone issues.`}
                  </small>
                )}
              </article>
            ))}
          </div>
        </>
      )}

      <div className="sa-result-review__script" aria-label={studentUiCopy.wordByWord.zh}>
        {scriptUnitGroups(units).map((group) => (
          <span className="sa-script-group" key={group[0].index}>
            {group.map(({ unit, index }) => (
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
          </span>
        ))}
      </div>

      {splitTeacherScriptIntoPhrases(targetScript).length > 0 && (
        <div className="sa-result-review__phrases" aria-label={studentUiCopy.viewPhrase.zh}>
          <span><StudentSystemText k="viewPhrase" /></span>
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
        <span><StudentSystemText k="youSaid" /></span>
        <strong lang="zh-Hant">{transcript?.trim() || studentUiCopy.noTranscript.zh}</strong>
      </p>
      {scriptMismatchTokens(targetScript, transcript).length > 0 && (
        <p className="sa-result-review__content-note" role="status">
          <StudentIcon name="info" size={16} role="meaningful" label={studentUiCopy.contentNote.zh} />
          <span>
            <span>
              <StudentSystemText k="notHeardClearly" /> <strong lang="zh-Hant">{scriptMismatchTokens(targetScript, transcript).join(" · ")}</strong>
            </span>
            <StudentSystemText k="notHeardNote" />
          </span>
        </p>
      )}

      <div className="sa-result-review__tone">
        <p className="sa-result-review__eyebrow"><StudentSystemText k="toneChart" /></p>
        <PraatTimeline
          audioBlob={audioBlob}
          pitchContour={metrics.pitch_contour ?? []}
          wordProsody={words}
          transcription={targetScript}
          modelOverlay={modelOverlay}
          useFallbackWordSegments={false}
        />
        {selectedWord ? (
          <WordDetail word={selectedWord} audioBlob={audioBlob} modelOverlay={modelOverlay} />
        ) : selectedPhrase ? (
          <PhraseDetail phrase={selectedPhrase} metrics={metrics} audioBlob={audioBlob} modelOverlay={modelOverlay} />
        ) : (
          <p className="sa-result-review__prompt"><StudentSystemText k="tapAWord" /></p>
        )}
      </div>

      {pronunciation?.reference_comparison && <ReferenceComparison comparison={pronunciation.reference_comparison} />}

      {aiFeedback && (
        <div className="sa-result-review__coach">
          <StudentIcon name="school" size={18} role="meaningful" label={studentUiCopy.aiTeacher.zh} />
          <div>
            <strong><StudentSystemText k="aiTeacher" /></strong>
            {pronunciation?.model.feedback_model && <span> · {pronunciation.model.feedback_model}</span>}
            <p>{aiFeedback}</p>
            {pronunciation?.feedback.focus_words.map((focus) => (
              <p key={focus.word}><strong lang="zh-Hant">{focus.word}</strong>：<span>{focus.feedback}</span></p>
            ))}
            {pronunciation?.feedback.practice_tip && <p>{pronunciation.feedback.practice_tip}</p>}
            {pronunciation?.reference.audio_url && (
              <StudentAudioControl audioUrl={pronunciation.reference.audio_url} labelKey="teacherModel" />
            )}
          </div>
        </div>
      )}

      {footer && <div className="sa-result-review__footer">{footer}</div>}
    </section>
  );
}

function WordDetail({ word, audioBlob, modelOverlay }: { word: WordProsody; audioBlob?: Blob | null; modelOverlay: ModelOverlay }) {
  const [open, setOpen] = useState(false);
  const hasPitch = (word.pitch_contour?.length ?? 0) > 1;
  const wordOverlay = overlayForWords(modelOverlay, [word]);
  const modelPoints = wordOverlay.status === "ok" ? wordOverlay.segments[0]?.points : undefined;

  return (
    <div className="sa-result-review__detail">
      <div className="sa-result-review__detail-heading">
        <div>
          <span className="sa-result-review__detail-label"><StudentSystemText k="selectedWord" /></span>
          <strong lang="zh-Hant">{word.token}</strong>
        </div>
        <SegmentPlayButton audioBlob={audioBlob} start={word.start_time} end={word.end_time} labelKey="playWord" />
      </div>
      {hasPitch ? (
        <div className="sa-result-review__mini-chart">
          <MiniContourChart actual={word.pitch_contour ?? []} reference={modelPoints} />
          <p><StudentSystemText k={modelPoints ? "pitchVsModel" : modelNoticeKey(modelOverlay)} /></p>
        </div>
      ) : (
        <p className="sa-result-review__empty"><StudentSystemText k="notEnoughPitch" /></p>
      )}
      <button type="button" className="sa-result-review__disclosure" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span><StudentSystemText k={open ? "hideSoundChart" : "showSoundChart"} withinControl /></span>
        <StudentIcon name={open ? "expand_less" : "expand_more"} size={16} role="decorative" />
      </button>
      {open && (
        <div className="sa-result-review__timeline">
          <PraatTimeline
            audioBlob={audioBlob}
            pitchContour={word.pitch_contour ?? []}
            wordProsody={[word]}
            transcription={word.token}
            modelOverlay={wordOverlay}
            useFallbackWordSegments={false}
          />
        </div>
      )}
    </div>
  );
}

function PhraseDetail({ phrase, metrics, audioBlob, modelOverlay }: { phrase: string; metrics: PraatMetrics; audioBlob?: Blob | null; modelOverlay: ModelOverlay }) {
  const phraseWords = wordsForPhrase(phrase, metrics.word_prosody ?? []);
  return (
    <div className="sa-result-review__detail">
      <div className="sa-result-review__detail-heading">
        <div>
          <span className="sa-result-review__detail-label"><StudentSystemText k="selectedPhrase" /></span>
          <strong lang="zh-Hant">{phrase}</strong>
        </div>
        <SegmentPlayButton
          audioBlob={audioBlob}
          start={phraseWords[0]?.start_time}
          end={phraseWords[phraseWords.length - 1]?.end_time}
          labelKey="playPhrase"
        />
      </div>
      <PraatTimeline
        audioBlob={audioBlob}
        pitchContour={metrics.pitch_contour ?? []}
        wordProsody={phraseWords}
        transcription={phrase}
        modelOverlay={overlayForWords(modelOverlay, phraseWords)}
        useFallbackWordSegments={false}
      />
    </div>
  );
}

/** Narrows a sentence overlay to the words a detail view shows. A word with
 * no model segment of its own reads as "missing" there. */
function overlayForWords(overlay: ModelOverlay, shown: WordProsody[]): ModelOverlay {
  if (overlay.status !== "ok") return overlay;
  const indexes = new Set(shown.map((word) => word.index));
  const segments = overlay.segments.filter((segment) => indexes.has(segment.wordIndex));
  return segments.length ? { status: "ok", segments } : { status: "missing" };
}

function modelNoticeKey(overlay: ModelOverlay): StudentUiCopyKey {
  return overlay.status === "mismatch" ? "modelHiddenDifferent" : "noModelWord";
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
  labelKey,
}: {
  audioBlob?: Blob | null;
  start?: number;
  end?: number;
  labelKey: StudentUiCopyKey;
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
        <StudentSystemText k={available ? labelKey : "segmentUnavailable"} withinControl />
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

function ResultBadge({ ok }: { ok: boolean }) {
  return (
    <span className={`sa-result-badge ${ok ? "is-correct" : "is-attention"}`}>
      <StudentIcon name={ok ? "check_circle" : "change_history"} size={16} role="decorative" />
      <span><StudentSystemText k="meaningLabel" withinControl />：<StudentSystemText k={ok ? "resultClear" : "resultNeedsWork"} withinControl /></span>
    </span>
  );
}

function getAiFeedback(metrics: PraatMetrics): string {
  const corrective = metrics.ai_feedback?.corrective_feedback;
  const feedback = corrective?.hint?.trim()
    || metrics.ai_feedback?.pronunciation_note?.feedback?.trim()
    || metrics.ai_feedback?.coherence?.feedback?.trim()
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

/** Groups each unit with the punctuation-only units that follow it so a
 * closing 。？ can never wrap onto a line of its own. */
function scriptUnitGroups(units: ScriptUnit[]) {
  const groups: Array<Array<{ unit: ScriptUnit; index: number }>> = [];
  units.forEach((unit, index) => {
    const isPunctuation = !unit.word && /^[\p{P}\s]+$/u.test(unit.text);
    const last = groups[groups.length - 1];
    if (isPunctuation && last) last.push({ unit, index });
    else groups.push([{ unit, index }]);
  });
  return groups;
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
