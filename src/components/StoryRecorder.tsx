import { useState, useRef, useEffect } from "react";
import PitchChart from "../PitchChart";
import "./StoryRecorder.css";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

interface Topic {
  id: string;
  name: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

interface StoryRecorderProps {
  topic: Topic;
  selectedImage: string;
  selectedImageIndex: number;
  onImageSelect: (index: number) => void;
  onImageChange: (image: string) => void;
  onAddRecord: (record: any) => void;
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
  const [transcriptions, setTranscriptions] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<
    "webspeech" | "openai" | "gemini"
  >("webspeech");
  const [silenceDuration, setSilenceDuration] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [praatMetrics, setPraatMetrics] = useState<any>(null);
  const [showAudioHistory, setShowAudioHistory] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const recordingStartTimeRef = useRef<number>(0);
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const recordingStartRef = useRef<number>(0);

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
    };
  }, []);

  const startRecording = async () => {
    try {
      setError(null);
      recordingStartRef.current = Date.now();

      if (selectedModel === "webspeech") {
        startWebSpeechRecording();
      } else {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        streamRef.current = stream;

        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;
        audioChunksRef.current = [];

        mediaRecorder.ondataavailable = (event) => {
          audioChunksRef.current.push(event.data);
        };

        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, {
            type: "audio/wav",
          });
          await transcribeAudio(audioBlob);
        };

        mediaRecorder.start();
        setIsRecording(true);
      }
    } catch (err) {
      setError("Failed to access microphone. Please check permissions.");
    }
  };

  const startWebSpeechRecording = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError(
        "Web Speech API not supported in this browser. Use Chrome, Edge, or Safari.",
      );
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "zh-TW";

    recognition.onstart = () => {
      setIsRecording(true);
      recordingStartTimeRef.current = Date.now();
      setSilenceDuration(0);
      setRecordingDuration(0);

      startAudioRecording();

      durationIntervalRef.current = setInterval(() => {
        const elapsed = Math.floor(
          (Date.now() - recordingStartTimeRef.current) / 1000,
        );
        setRecordingDuration(elapsed);
      }, 100);
    };

    recognition.onresult = (event: any) => {
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          addTranscription(transcript);
        } else {
          interimTranscript += transcript;
        }
      }

      if (interimTranscript) {
        setSilenceDuration(0);
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
        }
      }
    };

    recognition.onerror = (event: any) => {
      setError(`Speech recognition error: ${event.error}`);
    };

    recognition.onend = () => {
      setIsRecording(false);
      setSilenceDuration(0);
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
      stopAudioRecording();
    };

    recognitionRef.current = recognition;
    recognition.start();
    startSilenceDetection(recognition);
  };

  const startSilenceDetection = (recognition: any) => {
    let currentSilenceTime = 0;
    const SILENCE_THRESHOLD = 7000;
    const CHECK_INTERVAL = 100;

    const checkSilence = () => {
      currentSilenceTime += CHECK_INTERVAL;
      setSilenceDuration(Math.floor(currentSilenceTime / 1000));

      if (currentSilenceTime >= SILENCE_THRESHOLD && isRecording) {
        recognition.stop();
        setIsRecording(false);
      } else {
        silenceTimerRef.current = setTimeout(checkSilence, CHECK_INTERVAL);
      }
    };

    silenceTimerRef.current = setTimeout(checkSilence, CHECK_INTERVAL);
  };

  const startAudioRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      streamRef.current = stream;

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });
        const duration = recordingDuration;
        const lastTranscription = transcriptions[transcriptions.length - 1];
        await analyzeSpeechAudio(
          audioBlob,
          duration,
          lastTranscription?.text || "",
        );
      };

      mediaRecorder.start();
    } catch (err) {
      console.error("Audio recording error:", err);
    }
  };

  const stopAudioRecording = () => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }
  };

  const stopRecording = () => {
    if (selectedModel === "webspeech") {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        setIsRecording(false);
      }
    } else {
      if (mediaRecorderRef.current && isRecording) {
        mediaRecorderRef.current.stop();
        setIsRecording(false);

        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
        }
      }
    }

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
    }
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
    }
    setSilenceDuration(0);
    setRecordingDuration(0);
  };

  const transcribeAudio = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    try {
      const formData = new FormData();
      formData.append("file", audioBlob, "audio.wav");
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

      const duration = Math.floor(
        (Date.now() - recordingStartRef.current) / 1000,
      );
      await analyzeSpeechAudio(audioBlob, duration, data.text);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Transcription error occurred",
      );
    } finally {
      setIsTranscribing(false);
    }
  };

  const analyzeSpeechAudio = async (
    audioBlob: Blob,
    duration: number,
    transcription: string,
  ) => {
    setIsAnalyzing(true);
    try {
      const formData = new FormData();
      formData.append("file", audioBlob, "audio.wav");

      const response = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Analysis failed");
      }

      const metrics = await response.json();
      setPraatMetrics(metrics);

      onAddRecord({
        id: `audio-${Date.now()}`,
        audioBlob,
        timestamp: new Date().toLocaleString(),
        duration,
        transcription,
        model: selectedModel,
        topicId: topic.id,
        praatMetrics: metrics,
      });
    } catch (err) {
      console.error("Error analyzing speech:", err);
      setError(
        err instanceof Error ? err.message : "Speech analysis error occurred",
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const addTranscription = (text: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setTranscriptions((prev) => [
      ...prev,
      {
        text,
        timestamp,
        model: selectedModel,
      },
    ]);
  };

  const getToneName = (tone: number): string => {
    const toneNames: Record<number, string> = {
      1: "High Level (妈 mā)",
      2: "Rising (麻 má)",
      3: "Falling-Rising (马 mǎ)",
      4: "Falling (骂 mà)",
    };
    return toneNames[tone] || "Unknown";
  };

  return (
    <div className="story-recorder">
      <div className="recorder-header">
        <h1>🎤 {topic.name} - Create Your Story</h1>
        {selectedImage && (
          <div className="story-image-preview">
            <img src={selectedImage} alt="Selected for story" />
          </div>
        )}
      </div>

      <div className="topic-images-section">
        <h3>Choose Your Story Image:</h3>
        <div className="topic-images-grid">
          {topic.images.map((image, index) => (
            <div key={index} className="topic-image-wrapper">
              <div
                className={`topic-image-card ${
                  selectedImageIndex === index ? "selected" : ""
                }`}
                onClick={() => {
                  onImageChange(image);
                  onImageSelect(index);
                }}
              >
                <img src={image} alt={`Story option ${index + 1}`} />
              </div>
              <div className="image-vocabulary">
                {topic.vocabulary[index]?.join(" / ")}
              </div>
            </div>
          ))}
        </div>
      </div>

      {praatMetrics && (
        <div className="metrics-section">
          <div className="metric-card tone-card">
            <div className="metric-label">🎯 Detected Tone</div>
            <div className="metric-value">
              {getToneName(praatMetrics.detected_tone)}
            </div>
          </div>

          <div className="metric-card accuracy-card">
            <div className="metric-label">📊 Tone Accuracy</div>
            <div className="metric-value">
              {Math.round(praatMetrics.tone_accuracy)}%
            </div>
            <div className="metric-bar">
              <div
                className="metric-fill"
                style={{ width: `${praatMetrics.tone_accuracy}%` }}
              ></div>
            </div>
          </div>

          <div className="metric-card fluency-card">
            <div className="metric-label">💬 Fluency</div>
            <div className="metric-value">
              {Math.round(praatMetrics.fluency_score)}/100
            </div>
            <div className="metric-bar">
              <div
                className="metric-fill"
                style={{ width: `${praatMetrics.fluency_score}%` }}
              ></div>
            </div>
          </div>

          <div className="metric-card rate-card">
            <div className="metric-label">⚡ Speech Rate</div>
            <div className="metric-value">
              {praatMetrics.speech_rate.toFixed(1)}
            </div>
            <div className="metric-subtext">syllables/sec</div>
          </div>

          <div className="metric-card formants-card">
            <div className="metric-label">🎵 Formants</div>
            <div className="formants-grid">
              <div className="formant">
                <span>F1:</span>
                <strong>{Math.round(praatMetrics.formants.F1 || 0)} Hz</strong>
              </div>
              <div className="formant">
                <span>F2:</span>
                <strong>{Math.round(praatMetrics.formants.F2 || 0)} Hz</strong>
              </div>
              <div className="formant">
                <span>F3:</span>
                <strong>{Math.round(praatMetrics.formants.F3 || 0)} Hz</strong>
              </div>
            </div>
          </div>
        </div>
      )}

      {praatMetrics && praatMetrics.pitch_contour && (
        <div className="chart-section">
          <PitchChart
            pitchContour={praatMetrics.pitch_contour}
            detectedTone={praatMetrics.detected_tone}
          />
        </div>
      )}

      {praatMetrics && (
        <div className="feedback-section">
          <h3>💡 Feedback</h3>
          <p>{praatMetrics.feedback}</p>
        </div>
      )}

      <div className="model-selector">
        <label htmlFor="model">Select Model:</label>
        <select
          id="model"
          value={selectedModel}
          onChange={(e) =>
            setSelectedModel(
              e.target.value as "webspeech" | "openai" | "gemini",
            )
          }
          disabled={isRecording || isTranscribing || isAnalyzing}
        >
          <option value="webspeech">🌐 Web Speech API (Free)</option>
          <option value="openai">🤖 OpenAI Whisper</option>
          <option value="gemini">✨ Google Gemini</option>
        </select>
      </div>

      <div className="controls">
        <button
          onClick={startRecording}
          disabled={isRecording || isTranscribing || isAnalyzing}
          className="btn btn-primary"
        >
          {isRecording ? "🔴 Recording..." : "Start Recording"}
        </button>

        <button
          onClick={stopRecording}
          disabled={!isRecording}
          className="btn btn-danger"
        >
          Stop Recording
        </button>
      </div>

      {isRecording && selectedModel === "webspeech" && (
        <div className="recording-info">
          <p>⏱️ Recording: {recordingDuration}s</p>
          <p>🔇 Silence: {silenceDuration}s / 7s (auto-stop)</p>
        </div>
      )}

      {(isTranscribing || isAnalyzing) && (
        <p className="loading">
          🔄 {isTranscribing ? "Transcribing" : "Analyzing"} audio...
        </p>
      )}

      {error && <p className="error">❌ {error}</p>}

      <div className="transcriptions">
        <h2>Transcriptions</h2>
        {transcriptions.length === 0 ? (
          <p className="empty">No transcriptions yet. Start recording!</p>
        ) : (
          transcriptions.map((item, idx) => (
            <div key={idx} className="transcription-item">
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
