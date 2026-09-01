import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { convertBlobToWav } from "../../utils/audio";
import { formatBackendError, getBackendUrl } from "../../utils/storyRecorderFeedback";
import { toPinyin } from "../../utils/pinyin";
import type { ContentDiffSegment, WordProsody } from "../story-recorder/StoryRecorder";
import ContentDiffDisplay from "../ContentDiffDisplay";
import MiniContourChart from "../pitch/MiniContourChart";
import { BiLabel } from "../BiLabel";
import VoiceFeedbackReliabilityNotice from "../VoiceFeedbackReliabilityNotice";
import {
  assessVoiceFeedbackReliability,
  type VoiceFeedbackReliability,
} from "../../utils/voiceFeedbackReliability";

// A 7-9 character phrase spoken as connected, natural speech will often have
// one weaker syllable — requiring every single word to individually pass its
// tone bar (the old rule) isn't realistic. Math.ceil keeps short phrases (2-3
// words) still needing every word right, since 80% of a small n rounds up.
const WORD_PASS_RATIO = 0.8;

/** A focused recorder for one meaning-chunk of the model sentence.
 *
 * The target text is deliberately sent as the analysis transcription: this
 * gives Praat the target tones for every character. `verify_word` still asks
 * the backend to run an independent ASR pass (returned as `recognized_text`
 * and `content_match`) so a learner cannot clear a chunk by making arbitrary
 * sounds with a similar pitch contour. `content_match` is authoritative when
 * the backend was able to compute it (true/false), but a null/unverified
 * result (the check errored, timed out, or ran without a configured model)
 * fails open rather than blocking a pass — matching the backend's own stated
 * intent that a verification hiccup should never cost the student their
 * pronunciation feedback.
 */
export default function PhrasePracticeDrill({
  phrase,
  onPass,
}: {
  phrase: string;
  onPass: (phrase: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{
    words: WordProsody[];
    contentMatch: boolean | null;
    recognizedText: string | null;
    contentDiff: ContentDiffSegment[];
    passed: boolean;
    reliability: VoiceFeedbackReliability;
  } | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(
    () => () => streamRef.current?.getTracks().forEach((track) => track.stop()),
    [],
  );

  const analyze = async (audio: Blob) => {
    setIsAnalyzing(true);
    setError("");
    let backendUrl = "the configured backend";
    try {
      backendUrl = getBackendUrl();
      const wav = await convertBlobToWav(audio);
      const formData = new FormData();
      formData.append("file", wav, "phrase-practice.wav");
      formData.append("transcription", phrase);
      formData.append("verify_word", phrase);
      formData.append("scene_vocabulary", phrase);
      formData.append("ai_provider", "local");

      const response = await fetch(`${backendUrl}/api/analyze`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Phrase analysis failed.");
      }

      const data = await response.json();
      const words: WordProsody[] = data.word_prosody ?? [];
      // The backend's independent ASR result is authoritative. Missing ASR
      // evidence is unverified and cannot clear this drill.
      const recognizedText: string | null = data.recognized_text ?? null;
      const contentMatch: boolean | null = data.content_match ?? null;
      const contentDiff: ContentDiffSegment[] = data.content_diff ?? [];
      const passedWordCount = words.filter((word) => word.passed === true).length;
      const wordsOk =
        words.length > 0 && passedWordCount >= Math.ceil(words.length * WORD_PASS_RATIO);
      const reliability = assessVoiceFeedbackReliability({
        feedbackQuality: data.feedback_quality,
        contentMatch,
        wordProsody: words,
      });
      const passed =
        reliability.canCountForProgress &&
        contentMatch !== false &&
        wordsOk;
      setResult({ words, contentMatch, recognizedText, contentDiff, passed, reliability });
      if (passed) onPass(phrase);
    } catch (err) {
      setError(formatBackendError(err, backendUrl));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const startRecording = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const audio = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        await analyze(audio);
      };
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "無法使用麥克風 Could not access the microphone.",
      );
    }
  };

  const stopRecording = () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setIsRecording(false);
  };

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("audio/") && !/\.(wav|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name)) {
      setError("請選擇音訊檔案來分析這部分。 Choose an audio file to analyze this phrase.");
      return;
    }
    await analyze(file);
  };

  return (
    <section className="phrase-practice-drill" aria-label={`Practice phrase ${phrase}`}>
      <p className="phrase-practice-target" lang="zh-Hant">{phrase}</p>
      <p className="phrase-practice-pinyin">{toPinyin(phrase)}</p>
      <p className="phrase-practice-instruction">
        <BiLabel
          zh="自己說這部分，每個字都要對上目標聲調。"
          pinyin="Zìjǐ shuō zhè bùfen, měi ge zì dōu yào duì shàng mùbiāo shēngdiào."
          en="Say this part on its own. Each word should match its target pitch shape."
        />
      </p>
      <div className="word-practice-controls">
        <button
          type="button"
          className={`btn-mini ${isRecording ? "recording" : ""}`}
          onClick={isRecording ? stopRecording : startRecording}
          disabled={isAnalyzing}
        >
          {isRecording ? (
            <BiLabel zh="停止" pinyin="Tíngzhǐ" en="Stop" />
          ) : result ? (
            <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
          ) : (
            <BiLabel zh="錄這部分" pinyin="Lù zhè bùfen" en="Record this part" />
          )}
        </button>
        <label className={`btn-mini btn-mini-secondary word-practice-upload-label ${isRecording || isAnalyzing ? "disabled" : ""}`}>
          <BiLabel zh="上傳音檔" pinyin="Shàngchuán yīndàng" en="Upload audio" />
          <input
            className="word-practice-upload-input"
            type="file"
            accept="audio/*,.wav,.webm,.mp3,.m4a,.ogg,.aac,.flac"
            disabled={isRecording || isAnalyzing}
            onChange={upload}
          />
        </label>
        {isAnalyzing && (
          <span className="word-practice-status">
            <BiLabel zh="分析中…" pinyin="Fēnxī zhōng…" en="Analyzing…" />
          </span>
        )}
      </div>
      {error && <p className="word-practice-error">{error}</p>}
      {result && !isAnalyzing && (
        <div className={`phrase-practice-result ${result.passed ? "is-passed" : "is-failed"}`}>
          <VoiceFeedbackReliabilityNotice
            assessment={result.reliability}
          />
          {result.contentMatch !== true && (
            <ContentDiffDisplay
              target={phrase}
              heard={result.recognizedText}
              diff={result.contentDiff}
              contentMatch={result.contentMatch}
            />
          )}
          {result.reliability.level !== "retry" && (
            <>
          <p className="phrase-practice-verdict">
            {result.passed ? (
              <BiLabel
                zh="這部分通過了！繼續下一部分。"
                pinyin="Zhè bùfen tōngguò le! Jìxù xià yí bùfen."
                en="This part passed! Continue to the next part."
              />
            ) : (
              <BiLabel
                zh="再試一次這部分，聲調要更接近目標曲線。"
                pinyin="Zài shì yí cì zhè bùfen, shēngdiào yào gèng jiējìn mùbiāo qūxiàn."
                en="Try this part again — get your tones closer to the target shape first."
              />
            )}
          </p>
          {result.contentMatch === false && (
            <p className="word-practice-content-warning">
              <BiLabel
                zh="錄音聽起來和這部分不太一樣，還不能算過關。"
                pinyin="Lùyīn tīng qǐlái hé zhè bùfen bú tài yíyàng, hái bù néng suàn guòguān."
                en="This recording doesn't sound close enough to the target phrase yet."
              />
            </p>
          )}
          {result.contentMatch !== true && (
            <p className="word-practice-content-warning">
              Tone results below are reference-only until the target phrase is verified.
            </p>
          )}
          <div className="phrase-practice-word-results">
            {result.words.map((word, index) => (
              <div className={`phrase-practice-word ${word.passed ? "is-passed" : "is-failed"}`} key={`${word.token}-${index}`}>
                <div>
                  <strong>{word.token}</strong>
                  <span>{toPinyin(word.token)}</span>
                </div>
                <MiniContourChart
                  actual={word.pitch_contour}
                  reference={word.reference_contour}
                  userCurve={word.user_curve}
                  targetCurve={word.target_curve}
                />
                <small>
                  {word.passed ? (
                    <BiLabel zh="過關" en="Passed" />
                  ) : (
                    <BiLabel zh="待加強" en="Needs work" />
                  )}
                </small>
              </div>
            ))}
          </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
