import { useEffect, useRef, useState } from "react";
import PitchChart from "../PitchChart";
import "./StoryRecorder.css";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

type SpeechModel = "webspeech" | "openai" | "gemini";

interface Topic {
  id: string;
  name: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

interface PraatMetrics {
  pitch_contour: Array<[number, number]>;
  detected_tone: number;
  tone_accuracy: number;
  formants: Record<string, number>;
  speech_rate: number;
  fluency_score: number;
  pitch_statistics: Record<string, number>;
  feedback: string;
  ai_feedback?: LanguageFeedback;
}

interface LanguageFeedback {
  provider: string;
  fluency: {
    score: number;
    feedback: string;
  };
  grammar: {
    score: number;
    feedback: string;
    corrections: string[];
  };
  vocabulary: {
    score: number;
    feedback: string;
    suggestions: string[];
  };
  improved_version: string;
  practice_prompt: string;
}

interface TranscriptionItem {
  text: string;
  timestamp: string;
  model: SpeechModel;
}

interface StoryRecorderProps {
  topic: Topic;
  selectedImage: string;
  selectedImageIndex: number;
  onImageSelect: (index: number) => void;
  onImageChange: (image: string) => void;
  onAddRecord: (record: {
    id: string;
    audioBlob: Blob;
    timestamp: string;
    duration: number;
    transcription: string;
    model: SpeechModel;
    topicId: string;
    praatMetrics: PraatMetrics;
  }) => void;
}

export default function StoryRecorder({
  topic,
  selectedImage,
  selectedImageIndex,
  onImageSelect,
  onImageChange,
  onAddRecord,
}: StoryRecorderProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [transcriptions, setTranscriptions] = useState<TranscriptionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<SpeechModel>("webspeech");
  const [silenceDuration, setSilenceDuration] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [praatMetrics, setPraatMetrics] = useState<PraatMetrics | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const durationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordingStartRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const currentTranscriptRef = useRef("");

  useEffect(() => {
    return () => {
      stopTracks();
      clearTimers();
    };
  }, []);

  const clearTimers = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
      durationIntervalRef.current = null;
    }
  };

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const startRecording = async () => {
    try {
      setError(null);
      setPraatMetrics(null);
      currentTranscriptRef.current = "";
      recordingStartRef.current = Date.now();
      setRecordingDuration(0);
      setSilenceDuration(0);
      lastSpeechAtRef.current = Date.now();

      if (selectedModel === "webspeech") {
        await startWebSpeechRecording();
      } else {
        await startAudioRecording(async (audioBlob) => {
          await transcribeAudio(audioBlob);
        });
        setIsRecording(true);
      }

      durationIntervalRef.current = setInterval(() => {
        setRecordingDuration(
          Math.floor((Date.now() - recordingStartRef.current) / 1000),
        );
      }, 250);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to access microphone. Please check permissions.",
      );
      setIsRecording(false);
      clearTimers();
      stopTracks();
    }
  };

  const startWebSpeechRecording = async () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      throw new Error(
        "Web Speech API is not supported in this browser. Use Chrome, Edge, or Safari.",
      );
    }

    await startAudioRecording(async (audioBlob) => {
      await analyzeSpeechAudio(audioBlob, currentTranscriptRef.current.trim());
    });

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "zh-TW";

    recognition.onstart = () => {
      setIsRecording(true);
      startSilenceDetection(recognition);
    };

    recognition.onresult = (event: any) => {
      let heardSpeech = false;
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          currentTranscriptRef.current =
            `${currentTranscriptRef.current} ${transcript}`.trim();
          addTranscription(transcript);
          heardSpeech = true;
        } else if (transcript.trim()) {
          heardSpeech = true;
        }
      }

      if (heardSpeech) {
        lastSpeechAtRef.current = Date.now();
        setSilenceDuration(0);
      }
    };

    recognition.onerror = (event: any) => {
      setError(`Speech recognition error: ${event.error}`);
    };

    recognition.onend = () => {
      setIsRecording(false);
      clearTimers();
      stopAudioRecording();
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const startSilenceDetection = (recognition: any) => {
    const silenceThreshold = 7000;
    const checkInterval = 250;

    const checkSilence = () => {
      const currentSilenceTime = Date.now() - lastSpeechAtRef.current;
      setSilenceDuration(Math.floor(currentSilenceTime / 1000));

      if (currentSilenceTime >= silenceThreshold) {
        recognition.stop();
      } else {
        silenceTimerRef.current = setTimeout(checkSilence, checkInterval);
      }
    };

    silenceTimerRef.current = setTimeout(checkSilence, checkInterval);
  };

  const startAudioRecording = async (onStop: (audioBlob: Blob) => Promise<void>) => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const preferredType = MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "";
    const mediaRecorder = new MediaRecorder(
      stream,
      preferredType ? { mimeType: preferredType } : undefined,
    );
    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunksRef.current.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const rawBlob = new Blob(audioChunksRef.current, {
        type: mediaRecorder.mimeType || "audio/webm",
      });
      try {
        await onStop(rawBlob);
      } finally {
        stopTracks();
      }
    };

    mediaRecorder.start();
  };

  const stopAudioRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  };

  const stopRecording = () => {
    if (selectedModel === "webspeech") {
      recognitionRef.current?.stop();
    } else {
      stopAudioRecording();
      setIsRecording(false);
    }

    clearTimers();
    setSilenceDuration(0);
  };

  const transcribeAudio = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    try {
      const wavBlob = await convertBlobToWav(audioBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "speech.wav");
      formData.append("model", selectedModel);

      const response = await fetch(`${BACKEND_URL}/api/transcribe`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Transcription failed");
      }

      const data = await response.json();
      addTranscription(data.text);
      currentTranscriptRef.current = data.text;
      await analyzeSpeechAudio(wavBlob, data.text);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Transcription error occurred",
      );
    } finally {
      setIsTranscribing(false);
    }
  };

  const analyzeSpeechAudio = async (audioBlob: Blob, transcription: string) => {
    setIsAnalyzing(true);
    try {
      const wavBlob = await convertBlobToWav(audioBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "speech.wav");
      formData.append("transcription", transcription);

      const response = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Praat analysis failed");
      }

      const metrics = (await response.json()) as PraatMetrics;
      setPraatMetrics(metrics);

      onAddRecord({
        id: `audio-${Date.now()}`,
        audioBlob: wavBlob,
        timestamp: new Date().toLocaleString(),
        duration: Math.max(
          1,
          Math.floor((Date.now() - recordingStartRef.current) / 1000),
        ),
        transcription,
        model: selectedModel,
        topicId: topic.id,
        praatMetrics: metrics,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Speech analysis error occurred",
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const addTranscription = (text: string) => {
    if (!text.trim()) return;

    setTranscriptions((prev) => [
      ...prev,
      {
        text,
        timestamp: new Date().toLocaleTimeString(),
        model: selectedModel,
      },
    ]);
  };

  const getToneName = (tone: number): string => {
    const toneNames: Record<number, string> = {
      1: "Tone 1 - High Level (媽 ma1)",
      2: "Tone 2 - Rising (麻 ma2)",
      3: "Tone 3 - Falling-Rising (馬 ma3)",
      4: "Tone 4 - Falling (罵 ma4)",
    };
    return toneNames[tone] || "No clear tone";
  };

  const isBusy = isRecording || isTranscribing || isAnalyzing;

  return (
    <div className="story-recorder">
      <div className="recorder-header">
        <p className="eyebrow">Mandarin speech lab</p>
        <h1>{topic.name} Story Practice</h1>
        {selectedImage && (
          <div className="story-image-preview">
            <img src={selectedImage} alt="Selected story prompt" />
          </div>
        )}
      </div>

      <div className="topic-images-section">
        <h3>Choose a visual prompt</h3>
        <div className="topic-images-grid">
          {topic.images.map((image, index) => (
            <div key={image} className="topic-image-wrapper">
              <button
                type="button"
                className={`topic-image-card ${
                  selectedImageIndex === index ? "selected" : ""
                }`}
                onClick={() => {
                  onImageChange(image);
                  onImageSelect(index);
                }}
              >
                <img src={image} alt={`Story prompt ${index + 1}`} />
              </button>
              <div className="image-vocabulary">
                {topic.vocabulary[index]?.join(" / ")}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="model-selector">
        <label htmlFor="model">Speech source</label>
        <select
          id="model"
          value={selectedModel}
          onChange={(event) => setSelectedModel(event.target.value as SpeechModel)}
          disabled={isBusy}
        >
          <option value="webspeech">Web Speech API and Praat analysis</option>
          <option value="openai">OpenAI transcription and Praat analysis</option>
          <option value="gemini">Gemini transcription and Praat analysis</option>
        </select>
      </div>

      <div className="controls">
        <button
          type="button"
          onClick={startRecording}
          disabled={isBusy}
          className="btn btn-primary"
        >
          {isRecording ? "Recording..." : "Start Recording"}
        </button>

        <button
          type="button"
          onClick={stopRecording}
          disabled={!isRecording}
          className="btn btn-danger"
        >
          Stop and Analyze
        </button>
      </div>

      {isRecording && (
        <div className="recording-info">
          <p>Recording: {recordingDuration}s</p>
          {selectedModel === "webspeech" && (
            <p>Silence: {silenceDuration}s / 7s auto-stop</p>
          )}
        </div>
      )}

      {(isTranscribing || isAnalyzing) && (
        <p className="loading">
          {isTranscribing ? "Transcribing speech..." : "Running Praat analysis..."}
        </p>
      )}

      {error && <p className="error">{error}</p>}

      {praatMetrics && (
        <section className="analysis-panel">
          <div className="analysis-heading">
            <p className="eyebrow">Praat result</p>
            <h2>Pronunciation Analysis</h2>
          </div>

          <div className="metrics-section">
            <div className="metric-card tone-card">
              <div className="metric-label">Detected Tone</div>
              <div className="metric-value compact">
                {getToneName(praatMetrics.detected_tone)}
              </div>
            </div>

            <div className="metric-card accuracy-card">
              <div className="metric-label">Tone Accuracy</div>
              <div className="metric-value">
                {Math.round(praatMetrics.tone_accuracy)}%
              </div>
              <div className="metric-bar">
                <div
                  className="metric-fill"
                  style={{ width: `${praatMetrics.tone_accuracy}%` }}
                />
              </div>
            </div>

            <div className="metric-card fluency-card">
              <div className="metric-label">Fluency</div>
              <div className="metric-value">
                {Math.round(praatMetrics.fluency_score)}/100
              </div>
              <div className="metric-bar">
                <div
                  className="metric-fill"
                  style={{ width: `${praatMetrics.fluency_score}%` }}
                />
              </div>
            </div>

            <div className="metric-card rate-card">
              <div className="metric-label">Speech Rate</div>
              <div className="metric-value">
                {praatMetrics.speech_rate.toFixed(1)}
              </div>
              <div className="metric-subtext">syllables/sec</div>
            </div>

            <div className="metric-card formants-card">
              <div className="metric-label">Formants</div>
              <div className="formants-grid">
                {["F1", "F2", "F3"].map((formant) => (
                  <div className="formant" key={formant}>
                    <span>{formant}</span>
                    <strong>
                      {Math.round(praatMetrics.formants[formant] || 0)} Hz
                    </strong>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="chart-section">
            <PitchChart
              pitchContour={praatMetrics.pitch_contour}
              detectedTone={praatMetrics.detected_tone}
            />
          </div>

          <div className="feedback-section">
            <h3>Coaching Feedback</h3>
            <p>{praatMetrics.feedback}</p>
          </div>

          {praatMetrics.ai_feedback && (
            <div className="ai-feedback-section">
              <div className="ai-feedback-header">
                <p className="eyebrow">AI language coach</p>
                <h3>Fluency, Grammar, and Vocabulary</h3>
                <span>{praatMetrics.ai_feedback.provider}</span>
              </div>

              <div className="ai-feedback-grid">
                <FeedbackCard
                  title="Fluency"
                  score={praatMetrics.ai_feedback.fluency.score}
                  feedback={praatMetrics.ai_feedback.fluency.feedback}
                />
                <FeedbackCard
                  title="Grammar"
                  score={praatMetrics.ai_feedback.grammar.score}
                  feedback={praatMetrics.ai_feedback.grammar.feedback}
                  items={praatMetrics.ai_feedback.grammar.corrections}
                />
                <FeedbackCard
                  title="Vocabulary"
                  score={praatMetrics.ai_feedback.vocabulary.score}
                  feedback={praatMetrics.ai_feedback.vocabulary.feedback}
                  items={praatMetrics.ai_feedback.vocabulary.suggestions}
                />
              </div>

              {praatMetrics.ai_feedback.improved_version && (
                <div className="ai-example">
                  <strong>Improved version</strong>
                  <p>{praatMetrics.ai_feedback.improved_version}</p>
                </div>
              )}

              <div className="ai-example">
                <strong>Practice next</strong>
                <p>{praatMetrics.ai_feedback.practice_prompt}</p>
              </div>
            </div>
          )}
        </section>
      )}

      <div className="transcriptions">
        <h2>Transcriptions</h2>
        {transcriptions.length === 0 ? (
          <p className="empty">No transcriptions yet. Start recording.</p>
        ) : (
          transcriptions.map((item) => (
            <div
              key={`${item.timestamp}-${item.text}`}
              className="transcription-item"
            >
              <div className="item-header">
                <span className="time">{item.timestamp}</span>
                <span className="model-badge">{item.model.toUpperCase()}</span>
              </div>
              <p>{item.text}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function FeedbackCard({
  title,
  score,
  feedback,
  items = [],
}: {
  title: string;
  score: number;
  feedback: string;
  items?: string[];
}) {
  return (
    <div className="ai-feedback-card">
      <div className="ai-feedback-score">
        <span>{title}</span>
        <strong>{Math.round(score)}/100</strong>
      </div>
      <p>{feedback}</p>
      {items.length > 0 && (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

async function convertBlobToWav(blob: Blob): Promise<Blob> {
  if (blob.type === "audio/wav" || blob.type === "audio/wave") {
    return blob;
  }

  const audioContext = new AudioContext();
  try {
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    return encodeWav(audioBuffer);
  } finally {
    await audioContext.close();
  }
}

function encodeWav(audioBuffer: AudioBuffer): Blob {
  const numberOfChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const samples = audioBuffer.length;
  const bytesPerSample = 2;
  const blockAlign = numberOfChannels * bytesPerSample;
  const buffer = new ArrayBuffer(44 + samples * blockAlign);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples * blockAlign, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numberOfChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, samples * blockAlign, true);

  let offset = 44;
  for (let sampleIndex = 0; sampleIndex < samples; sampleIndex += 1) {
    for (let channel = 0; channel < numberOfChannels; channel += 1) {
      const sample = audioBuffer.getChannelData(channel)[sampleIndex];
      const clamped = Math.max(-1, Math.min(1, sample));
      view.setInt16(
        offset,
        clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff,
        true,
      );
      offset += bytesPerSample;
    }
  }

  return new Blob([view], { type: "audio/wav" });
}

function writeString(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}
