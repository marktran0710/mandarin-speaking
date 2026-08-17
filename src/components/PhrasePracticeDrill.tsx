import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { convertBlobToWav } from "../utils/audio";
import { formatBackendError, getBackendUrl } from "../utils/storyRecorderFeedback";
import { toPinyin } from "../utils/pinyin";
import { scriptMatchRatio } from "../utils/scriptAlignment";
import type { WordProsody } from "./StoryRecorder";
import MiniContourChart from "./MiniContourChart";
import { BiLabel } from "./BiLabel";
import VoiceFeedbackReliabilityNotice from "./VoiceFeedbackReliabilityNotice";
import {
  assessVoiceFeedbackReliability,
  type VoiceFeedbackReliability,
} from "../utils/voiceFeedbackReliability";

// A single ASR slip on one character of a multi-character phrase shouldn't
// fail the whole phrase — only flag content when a large share of it wasn't
// recognized at all. More forgiving than WORD_PASS_RATIO because ASR noise
// is noisier than genuine mispronunciation.
const CONTENT_MATCH_RATIO = 0.7;
// Smallest n where a single wrong character still clears CONTENT_MATCH_RATIO:
// (n-1)/n >= 0.7  =>  n >= 1/(1-0.7) = 3.33, rounded up.
const MIN_CONTENT_MATCH_CHARS = 4;
// A 7-9 character phrase spoken as connected, natural speech will often have
// one weaker syllable — requiring every single word to individually pass its
// tone bar (the old rule) isn't realistic. Math.ceil keeps short phrases (2-3
// words) still needing every word right, since 80% of a small n rounds up.
const WORD_PASS_RATIO = 0.8;

/** A focused recorder for one meaning-chunk of the model sentence.
 *
 * The target text is deliberately sent as the analysis transcription: this
 * gives Praat the target tones for every character. `verify_word` still asks
 * the backend to run an independent ASR pass (returned as `recognized_text`)
 * so a learner cannot clear a chunk by making arbitrary sounds with a similar
 * pitch contour — but the match against that transcript is scored by
 * character-alignment ratio here, not the backend's own exact-substring
 * `content_match` flag, which fails the whole phrase on a single ASR slip.
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
      // `recognized_text` is only present when the backend's independent ASR
      // pass actually ran; treat its absence as "unverifiable" (fail open),
      // the same contract the backend uses for its own content_match.
      const recognizedText: string | null | undefined = data.recognized_text;
      // Below MIN_CONTENT_MATCH_CHARS, a single ASR slip already breaches
      // CONTENT_MATCH_RATIO no matter what — (n-1)/n < 0.7 for n < 4 — so the
      // ratio can't tell "one wrong character" from "totally different", the
      // exact case that broke on 2-character proper nouns like "友美". Below
      // that length, skip content-match and trust the per-word tone/shape
      // pass alone, same as WordPracticeDrill does for single characters.
      const contentGateApplies = [...phrase].length >= MIN_CONTENT_MATCH_CHARS;
      const matchRatio =
        contentGateApplies && typeof recognizedText === "string"
          ? scriptMatchRatio(phrase, recognizedText)
          : null;
      const contentMatch = matchRatio === null ? null : matchRatio >= CONTENT_MATCH_RATIO;
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
      setResult({ words, contentMatch, passed, reliability });
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
