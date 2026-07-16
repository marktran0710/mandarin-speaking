import { type ChangeEvent, type ReactNode, useRef, useState } from "react";
import PraatTimeline from "../components/PraatTimeline";
import { convertBlobToWav } from "../utils/audio";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import "./VoiceTestPage.css";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");
const VOICE_TEST_ASR_MODEL = import.meta.env.VITE_VOICE_TEST_ASR_MODEL || "ctwhisper";

interface WordProsody {
  token: string;
  index: number;
  start_time?: number;
  end_time?: number;
  pitch_contour?: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  mean_pitch: number;
  pitch_range: number;
  start_pitch?: number;
  end_pitch?: number;
  contour_shape: string;
  feedback: string;
}

interface VoiceMetrics {
  description?: string;
  transcription?: string;
  transcription_model?: string;
  pitch_contour: Array<[number, number]>;
  word_prosody?: WordProsody[];
  detected_tone: number;
  tone_accuracy: number;
  speech_rate: number;
  fluency_score: number;
  feedback: string;
  ai_feedback?: {
    provider: string;
    fluency: { score: number; feedback: string };
    grammar: { score: number; feedback: string; corrections: string[] };
    vocabulary: { score: number; feedback: string; suggestions: string[] };
    improved_version: string;
    practice_prompt: string;
  };
}

export default function VoiceTestPage() {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [metrics, setMetrics] = useState<VoiceMetrics | null>(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [selectedAudioName, setSelectedAudioName] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const transcriptRef = useRef("");
  const startTimeRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startRecording = async () => {
    setError("");
    setMetrics(null);
    setAudioUrl("");
    setAudioBlob(null);
    setSelectedAudioName("");
    setLiveTranscript("");
    transcriptRef.current = "";
    setRecordingDuration(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const preferredType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const recorder = new MediaRecorder(
        stream,
        preferredType ? { mimeType: preferredType } : undefined,
      );
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const rawBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stopTracks();
        await analyzeAudio(
          rawBlob,
          "voice-test.wav",
          true,
          transcriptRef.current.trim(),
        );
      };

      startTimeRef.current = Date.now();
      durationTimerRef.current = setInterval(() => {
        setRecordingDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 250);

      recorder.start();
      startSpeechRecognition();
      setIsRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "無法存取麥克風。 Could not access microphone.");
      stopTracks();
      clearDurationTimer();
    }
  };

  const stopRecording = () => {
    recognitionRef.current?.stop();
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    clearDurationTimer();
  };

  const handleImportWav = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    const isWav =
      file.type === "audio/wav" ||
      file.type === "audio/wave" ||
      file.type === "audio/x-wav" ||
      file.type === "audio/vnd.wave" ||
      file.name.toLowerCase().endsWith(".wav");

    if (!isWav) {
      setError(`匯入的檔案格式不支援，請上傳 WAV 檔案。 Import a WAV file. "${file.name}" is not supported yet.`);
      return;
    }

    setError("");
    setMetrics(null);
    setRecordingDuration(0);
    setSelectedAudioName(file.name);
    await analyzeAudio(file, normalizeWavFileName(file.name), false);
  };

  const startSpeechRecognition = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setLiveTranscript("瀏覽器不支援即時語音轉錄。 Browser speech transcription is not available.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "zh-TW";

    recognition.onresult = (event: any) => {
      let finalText = transcriptRef.current;
      let interimText = "";

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const text = event.results[index][0].transcript;
        if (event.results[index].isFinal) {
          finalText = `${finalText} ${text}`.trim();
        } else {
          interimText = `${interimText} ${text}`.trim();
        }
      }

      transcriptRef.current = finalText;
      setLiveTranscript([finalText, interimText].filter(Boolean).join(" "));
    };

    recognition.onerror = () => {
      setLiveTranscript(
        transcriptRef.current ||
          "瀏覽器語音轉錄已停止，Praat 仍會分析這段音檔。 Browser speech transcription stopped. Praat will still analyze the audio.",
      );
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const analyzeAudio = async (
    rawBlob: Blob,
    fileName = "voice-test.wav",
    shouldConvertToWav = true,
    transcription = "",
  ) => {
    setIsAnalyzing(true);
    try {
      const wavBlob = shouldConvertToWav ? await convertBlobToWav(rawBlob) : rawBlob;
      const normalizedWavBlob = ensureWavBlob(wavBlob);
      setAudioBlob(normalizedWavBlob);
      setAudioUrl(URL.createObjectURL(normalizedWavBlob));

      const formData = new FormData();
      formData.append("file", normalizedWavBlob, fileName);
      formData.append("transcription", transcription);
      if (!transcription.trim()) {
        formData.append("asr_model", VOICE_TEST_ASR_MODEL);
      }

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "語音分析失敗。 Voice analysis failed.");
      }

      setMetrics((await response.json()) as VoiceMetrics);
    } catch (err) {
      setError(formatBackendError(err, BACKEND_URL || "the configured backend"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const clearDurationTimer = () => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  };

  const stopTracks = () => {
    recognitionRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const primaryLabel = isRecording
    ? { zh: "停止，看回饋", pinyin: "Tíngzhǐ, kàn huíkuì", en: "Stop and get feedback" }
    : metrics
      ? { zh: "再錄一次", pinyin: "Zài lù yí cì", en: "Record again" }
      : { zh: "開始語音測試", pinyin: "Kāishǐ yǔyīn cèshì", en: "Start voice test" };

  return (
    <main className="voice-test-page">
      <section className="voice-test-hero">
        <div>
          <p className="eyebrow">
            <BiLabel zh="語音練習" pinyin="Yǔyīn liànxí" en="Voice practice" />
          </p>
          <h1>
            <BiLabel zh="分析你的聲音" pinyin="Fēnxī nǐ de shēngyīn" en="Analyze Your Voice" />
          </h1>
          <p>
            <BiText
              zh="錄音或上傳 WAV 檔案，系統會轉錄音檔，然後檢查發音和語言表現，給你回饋。"
              pinyin="Lùyīn huò shàngchuán WAV dǎng'àn, xìtǒng huì zhuǎnlù yīndǎng, ránhòu jiǎnchá fāyīn hé yǔyán biǎoxiàn, gěi nǐ huíkuì."
              en="Record or upload a WAV file. The system transcribes the audio, then checks pronunciation and language feedback from the recording."
            />
          </p>
        </div>
        <div className="voice-test-status">
          <span>
            <BiLabel zh="狀態" pinyin="Zhuàngtài" en="Status" />
          </span>
          <strong>
            {isRecording ? (
              <BiLabel zh="錄音中" pinyin="Lùyīn zhōng" en="Recording" />
            ) : isAnalyzing ? (
              <BiLabel zh="分析中" pinyin="Fēnxī zhōng" en="Analyzing" />
            ) : (
              <BiLabel zh="準備好了" pinyin="Zhǔnbèi hǎo le" en="Ready" />
            )}
          </strong>
          <p>
            {isRecording ? (
              <BiLabel
                zh={`已錄音 ${recordingDuration} 秒`}
                pinyin={`Yǐ lùyīn ${recordingDuration} miǎo`}
                en={`${recordingDuration}s recorded`}
              />
            ) : (
              <BiLabel zh="錄一次就夠了。" pinyin="Lù yí cì jiù gòu le." en="One recording is enough." />
            )}
          </p>
        </div>
      </section>

      <section className="voice-test-workspace">
        <div className="voice-step-row" aria-label="Voice test steps">
          <span>
            <BiLabel zh="1. 說話或上傳" pinyin="1. Shuōhuà huò shàngchuán" en="1. Speak or upload" />
          </span>
          <span>
            <BiLabel zh="2. 轉錄音檔" pinyin="2. Zhuǎnlù yīndǎng" en="2. Transcribe audio" />
          </span>
          <span>
            <BiLabel zh="3. 查看結果" pinyin="3. Chákàn jiéguǒ" en="3. Review" />
          </span>
        </div>

        <div className="voice-test-controls">
          <button
            type="button"
            className={`btn ${isRecording ? "btn-danger" : "btn-primary"}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing}
          >
            <BiLabel zh={primaryLabel.zh} pinyin={primaryLabel.pinyin} en={primaryLabel.en} />
          </button>
          <label
            className={`btn btn-secondary voice-file-label ${
              isRecording || isAnalyzing ? "disabled" : ""
            }`}
          >
            <BiLabel zh="匯入 WAV 檔案" pinyin="Huìrù WAV dǎng'àn" en="Import WAV file" />
            <input
              className="voice-file-input"
              type="file"
              accept=".wav,audio/wav,audio/wave,audio/x-wav,audio/vnd.wave"
              onChange={handleImportWav}
              disabled={isRecording || isAnalyzing}
            />
          </label>
        </div>

        {audioUrl && (
          <div className="voice-audio-preview">
            <span id="voice-audio-preview-label">
              <BiLabel zh="錄音預覽" pinyin="Lùyīn yùlǎn" en="Recording preview" />
            </span>
            {selectedAudioName && <strong>{selectedAudioName}</strong>}
            <audio controls src={audioUrl} aria-labelledby="voice-audio-preview-label" />
          </div>
        )}

        {liveTranscript && (
          <div className="voice-live-transcript">
            <span>
              <BiLabel zh="即時轉錄" pinyin="Jíshí zhuǎnlù" en="Live transcript" />
            </span>
            <p>{liveTranscript}</p>
          </div>
        )}
      </section>

      {isAnalyzing && (
        <p className="voice-test-loading">
          <BiLabel zh="正在執行 Praat 分析和本地回饋…" pinyin="Zhèngzài zhíxíng Praat fēnxī hé běndì huíkuì…" en="Running Praat and local feedback..." />
        </p>
      )}
      {error && <p className="voice-test-error">{error}</p>}

      {metrics && (
        <section className="voice-feedback-panel">
          <div className="voice-score-grid">
            <ScoreCard
              label={<BiLabel zh="流暢度" pinyin="Liúchàng dù" en="Fluency" />}
              value={`${Math.round(metrics.fluency_score)}/100`}
            />
            <ScoreCard
              label={<BiLabel zh="聲調準確度" pinyin="Shēngdiào zhǔnquè dù" en="Tone accuracy" />}
              value={`${Math.round(metrics.tone_accuracy)}%`}
            />
            <ScoreCard
              label={<BiLabel zh="語速" pinyin="Yǔsù" en="Speech rate" />}
              value={`${metrics.speech_rate.toFixed(1)}/s`}
            />
          </div>

          <StudentFeedbackCards
            toneAccuracy={metrics.tone_accuracy}
            fluencyScore={metrics.fluency_score}
            speechRate={metrics.speech_rate}
            wordProsody={metrics.word_prosody || []}
          />

          <ModelExampleCard
            text={metrics.transcription || "今天下雨，所以我帶傘。"}
            focusWord={getToneFocusItems(metrics.word_prosody || [])[0]?.token}
          />

          <div className="voice-feedback-card">
            <h2>
              <BiLabel zh="音檔轉錄結果" pinyin="Yīndǎng zhuǎnlù jiéguǒ" en="Transcription from audio" />
            </h2>
            {metrics.description && (
              <p className="voice-result-description">{metrics.description}</p>
            )}
            <p className="voice-transcript-text">
              {metrics.transcription || (
                <BiText
                  zh="沒有轉錄結果，以下數據以音檔本身為準。"
                  pinyin="Méiyǒu zhuǎnlù jiéguǒ, yǐxià shùjù yǐ yīndǎng běnshēn wéi zhǔn."
                  en="No transcription was returned. Praat metrics are based on the audio file."
                />
              )}
            </p>
            <ScriptWordLevel
              transcription={metrics.transcription || ""}
              wordProsody={metrics.word_prosody}
            />
            {metrics.transcription_model && (
              <small className="voice-model-note">
                <BiLabel zh={`辨識模型：${metrics.transcription_model}`} en={`ASR model: ${metrics.transcription_model}`} />
              </small>
            )}
          </div>

          <details className="voice-advanced-details">
            <summary>
              <BiLabel zh="進階 Praat 詳細資料" pinyin="Jìnjiē Praat xiángxì zīliào" en="Advanced Praat details" />
            </summary>
          <div className="voice-feedback-card">
            <h2>
              <BiLabel zh="Praat 回饋" pinyin="Praat huíkuì" en="Praat feedback" />
            </h2>
            <p>{metrics.feedback}</p>
          </div>

          <div className="voice-feedback-card voice-praat-visual-card">
            <h2>
              <BiLabel zh="Praat 視覺化圖表" pinyin="Praat shìjué huà túbiǎo" en="Praat visualization" />
            </h2>
            <PraatTimeline
              audioBlob={audioBlob}
              pitchContour={metrics.pitch_contour}
              wordProsody={normalizeWordProsody(metrics.word_prosody)}
              transcription={metrics.transcription || ""}
            />
          </div>

          {metrics.word_prosody && metrics.word_prosody.length > 0 && (
            <div className="voice-feedback-card">
              <h2>
                <BiLabel zh="逐字韻律分析" pinyin="Zhúzì yùnlǜ fēnxī" en="Word-level prosody" />
              </h2>
              <div className="voice-word-grid">
                {metrics.word_prosody.map((word) => (
                  <div className="voice-word-card" key={`${word.token}-${word.index}`}>
                    <strong lang="zh-Hant">{word.token}</strong>
                    <span>
                      <BiLabel {...formatContourShape(word.contour_shape)} />
                    </span>
                    <small>
                      <BiLabel
                        zh={`平均 ${Math.round(word.mean_pitch)} Hz · 範圍 ${Math.round(word.pitch_range)} Hz`}
                        en={`${Math.round(word.mean_pitch)} Hz avg · ${Math.round(word.pitch_range)} Hz range`}
                      />
                    </small>
                    <p>{word.feedback}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          </details>

          {metrics.ai_feedback && (
            <div className="voice-feedback-card ai-card">
              <div className="ai-card-header">
                <h2>
                  <BiLabel zh="AI 回饋" pinyin="AI huíkuì" en="AI feedback" />
                </h2>
                <span>{metrics.ai_feedback.provider}</span>
              </div>
              <div className="ai-feedback-columns">
                <FeedbackBlock
                  title={<BiLabel zh="流暢度" pinyin="Liúchàng dù" en="Fluency" />}
                  score={metrics.ai_feedback.fluency.score}
                  text={metrics.ai_feedback.fluency.feedback}
                />
                <FeedbackBlock
                  title={<BiLabel zh="文法" pinyin="Wénfǎ" en="Grammar" />}
                  score={metrics.ai_feedback.grammar.score}
                  text={metrics.ai_feedback.grammar.feedback}
                />
                <FeedbackBlock
                  title={<BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" />}
                  score={metrics.ai_feedback.vocabulary.score}
                  text={metrics.ai_feedback.vocabulary.feedback}
                />
              </div>
              {metrics.ai_feedback.improved_version && (
                <p className="improved-version">
                  <strong>
                    <BiLabel zh="改進版本：" pinyin="Gǎijìn bǎnběn:" en="Improved version:" />
                  </strong>{" "}
                  {metrics.ai_feedback.improved_version}
                </p>
              )}
              <p className="practice-prompt">
                <strong>
                  <BiLabel zh="下一步練習：" pinyin="Xià yí bù liànxí:" en="Practice next:" />
                </strong>{" "}
                {metrics.ai_feedback.practice_prompt}
              </p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function normalizeWavFileName(fileName: string): string {
  return fileName.toLowerCase().endsWith(".wav") ? fileName : `${fileName}.wav`;
}

function ensureWavBlob(blob: Blob): Blob {
  if (blob.type === "audio/wav" || blob.type === "audio/x-wav") {
    return blob;
  }

  return new Blob([blob], { type: "audio/wav" });
}

function normalizeWordProsody(words: WordProsody[] = []) {
  return words.map((word, index) => ({
    token: word.token,
    index: word.index ?? index,
    start_time: word.start_time ?? index,
    end_time: word.end_time ?? index + 1,
    pitch_contour: word.pitch_contour ?? [],
    reference_contour: word.reference_contour ?? [],
    mean_pitch: word.mean_pitch,
    pitch_range: word.pitch_range,
    start_pitch: word.start_pitch ?? word.mean_pitch,
    end_pitch: word.end_pitch ?? word.mean_pitch,
    contour_shape: word.contour_shape,
    feedback: word.feedback,
  }));
}

function ScriptWordLevel({
  transcription,
  wordProsody = [],
}: {
  transcription: string;
  wordProsody?: WordProsody[];
}) {
  const scriptWords =
    wordProsody.length > 0
      ? wordProsody.map((word, index) => ({
          token: word.token,
          index: word.index ?? index,
          contour: word.contour_shape,
          feedback: word.feedback,
          meanPitch: word.mean_pitch,
          pitchRange: word.pitch_range,
        }))
      : tokenizeTranscript(transcription).map((token, index) => ({
          token,
          index,
          contour: "",
          feedback: "",
          meanPitch: 0,
          pitchRange: 0,
        }));

  if (scriptWords.length === 0) {
    return (
      <div className="voice-script-empty">
        <BiText
          zh="音檔轉錄完成後，會顯示逐字稿。"
          pinyin="Yīndǎng zhuǎnlù wánchéng hòu, huì xiǎnshì zhúzì gǎo."
          en="Word-level script appears after audio transcription."
        />
      </div>
    );
  }

  return (
    <div className="voice-script-level" aria-label="Word-level script">
      {scriptWords.map((word) => (
        <span
          className="voice-script-token"
          key={`${word.token}-${word.index}`}
          title={word.feedback || undefined}
        >
          <strong lang="zh-Hant">{word.token}</strong>
          {word.contour && (
            <em>
              <BiLabel {...formatContourShape(word.contour)} />
            </em>
          )}
          {word.meanPitch > 0 && (
            <small>
              {Math.round(word.meanPitch)} Hz / {Math.round(word.pitchRange)} Hz
            </small>
          )}
        </span>
      ))}
    </div>
  );
}

function tokenizeTranscript(transcription: string): string[] {
  return (
    transcription.match(/[\u4e00-\u9fff]|[A-Za-z0-9']+/g)?.slice(0, 80) || []
  );
}

function ScoreCard({ label, value }: { label: ReactNode; value: string }) {
  return (
    <div className="voice-score-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ModelExampleCard({
  text,
  focusWord,
}: {
  text: string;
  focusWord?: string;
}) {
  const exampleText = text.trim() || "今天下雨，所以我帶傘。";

  const playExample = () => {
    if (!("speechSynthesis" in window)) {
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(exampleText);
    utterance.lang = "zh-TW";
    utterance.rate = 0.82;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  };

  return (
    <section className="voice-model-example" aria-label="100 score example">
      <div>
        <span>
          <BiLabel zh="滿分示範" pinyin="Mǎnfēn shìfàn" en="100-score example" />
        </span>
        <h2>
          <BiLabel zh="先聽，再用你的聲音跟著說" pinyin="Xiān tīng, zài yòng nǐ de shēngyīn gēnzhe shuō" en="Listen, then copy with your voice" />
        </h2>
        <p lang="zh-Hant">{exampleText}</p>
      </div>
      <div className="voice-model-example-actions">
        {focusWord && (
          <em>
            <BiLabel zh={`先練：${focusWord}`} en={`Focus first: ${focusWord}`} />
          </em>
        )}
        <button type="button" onClick={playExample}>
          <BiLabel zh="播放示範" pinyin="Bòfàng shìfàn" en="Play example" />
        </button>
      </div>
    </section>
  );
}

function StudentFeedbackCards({
  toneAccuracy,
  fluencyScore,
  speechRate,
  wordProsody,
}: {
  toneAccuracy: number;
  fluencyScore: number;
  speechRate: number;
  wordProsody: WordProsody[];
}) {
  const focus = getToneFocusItems(wordProsody)[0];
  const strength = studentStrength(toneAccuracy, fluencyScore);
  const fix = studentFix(toneAccuracy, fluencyScore, speechRate, focus);
  const next = studentNextStep(speechRate, focus);

  return (
    <section className="voice-student-feedback" aria-label="Student feedback">
      <div className="voice-student-feedback-card good">
        <span>
          <BiLabel zh="優點" pinyin="Yōudiǎn" en="Good" />
        </span>
        <strong>
          <BiText zh={strength.zh} pinyin={strength.pinyin} en={strength.en} />
        </strong>
      </div>
      <div className="voice-student-feedback-card fix">
        <span>
          <BiLabel zh="待改進" pinyin="Dài gǎijìn" en="Fix" />
        </span>
        <strong>
          <BiText zh={fix.zh} pinyin={fix.pinyin} en={fix.en} />
        </strong>
      </div>
      <div className="voice-student-feedback-card next">
        <span>
          <BiLabel zh="下次試試" pinyin="Xiàcì shìshi" en="Next try" />
        </span>
        <strong>
          <BiText zh={next.zh} pinyin={next.pinyin} en={next.en} />
        </strong>
      </div>
    </section>
  );
}

interface BilingualLine {
  zh: string;
  pinyin?: string;
  en: string;
}

function studentStrength(toneAccuracy: number, fluencyScore: number): BilingualLine {
  if (toneAccuracy >= 80 && fluencyScore >= 75) {
    return {
      zh: "你的聲調和節奏已經夠清楚，可以試著說更長的句子了。",
      pinyin: "Nǐ de shēngdiào hé jiézòu yǐjīng gòu qīngchǔ, kěyǐ shìzhe shuō gèng cháng de jùzi le.",
      en: "Your tones and rhythm are clear enough to build a longer sentence.",
    };
  }
  if (toneAccuracy >= 75) {
    return {
      zh: "你的聲調形狀聽得出來。",
      pinyin: "Nǐ de shēngdiào xíngzhuàng tīng de chūlái.",
      en: "Your tone shape is recognizable.",
    };
  }
  if (fluencyScore >= 75) {
    return {
      zh: "你說話的節奏很穩定。",
      pinyin: "Nǐ shuōhuà de jiézòu hěn wěndìng.",
      en: "Your speaking rhythm is steady.",
    };
  }
  return {
    zh: "你完成了一次錄音，現在來改進一個小地方吧。",
    pinyin: "Nǐ wánchéng le yí cì lùyīn, xiànzài lái gǎijìn yí gè xiǎo dìfāng ba.",
    en: "You completed a recording. Now improve one small part.",
  };
}

function studentFix(
  toneAccuracy: number,
  fluencyScore: number,
  speechRate: number,
  focus?: WordProsody,
): BilingualLine {
  if (speechRate > 6.5) {
    return {
      zh: "說慢一點，讓每個聲調都有時間發完整。",
      pinyin: "Shuō màn yìdiǎn, ràng měi gè shēngdiào dōu yǒu shíjiān fā wánzhěng.",
      en: "Slow down so each Mandarin tone has time to finish.",
    };
  }
  if (toneAccuracy < 65 && focus) {
    return {
      zh: `把「${focus.token}」的聲調變化說得更清楚一點。`,
      en: `Make the tone movement clearer on "${focus.token}".`,
    };
  }
  if (fluencyScore < 60) {
    return {
      zh: "把字跟字連得更順一點，不要每個字中間都停頓。",
      pinyin: "Bǎ zì gēn zì lián de gèng shùn yìdiǎn, búyào měi gè zì zhōngjiān dōu tíngdùn.",
      en: "Connect the words more smoothly without stopping between every character.",
    };
  }
  if (focus) {
    return {
      zh: `先把「${focus.token}」練熟一點。`,
      en: `Polish "${focus.token}" first.`,
    };
  }
  return {
    zh: "句子保持簡短，把每個聲調都說清楚。",
    pinyin: "Jùzi bǎochí jiǎnduǎn, bǎ měi gè shēngdiào dōu shuō qīngchǔ.",
    en: "Keep the sentence short and make every tone clear.",
  };
}

function studentNextStep(speechRate: number, focus?: WordProsody): BilingualLine {
  if (focus) {
    return {
      zh: `把「${focus.token}」說三次，再說一次完整的句子。`,
      en: `Say "${focus.token}" three times, then repeat the full sentence.`,
    };
  }
  if (speechRate < 2.5) {
    return {
      zh: "再說一次同一句話，試著說得更順一點。",
      pinyin: "Zài shuō yí cì tóng yí jù huà, shìzhe shuō de gèng shùn yìdiǎn.",
      en: "Try the same sentence again with a little more flow.",
    };
  }
  return {
    zh: "再錄一次，試著保持一樣清楚的節奏。",
    pinyin: "Zài lù yí cì, shìzhe bǎochí yíyàng qīngchǔ de jiézòu.",
    en: "Record again and try to match the same clear rhythm.",
  };
}

function getToneFocusItems(items: WordProsody[]): WordProsody[] {
  const scored = items.map((item) => ({
    item,
    score:
      (item.contour_shape === "variable" ? 3 : 0) +
      (item.pitch_range < 15 ? 2 : 0) +
      (item.pitch_range > 95 ? 1 : 0),
  }));

  const focus = scored
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.item)
    .slice(0, 4);

  return focus.length > 0 ? focus : items.slice(0, 4);
}

function FeedbackBlock({
  title,
  score,
  text,
}: {
  title: ReactNode;
  score: number;
  text: string;
}) {
  return (
    <div className="feedback-block">
      <strong>
        {title} · {Math.round(score)}/100
      </strong>
      <p>{text}</p>
    </div>
  );
}

function formatContourShape(shape: string): { zh: string; en: string } {
  const labels: Record<string, { zh: string; en: string }> = {
    dip: { zh: "凹型", en: "Dipping" },
    falling: { zh: "下降", en: "Falling" },
    level: { zh: "平", en: "Level" },
    rising: { zh: "上升", en: "Rising" },
    variable: { zh: "不穩定", en: "Variable" },
  };
  return labels[shape] || labels.variable;
}

async function readErrorResponse(response: Response): Promise<{ detail?: string }> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

function getBackendUrl(): string {
  if (BACKEND_URL) {
    return BACKEND_URL;
  }

  throw new Error(
    "語音測試需要正式部署的後端。請部署 FastAPI 後端並設定 VITE_BACKEND_URL。 Voice testing needs a deployed backend in production. Deploy the FastAPI backend and set VITE_BACKEND_URL.",
  );
}

function formatBackendError(error: unknown, backendUrl: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const networkFailures = ["Failed to fetch", "NetworkError", "Load failed"];

  if (networkFailures.some((failure) => message.includes(failure))) {
    return `無法連線到語音分析伺服器 (${backendUrl})，請先啟動 FastAPI 後端（8000 埠），再試一次。 Cannot reach the speech analysis backend at ${backendUrl}. Start the FastAPI backend on port 8000, then try again.`;
  }

  return message || "語音分析發生錯誤。 Voice analysis error occurred.";
}
