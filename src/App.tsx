import { useState, useRef, useEffect } from "react";
import TopicSelector from "./TopicSelector";

type Model = "openai" | "gemini" | "webspeech";

interface TranscriptionResult {
  text: string;
  timestamp: string;
  model: Model;
  audioBlob?: Blob;
  duration?: number;
}

interface AudioRecord {
  id: string;
  audioBlob: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  model: Model;
}

interface Topic {
  id: string;
  name: string;
  description: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

export default function App() {
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null);
  const [selectedImage, setSelectedImage] = useState<string>("");
  const [selectedImageIndex, setSelectedImageIndex] = useState<number>(0);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcriptions, setTranscriptions] = useState<TranscriptionResult[]>(
    [],
  );
  const [audioRecords, setAudioRecords] = useState<AudioRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<Model>("webspeech");
  const [silenceDuration, setSilenceDuration] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [showAudioHistory, setShowAudioHistory] = useState(false);
  const [score, setScore] = useState<number>(0);
  const [feedback, setFeedback] = useState<string>("");
  const [ranking, setRanking] = useState<string>("Beginner");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const recordingStartTimeRef = useRef<number>(0);
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const currentAudioBlobRef = useRef<Blob | null>(null);
  const recordingStartRef = useRef<number>(0);

  // Load persisted audio records from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem("audioRecords");
    if (stored) {
      try {
        const recordsData = JSON.parse(stored);
        // Note: Blobs are not stored in localStorage, only metadata
        // We'll need to rebuild the records from what's available
        setAudioRecords(
          recordsData.map((data: any) => ({
            ...data,
            audioBlob: new Blob([], { type: "audio/webm" }), // Empty blob as placeholder
          })),
        );
      } catch (e) {
        console.error("Failed to load audio records:", e);
      }
    }
  }, []);

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
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
          currentAudioBlobRef.current = audioBlob;
          await transcribeAudio(audioBlob);
        };

        mediaRecorder.start();
        setIsRecording(true);
      }
    } catch (err) {
      setError("Failed to access microphone. Please check permissions.");
      console.error(err);
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

      // Start recording audio in parallel
      startAudioRecording();

      // Start duration timer
      durationIntervalRef.current = setInterval(() => {
        const elapsed = Math.floor(
          (Date.now() - recordingStartTimeRef.current) / 1000,
        );
        setRecordingDuration(elapsed);
      }, 100);
    };

    recognition.onresult = (event: any) => {
      let interimTranscript = "";
      let hasNewFinal = false;

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          addTranscription(transcript, "webspeech");
          hasNewFinal = true;
        } else {
          interimTranscript += transcript;
        }
      }

      // Reset silence timer when speech is detected
      if (hasNewFinal || interimTranscript) {
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

    // Start silence detection timer
    startSilenceDetection(recognition);
  };

  const startSilenceDetection = (recognition: any) => {
    let currentSilenceTime = 0;
    const SILENCE_THRESHOLD = 7000; // 7 seconds
    const CHECK_INTERVAL = 100; // Check every 100ms

    const checkSilence = () => {
      currentSilenceTime += CHECK_INTERVAL;
      setSilenceDuration(Math.floor(currentSilenceTime / 1000));

      if (currentSilenceTime >= SILENCE_THRESHOLD && isRecording) {
        recognition.stop();
        setIsRecording(false);
      } else if (currentSilenceTime < SILENCE_THRESHOLD) {
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

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });
        const duration = recordingDuration;
        const lastTranscription = transcriptions[transcriptions.length - 1];
        saveAudioRecord(
          audioBlob,
          duration,
          lastTranscription?.text || "",
          "webspeech",
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

  const saveAudioRecord = (
    audioBlob: Blob,
    duration: number,
    transcription: string = "",
    model: Model = "webspeech",
  ) => {
    const record: AudioRecord = {
      id: `audio-${Date.now()}`,
      audioBlob,
      timestamp: new Date().toLocaleString(),
      duration,
      transcription,
      model,
    };

    setAudioRecords((prev) => [record, ...prev]);

    // Save to localStorage
    const audioData = {
      id: record.id,
      timestamp: record.timestamp,
      duration: record.duration,
      transcription: record.transcription,
      model: record.model,
    };
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    localStorage.setItem(
      "audioRecords",
      JSON.stringify([audioData, ...stored]),
    );
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

    // Clear timers
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
      const openaiKey = import.meta.env.VITE_OPENAI_API_KEY;
      const geminiKey = import.meta.env.VITE_GEMINI_API_KEY;

      if (selectedModel === "openai") {
        if (!openaiKey) {
          setError("OpenAI API key not configured. Check .env file.");
          setIsTranscribing(false);
          return;
        }
        await transcribeWithOpenAI(audioBlob, openaiKey);
      } else if (selectedModel === "gemini") {
        if (!geminiKey) {
          setError("Gemini API key not configured. Check .env file.");
          setIsTranscribing(false);
          return;
        }
        await transcribeWithGemini(audioBlob, geminiKey);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Transcription error occurred",
      );
    } finally {
      setIsTranscribing(false);
    }
  };

  const transcribeWithOpenAI = async (audioBlob: Blob, apiKey: string) => {
    const formData = new FormData();
    formData.append("file", audioBlob, "audio.wav");
    formData.append("model", "whisper-1");
    formData.append("language", "zh");

    const response = await fetch(
      "https://api.openai.com/v1/audio/transcriptions",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
        },
        body: formData,
      },
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(
        errorData.error?.message || "OpenAI transcription failed",
      );
    }

    const data = await response.json();
    addTranscription(data.text, "openai");

    // Save audio record with transcription
    const duration = Math.floor(
      (Date.now() - recordingStartRef.current) / 1000,
    );
    saveAudioRecord(audioBlob, duration, data.text, "openai");
  };

  const transcribeWithGemini = async (audioBlob: Blob, apiKey: string) => {
    const base64Audio = await blobToBase64(audioBlob);
    const mimeType = "audio/wav";

    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          contents: [
            {
              parts: [
                {
                  inline_data: {
                    mime_type: mimeType,
                    data: base64Audio,
                  },
                },
                {
                  text: "Please transcribe this audio to text. Only provide the transcription without any additional explanation.",
                },
              ],
            },
          ],
        }),
      },
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(
        errorData.error?.message || "Gemini transcription failed",
      );
    }

    const data = await response.json();
    const text =
      data.candidates?.[0]?.content?.parts?.[0]?.text || "Unable to transcribe";
    addTranscription(text, "gemini");

    // Save audio record with transcription
    const duration = Math.floor(
      (Date.now() - recordingStartRef.current) / 1000,
    );
    saveAudioRecord(audioBlob, duration, text, "gemini");
  };

  const blobToBase64 = (blob: Blob): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const result = reader.result as string;
        resolve(result.split(",")[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  };

  const addTranscription = (text: string, model: Model) => {
    const timestamp = new Date().toLocaleTimeString();
    setTranscriptions((prev) => [
      ...prev,
      {
        text,
        timestamp,
        model,
      },
    ]);

    // Calculate score and feedback based on transcription
    generateScoreAndFeedback(text);
  };

  const generateScoreAndFeedback = (text: string) => {
    // Calculate score based on text length and quality
    const wordCount = text.trim().split(/\s+/).length;
    const charCount = text.length;

    let calculatedScore = Math.min(100, Math.round((charCount / 5) * 10));
    calculatedScore = Math.min(100, calculatedScore + (wordCount > 10 ? 20 : 0));

    // Generate ranking based on score
    let newRanking = "Beginner";
    if (calculatedScore >= 80) newRanking = "Advanced";
    else if (calculatedScore >= 60) newRanking = "Intermediate";
    else if (calculatedScore >= 40) newRanking = "Developing";

    // Generate feedback
    let newFeedback = "Good start! ";
    if (wordCount > 30) newFeedback += "Great vocabulary usage! ";
    else if (wordCount > 20) newFeedback += "Nice work with your sentences! ";
    else if (wordCount > 10) newFeedback += "Good effort, try to speak more! ";
    else newFeedback += "Try to speak longer sentences! ";

    if (calculatedScore >= 80)
      newFeedback += "Your pronunciation is excellent! 🌟";
    else if (calculatedScore >= 60)
      newFeedback += "Keep practicing to improve fluency! 💪";
    else newFeedback += "Practice more to build confidence! 📖";

    setScore(calculatedScore);
    setFeedback(newFeedback);
    setRanking(newRanking);
  };

  const downloadAudio = (audioBlob: Blob, filename: string) => {
    const url = URL.createObjectURL(audioBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const deleteAudioRecord = (id: string) => {
    setAudioRecords((prev) => prev.filter((record) => record.id !== id));
    const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
    const updated = stored.filter((record: any) => record.id !== id);
    localStorage.setItem("audioRecords", JSON.stringify(updated));
  };

  return (
    <>
      {!selectedTopic ? (
        <TopicSelector
          onTopicSelect={(topic) => {
            setSelectedTopic(topic);
            setSelectedImage(topic.images[0]);
            setSelectedImageIndex(0);
          }}
        />
      ) : (
        <div className="container">
          <div className="story-header">
            <button
              onClick={() => {
                setSelectedTopic(null);
                setSelectedImage("");
                setSelectedImageIndex(0);
              }}
              className="btn-back"
            >
              ← Back to Topics
            </button>
            <h1>🎤 {selectedTopic.name} - Create Your Story</h1>
            {selectedImage && (
              <div className="story-image-preview">
                <img src={selectedImage} alt="Selected for story" />
              </div>
            )}
          </div>

          {/* Topic Images Grid */}
          <div className="topic-images-section">
            <h3>Choose Your Story Image:</h3>
            <div className="topic-images-grid">
              {selectedTopic.images.map((image, index) => (
                <div
                  key={index}
                  className="topic-image-wrapper"
                >
                  <div
                    className={`topic-image-card ${selectedImageIndex === index ? "selected" : ""}`}
                    onClick={() => {
                      setSelectedImage(image);
                      setSelectedImageIndex(index);
                    }}
                  >
                    <img src={image} alt={`Story option ${index + 1}`} />
                  </div>
                  <div className="image-vocabulary">
                    {selectedTopic.vocabulary[index]?.join(" / ")}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Score, Feedback, Ranking Cards */}
          <div className="metrics-section">
            <div className="metric-card score-card">
              <div className="metric-label">📊 Score</div>
              <div className="metric-value">{score}/100</div>
              <div className="metric-bar">
                <div className="metric-fill" style={{ width: `${score}%` }}></div>
              </div>
            </div>

            <div className="metric-card feedback-card">
              <div className="metric-label">💬 Feedback</div>
              <div className="metric-text">
                {feedback || "Start recording to get feedback"}
              </div>
            </div>

            <div className="metric-card ranking-card">
              <div className="metric-label">🏆 Ranking</div>
              <div className="metric-badge">{ranking}</div>
            </div>
          </div>

          <div className="model-selector">
            <label htmlFor="model">Select Model:</label>
            <select
              id="model"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value as Model)}
              disabled={isRecording || isTranscribing}
            >
              <option value="webspeech">🌐 Web Speech API (Free, Offline)</option>
              <option value="openai">🤖 OpenAI Whisper</option>
              <option value="gemini">✨ Google Gemini</option>
            </select>
          </div>

          <div className="controls">
            <button
              onClick={startRecording}
              disabled={isRecording || isTranscribing}
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

            <button
              onClick={() => setShowAudioHistory(!showAudioHistory)}
              className="btn btn-secondary"
            >
              📁 Audio History ({audioRecords.length})
            </button>
          </div>

          {isRecording && selectedModel === "webspeech" && (
            <div className="recording-info">
              <p>⏱️ Recording: {recordingDuration}s</p>
              <p>🔇 Silence: {silenceDuration}s / 7s (auto-stop)</p>
            </div>
          )}

          {isTranscribing && <p className="loading">🔄 Transcribing audio...</p>}
          {error && <p className="error">❌ {error}</p>}

          {showAudioHistory && (
            <div className="audio-history-panel">
              <h2>📁 Audio History (View & Manage Recordings)</h2>
              {audioRecords.length === 0 ? (
                <p className="empty">No recordings yet.</p>
              ) : (
                <div className="audio-list">
                  {audioRecords.map((record) => (
                    <div key={record.id} className="audio-item">
                      <div className="audio-info">
                        <div className="audio-header">
                          <span className="timestamp">{record.timestamp}</span>
                          <span className="duration">⏱️ {record.duration}s</span>
                          <span className="model-badge">
                            {record.model === "openai"
                              ? "🤖 Whisper"
                              : record.model === "gemini"
                                ? "✨ Gemini"
                                : "🌐 Web Speech"}
                          </span>
                        </div>
                        <p className="transcription">
                          <strong>📝 Transcription:</strong>{" "}
                          {record.transcription || "(no speech detected)"}
                        </p>
                      </div>
                      <div className="audio-controls">
                        <audio
                          controls
                          className="audio-player"
                          controlsList="nodownload"
                        >
                          <source
                            src={URL.createObjectURL(record.audioBlob)}
                            type="audio/webm"
                          />
                        </audio>
                        <button
                          onClick={() =>
                            downloadAudio(
                              record.audioBlob,
                              `recording-${record.id}.webm`,
                            )
                          }
                          className="btn btn-small"
                        >
                          ⬇️ Download
                        </button>
                        <button
                          onClick={() => deleteAudioRecord(record.id)}
                          className="btn btn-small btn-danger"
                        >
                          🗑️ Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

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
      )}
    </>
  );
}
