import { type ChangeEvent, useEffect, useRef, useState } from "react";
import PitchChart from "../PitchChart";
import PraatTimeline from "./PraatTimeline";
import "./StoryRecorder.css";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

type SpeechModel = "webspeech" | "ctwhisper" | "vibevoice";

interface Topic {
  id: string;
  name: string;
  description?: string;
  skillFocus?: string;
  level?: string;
  images: string[];
  vocabulary: Record<number, string[]>;
  conceptMaps?: Record<number, Partial<ConceptMapDraft>>;
}

interface PraatMetrics {
  transcription?: string;
  transcription_model?: string;
  pitch_contour: Array<[number, number]>;
  word_prosody?: WordProsody[];
  detected_tone: number;
  tone_accuracy: number;
  formants: Record<string, number>;
  speech_rate: number;
  fluency_score: number;
  pitch_statistics: Record<string, number>;
  feedback: string;
  ai_feedback?: LanguageFeedback;
}

interface WordProsody {
  token: string;
  index: number;
  start_time: number;
  end_time: number;
  pitch_contour: Array<[number, number]>;
  mean_pitch: number;
  pitch_range: number;
  start_pitch: number;
  end_pitch: number;
  contour_shape: string;
  feedback: string;
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

interface ConceptMapDraft {
  characters: string;
  place: string;
  actions: string;
  vocabulary: string;
  connectors: string;
  fullStory: string;
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
    imageUrl: string;
    imageIndex: number;
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
  const [analysisAudioBlob, setAnalysisAudioBlob] = useState<Blob | null>(null);
  const [submittedAudioName, setSubmittedAudioName] = useState("");
  const [conceptDraft, setConceptDraft] = useState<ConceptMapDraft>(
    createEmptyConceptMapDraft(),
  );

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const durationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );
  const recordingStartRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const currentTranscriptRef = useRef("");

  useEffect(() => {
    return () => {
      stopTracks();
      clearTimers();
    };
  }, []);

  useEffect(() => {
    setConceptDraft(createConceptMapDraft(topic, selectedImageIndex));
  }, [selectedImageIndex, topic.id]);

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
      setAnalysisAudioBlob(null);
      setSubmittedAudioName("");
      currentTranscriptRef.current = "";
      recordingStartRef.current = Date.now();
      setRecordingDuration(0);
      setSilenceDuration(0);
      lastSpeechAtRef.current = Date.now();

      if (selectedModel === "webspeech") {
        await startWebSpeechRecording();
      } else {
        await startAudioRecording(async (audioBlob) => {
          if (selectedModel === "vibevoice") {
            await analyzeSpeechAudio(audioBlob, "", "vibevoice");
          } else {
            await transcribeAudio(audioBlob);
          }
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
      await analyzeSpeechAudio(
        audioBlob,
        currentTranscriptRef.current.trim() || practiceAnalysisText,
      );
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

  const startAudioRecording = async (
    onStop: (audioBlob: Blob) => Promise<void>,
  ) => {
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
      const backendUrl = getBackendUrl();
      const wavBlob = await convertBlobToWav(audioBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "speech.wav");
      formData.append("model", selectedModel);

      const response = await fetch(`${backendUrl}/api/transcribe`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "Transcription failed");
      }

      const data = await response.json();
      const transcript = (data.text || "").trim();
      if (transcript) {
        addTranscription(transcript);
        currentTranscriptRef.current = transcript;
      }
      await analyzeSpeechAudio(wavBlob, transcript || practiceAnalysisText);
    } catch (err) {
      setError(formatBackendError(err, BACKEND_URL || "the configured backend"));
    } finally {
      setIsTranscribing(false);
    }
  };

  const analyzeSpeechAudio = async (
    audioBlob: Blob,
    transcription: string,
    asrModel = "",
    recordModel: SpeechModel = selectedModel,
  ) => {
    setIsAnalyzing(true);
    try {
      const backendUrl = getBackendUrl();
      const wavBlob = await convertBlobToWav(audioBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "speech.wav");
      const analysisText = transcription.trim() || (asrModel ? "" : practiceAnalysisText);
      formData.append("transcription", analysisText);
      if (asrModel) {
        formData.append("asr_model", asrModel);
      }

      const response = await fetch(`${backendUrl}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "Praat analysis failed");
      }

      const metrics = (await response.json()) as PraatMetrics;
      const finalTranscription = (
        metrics.transcription ||
        analysisText ||
        practiceAnalysisText
      ).trim();
      if (finalTranscription && finalTranscription !== currentTranscriptRef.current) {
        currentTranscriptRef.current = finalTranscription;
        if (finalTranscription !== practiceAnalysisText) {
          addTranscription(finalTranscription, recordModel);
        }
      }
      setPraatMetrics(metrics);
      setAnalysisAudioBlob(wavBlob);

      onAddRecord({
        id: `audio-${Date.now()}`,
        audioBlob: wavBlob,
        timestamp: new Date().toLocaleString(),
        duration: Math.max(
          1,
          Math.floor((Date.now() - recordingStartRef.current) / 1000),
        ),
        transcription: finalTranscription,
        model: recordModel,
        topicId: topic.id,
        imageUrl: selectedImage,
        imageIndex: selectedImageIndex,
        praatMetrics: metrics,
      });
    } catch (err) {
      setError(formatBackendError(err, BACKEND_URL || "the configured backend"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleSubmitVoiceFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    if (!file.type.startsWith("audio/") && !hasAudioFileExtension(file.name)) {
      setError(`Submit an audio file. "${file.name}" is not supported.`);
      return;
    }

    setError(null);
    setPraatMetrics(null);
    setAnalysisAudioBlob(null);
    setSubmittedAudioName(file.name);
    currentTranscriptRef.current = "";
    recordingStartRef.current = Date.now();
    setRecordingDuration(0);

    const uploadModel = selectedModel === "webspeech" ? "ctwhisper" : selectedModel;
    await analyzeSpeechAudio(file, "", uploadModel, uploadModel);
  };

  const addTranscription = (text: string, model: SpeechModel = selectedModel) => {
    if (!text.trim()) return;

    setTranscriptions((prev) => [
      ...prev,
      {
        text,
        timestamp: new Date().toLocaleTimeString(),
        model,
      },
    ]);
  };

  const getToneName = (tone: number): string => {
    const toneNames: Record<number, string> = {
      1: "Tone 1 - High Level (ma1)",
      2: "Tone 2 - Rising (ma2)",
      3: "Tone 3 - Falling-Rising (ma3)",
      4: "Tone 4 - Falling (ma4)",
    };
    return toneNames[tone] || "No clear tone";
  };

  const isBusy = isRecording || isTranscribing || isAnalyzing;
  const selectedVocabulary = topic.vocabulary[selectedImageIndex] || [];
  const teacherConceptMap = topic.conceptMaps?.[selectedImageIndex] || {};
  const conceptMapText = buildConceptMapText(conceptDraft);
  const practiceAnalysisText =
    conceptMapText || buildPracticeAnalysisText(selectedVocabulary);
  const hasWordProsody = Boolean(praatMetrics?.word_prosody?.length);
  const modelExampleText =
    currentTranscriptRef.current || practiceAnalysisText || "Today I am at school and I help a friend.";
  const storyConnectors = ["first", "then", "because", "so", "finally"];
  const sentenceStarters = [
    "First,",
    "Then,",
    "Because",
    "So",
    "Finally,",
  ];
  const recordingStatus = isRecording
    ? "Recording in progress"
    : isTranscribing
      ? "Transcribing speech"
      : isAnalyzing
        ? "Analyzing pronunciation"
        : praatMetrics
          ? "Feedback ready"
          : "Ready to record";
  const recordingButtonLabel = isRecording
    ? "Stop and analyze"
    : praatMetrics
      ? "Record again"
      : "Start recording";
  const recordingButtonDisabled = isTranscribing || isAnalyzing;
  const activeFlowStep = praatMetrics
    ? "review"
    : isRecording || isTranscribing || isAnalyzing
      ? "record"
      : conceptMapText
        ? "record"
        : "plan";

  const handlePrimaryRecordingAction = () => {
    if (isRecording) {
      stopRecording();
      return;
    }

    startRecording();
  };

  const updateConceptDraft = (
    field: keyof ConceptMapDraft,
    value: string,
  ) => {
    setConceptDraft((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const appendConceptToken = (
    field: keyof ConceptMapDraft,
    token: string,
  ) => {
    setConceptDraft((prev) => ({
      ...prev,
      [field]: appendToken(prev[field], token),
    }));
  };

  return (
    <div className="story-recorder">
      <section className="student-flow-board" aria-label="Student practice flow">
        <div className="flow-step completed">
          <span>1</span>
          <strong>Look</strong>
          <p>Study the picture cue.</p>
        </div>
        <div className={`flow-step ${activeFlowStep === "plan" ? "active" : ""}`}>
          <span>2</span>
          <strong>Plan</strong>
          <p>Choose who, where, and action.</p>
        </div>
        <div className={`flow-step ${activeFlowStep === "record" ? "active" : ""}`}>
          <span>3</span>
          <strong>Record</strong>
          <p>Speak this cue clearly.</p>
        </div>
        <div className={`flow-step ${activeFlowStep === "review" ? "active" : ""}`}>
          <span>4</span>
          <strong>Review</strong>
          <p>Use feedback to revise.</p>
        </div>
      </section>

      <section className="recorder-hero">
        <div className="recorder-hero-copy">
          <p className="eyebrow">Picture cue {selectedImageIndex + 1} of {topic.images.length}</p>
          <h1>{topic.name} Story Challenge</h1>
          <p>
            {topic.description ||
              "Tell a complete Mandarin story using the selected picture."}
          </p>
          <div className="challenge-meta">
            <span>{topic.level || "Narrative practice"}</span>
            <span>{topic.skillFocus || "Story fluency"}</span>
            <span>
              Story part {selectedImageIndex + 1} of {topic.images.length}
            </span>
          </div>
        </div>

        <div className="recording-status-card">
          <span>Status</span>
          <strong>{recordingStatus}</strong>
          {isRecording ? (
            <p>{recordingDuration}s recorded</p>
          ) : (
            <p>Finish the quick plan, then record this cue.</p>
          )}
        </div>
      </section>

      <section className="recording-workspace">
        <div className="prompt-stage">
          <div className="story-image-preview">
            <img src={selectedImage} alt="Selected story prompt" />
          </div>

          <div className="prompt-thumbnails">
            {topic.images.map((image, index) => (
              <button
                type="button"
                key={image}
                className={`prompt-mini-card ${
                  selectedImageIndex === index ? "selected" : ""
                }`}
                onClick={() => {
                  onImageChange(image);
                  onImageSelect(index);
                }}
                disabled={isBusy}
              >
                <img src={image} alt={`Story prompt ${index + 1}`} />
                <span>Part {index + 1}</span>
              </button>
            ))}
          </div>
        </div>

        <aside className="recording-coach-panel">
          <div className="coach-block task-card">
            <h2>Your task</h2>
            <p>
              Tell only this picture cue first. One or two clear sentences is
              enough.
            </p>
          </div>

          <div className="coach-block">
            <h2>Simple speaking pattern</h2>
            <ol>
              <li>Who is in the picture?</li>
              <li>Where are they?</li>
              <li>What happens?</li>
            </ol>
          </div>

          <div className="coach-block">
            <h2>Vocabulary boost</h2>
            <div className="recording-vocabulary">
              {selectedVocabulary.map((word) => (
                <span key={word}>{word}</span>
              ))}
            </div>
          </div>

          <div className="coach-block readiness-card">
            <h2>Ready?</h2>
            <div className="readiness-list">
              <span>Quiet space</span>
              <span>Clear voice</span>
              <span>One ending</span>
            </div>
          </div>
        </aside>
      </section>

      <section className="concept-map-section" aria-label="Story concept map">
        <div className="concept-map-header">
          <p className="eyebrow">Quick plan</p>
          <h2>Plan this picture cue</h2>
          <p>
            Fill the missing ideas first. If your teacher prepared a layout,
            use it to build one clear story sentence before recording.
          </p>
        </div>

        <div className="concept-map">
          <label className="concept-node character">
            <span>Characters</span>
            <strong>隤? Who?</strong>
            <textarea
              value={conceptDraft.characters}
              onChange={(event) =>
                updateConceptDraft("characters", event.target.value)
              }
              placeholder={getConceptPlaceholder(teacherConceptMap, "characters", "Example: student, teacher, friend")}
              rows={3}
            />
          </label>
          <label className="concept-node scene">
            <span>Place</span>
            <strong>?典鋆? Where?</strong>
            <textarea
              value={conceptDraft.place}
              onChange={(event) => updateConceptDraft("place", event.target.value)}
              placeholder={getConceptPlaceholder(teacherConceptMap, "place", "Example: school, market, park")}
              rows={3}
            />
          </label>
          <label className="concept-node event">
            <span>Actions</span>
            <strong>??暻? What happens?</strong>
            <textarea
              value={conceptDraft.actions}
              onChange={(event) =>
                updateConceptDraft("actions", event.target.value)
              }
              placeholder={getConceptPlaceholder(teacherConceptMap, "actions", "Example: sees, helps, walks together")}
              rows={3}
            />
          </label>
          <label className="concept-node vocabulary-node">
            <span>Vocabulary</span>
            <strong>Useful words</strong>
            <textarea
              value={conceptDraft.vocabulary}
              onChange={(event) =>
                updateConceptDraft("vocabulary", event.target.value)
              }
              placeholder={getConceptPlaceholder(teacherConceptMap, "vocabulary", "Click words below or type your own")}
              rows={3}
            />
          </label>
          <label className="concept-node connector-node">
            <span>Connectors</span>
            <strong>How ideas connect</strong>
            <textarea
              value={conceptDraft.connectors}
              onChange={(event) =>
                updateConceptDraft("connectors", event.target.value)
              }
              placeholder={getConceptPlaceholder(teacherConceptMap, "connectors", "Example: then, because, so, finally")}
              rows={3}
            />
          </label>
          <label className="concept-node full-story-node">
            <span>Full Story</span>
            <strong>Combine your ideas</strong>
            <textarea
              value={conceptDraft.fullStory}
              onChange={(event) =>
                updateConceptDraft("fullStory", event.target.value)
              }
              placeholder={getConceptPlaceholder(teacherConceptMap, "fullStory", "Example: First, the student is at the market. Then, the student helps a friend.")}
              rows={5}
            />
          </label>
        </div>

        <div className="concept-chip-panel">
          <div className="concept-chip-group">
            <span>Vocabulary</span>
            <div>
              {selectedVocabulary.map((word) => (
                <button
                  type="button"
                  key={word}
                  onClick={() => appendConceptToken("vocabulary", word)}
                  disabled={isBusy}
                >
                  {word}
                </button>
              ))}
            </div>
          </div>

          <div className="concept-chip-group">
            <span>Connectors</span>
            <div>
              {storyConnectors.map((connector) => (
                <button
                  type="button"
                  key={connector}
                  onClick={() => appendConceptToken("connectors", connector)}
                  disabled={isBusy}
                >
                  {connector}
                </button>
              ))}
            </div>
          </div>

          <div className="concept-chip-group">
            <span>Sentence starters</span>
            <div>
              {sentenceStarters.map((starter) => (
                <button
                  type="button"
                  key={starter}
                  onClick={() => appendConceptToken("fullStory", starter)}
                  disabled={isBusy}
                >
                  {starter}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="concept-practice-text">
          <span>Pronunciation target</span>
          <p>
            {practiceAnalysisText ||
              "Add vocabulary or write your full story before recording."}
          </p>
        </div>

        <div className="concept-map-actions">
          <button
            type="button"
            onClick={() =>
              updateConceptDraft("fullStory", buildSuggestedStory(conceptDraft))
            }
            disabled={isBusy}
          >
            Draft story from map
          </button>
          <button
            type="button"
            onClick={() => setConceptDraft(createEmptyConceptMapDraft())}
            disabled={isBusy}
          >
            Clear map
          </button>
        </div>

        <div className="word-level-note">
          <strong>Word-level pronunciation</strong>
          <p>
            After recording, Praat aligns the pitch contour to each Mandarin
            character in your transcript or target story and shows contour,
            average pitch, pitch range, and coaching feedback.
          </p>
        </div>

        <div className="sentence-starters" hidden>
          <span>Starter phrases</span>
          <p>銝??... / ?嗅?... / ?... / ?隞?.. / ?敺?..</p>
        </div>
      </section>

      {praatMetrics && hasWordProsody && (
        <section
          className="word-level-preview"
          aria-label="Word-level pronunciation overview"
        >
          <div>
            <p className="eyebrow">Word-level pronunciation</p>
            <h2>Character prosody preview</h2>
          </div>
          <div className="word-level-strip">
            {praatMetrics.word_prosody?.slice(0, 18).map((item) => (
              <div
                key={`preview-${item.token}-${item.index}`}
                className={`word-level-token ${item.contour_shape}`}
              >
                <strong>{item.token}</strong>
                <span>{formatContourShape(item.contour_shape)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="recording-console simple-recording-console">
        <div className="recording-action-copy">
          <span>Record or submit</span>
          <h2>Speak your story</h2>
          <p>Use the picture, vocabulary, and four-step plan, then record or upload voice audio.</p>
        </div>

        <div className="controls simple-controls">
          <button
            type="button"
            onClick={handlePrimaryRecordingAction}
            disabled={recordingButtonDisabled}
            className={`btn btn-record-main ${
              isRecording ? "btn-danger" : "btn-primary"
            }`}
          >
            {recordingButtonLabel}
          </button>

          <label
            className={`btn btn-secondary submit-voice-label ${
              isBusy ? "disabled" : ""
            }`}
            role="button"
            tabIndex={isBusy ? -1 : 0}
          >
            Submit voice file
            <input
              className="submit-voice-input"
              type="file"
              accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg"
              onChange={handleSubmitVoiceFile}
              disabled={isBusy}
            />
          </label>

          {submittedAudioName && (
            <p className="submitted-audio-name">Submitted: {submittedAudioName}</p>
          )}

          <details className="advanced-recording-options">
            <summary>Recording options</summary>
            <div className="model-selector">
              <label htmlFor="model">Speech source</label>
              <select
                id="model"
                value={selectedModel}
                onChange={(event) =>
                  setSelectedModel(event.target.value as SpeechModel)
                }
                disabled={isBusy}
              >
                <option value="webspeech">
                  Browser Traditional Chinese transcript and Praat analysis
                </option>
                <option value="ctwhisper">
                  Chinese/Taiwanese Whisper transcript and Praat analysis
                </option>
                <option value="vibevoice">
                  VibeVoice-ASR local file transcript and Praat analysis
                </option>
              </select>
            </div>
          </details>
        </div>
      </section>

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
            <p className="eyebrow">Feedback unlocked</p>
            <h2>Your Speaking Results</h2>
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

          <StudentFeedbackCards
            toneAccuracy={praatMetrics.tone_accuracy}
            fluencyScore={praatMetrics.fluency_score}
            speechRate={praatMetrics.speech_rate}
            wordProsody={praatMetrics.word_prosody || []}
          />

          <ModelExampleCard
            text={modelExampleText}
            focusWord={getToneFocusItems(praatMetrics.word_prosody || [])[0]?.token}
          />

          <details className="advanced-praat-details">
            <summary>Advanced Praat details</summary>
            <PraatTimeline
              audioBlob={analysisAudioBlob}
              pitchContour={praatMetrics.pitch_contour}
              wordProsody={praatMetrics.word_prosody}
              transcription={currentTranscriptRef.current}
            />

            <div className="chart-section">
              <PitchChart
                pitchContour={praatMetrics.pitch_contour}
                detectedTone={praatMetrics.detected_tone}
              />
            </div>

            <div className="word-prosody-section">
              <div className="word-prosody-header">
                <h3>Word-by-word prosody</h3>
                <p>
                  Each card estimates pitch movement for one Mandarin character
                  or spoken word.
                </p>
              </div>

              {hasWordProsody ? (
                  <div className="word-prosody-grid">
                    {praatMetrics.word_prosody?.map((item) => (
                      <WordProsodyCard key={`${item.token}-${item.index}`} item={item} />
                    ))}
                  </div>
              ) : (
                <div className="word-prosody-empty">
                  <strong>No word feedback yet</strong>
                  <p>
                    Praat needs a clear pitch contour and transcript. Try one
                    complete sentence, or choose Chinese/Taiwanese Whisper in
                    recording options for backend transcription.
                  </p>
                </div>
              )}
            </div>
          </details>

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
        <h2>Speech transcript</h2>
        {transcriptions.length === 0 ? (
          <p className="empty">Your transcript will appear after recording.</p>
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

function WordProsodyCard({ item }: { item: WordProsody }) {
  return (
    <div className="word-prosody-card">
      <div className="word-prosody-topline">
        <strong>{item.token}</strong>
        <span>{formatContourShape(item.contour_shape)}</span>
      </div>
      <div className="mini-contour" aria-label={`${item.token} pitch contour`}>
        {item.pitch_contour.length > 1 ? (
          item.pitch_contour.map((point, index) => {
            const pitches = item.pitch_contour.map((entry) => entry[1]);
            const min = Math.min(...pitches);
            const max = Math.max(...pitches);
            const range = Math.max(max - min, 1);
            const height = 18 + ((point[1] - min) / range) * 42;

            return (
              <span
                key={`${point[0]}-${index}`}
                style={{ height: `${height}px` }}
              />
            );
          })
        ) : (
          <span style={{ height: "28px" }} />
        )}
      </div>
      <div className="word-prosody-stats">
        <span>{Math.round(item.mean_pitch)} Hz avg</span>
        <span>{Math.round(item.pitch_range)} Hz range</span>
      </div>
      <p>{item.feedback}</p>
    </div>
  );
}

function buildPracticeAnalysisText(vocabulary: string[]): string {
  return vocabulary
    .map((word) => word.trim())
    .filter(Boolean)
    .join(" ");
}

function createEmptyConceptMapDraft(): ConceptMapDraft {
  return {
    characters: "",
    place: "",
    actions: "",
    vocabulary: "",
    connectors: "",
    fullStory: "",
  };
}

function createConceptMapDraft(topic: Topic, imageIndex: number): ConceptMapDraft {
  const scaffold = topic.conceptMaps?.[imageIndex] || {};

  return {
    characters: getScaffoldValue(scaffold.characters),
    place: getScaffoldValue(scaffold.place),
    actions: getScaffoldValue(scaffold.actions),
    vocabulary: getScaffoldValue(scaffold.vocabulary),
    connectors: getScaffoldValue(scaffold.connectors),
    fullStory: getScaffoldValue(scaffold.fullStory),
  };
}

function getScaffoldValue(value?: string): string {
  const cleanValue = value?.trim() || "";
  return cleanValue.includes("___") ? "" : cleanValue;
}

function getConceptPlaceholder(
  scaffold: Partial<ConceptMapDraft>,
  field: keyof ConceptMapDraft,
  fallback: string,
): string {
  const value = scaffold[field]?.trim();
  return value || fallback;
}

function buildConceptMapText(draft: ConceptMapDraft): string {
  const fullStory = draft.fullStory.trim();
  if (fullStory) {
    return fullStory;
  }

  return [
    draft.characters,
    draft.place,
    draft.actions,
    draft.vocabulary,
    draft.connectors,
  ]
    .map((value) => value.trim())
    .filter(Boolean)
    .join(" ");
}

function buildSuggestedStory(draft: ConceptMapDraft): string {
  const characters = draft.characters.trim() || "someone";
  const place = draft.place.trim() || "a familiar place";
  const actions = draft.actions.trim() || "does something helpful";
  const vocabulary = draft.vocabulary.trim();
  const connectors = draft.connectors.trim() || "then finally";
  const connectorList = connectors.split(/\s+/).filter(Boolean);
  const secondConnector = connectorList[0] || "Then";
  const finalConnector = connectorList[connectorList.length - 1] || "Finally";

  return [
    `First, ${characters} is at ${place}.`,
    `${secondConnector}, ${characters} ${actions}.`,
    vocabulary ? `Useful words: ${vocabulary}.` : "",
    `${finalConnector}, the story has a clear ending.`,
  ]
    .filter(Boolean)
    .join(" ");
}
function appendToken(currentValue: string, token: string): string {
  const cleanToken = token.trim();
  if (!cleanToken) {
    return currentValue;
  }

  const trimmed = currentValue.trim();
  return trimmed ? `${trimmed} ${cleanToken}` : cleanToken;
}

function hasAudioFileExtension(fileName: string): boolean {
  return /\.(wav|wave|webm|mp3|m4a|ogg)$/i.test(fileName);
}

function formatContourShape(shape: string): string {
  const labels: Record<string, string> = {
    dip: "Dipping",
    falling: "Falling",
    level: "Level",
    rising: "Rising",
    variable: "Variable",
  };
  return labels[shape] || "Variable";
}

function getBackendUrl(): string {
  if (BACKEND_URL) {
    return BACKEND_URL;
  }

  throw new Error(
    "Praat analysis needs a deployed backend in production. Deploy the FastAPI backend and set VITE_BACKEND_URL to its public URL.",
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

  return (
    <section className="student-feedback-cards" aria-label="Student feedback">
      <div className="student-feedback-card good">
        <span>Good</span>
        <strong>{studentStrength(toneAccuracy, fluencyScore)}</strong>
      </div>
      <div className="student-feedback-card fix">
        <span>Fix</span>
        <strong>{studentFix(toneAccuracy, fluencyScore, speechRate, focus)}</strong>
      </div>
      <div className="student-feedback-card next">
        <span>Next try</span>
        <strong>{studentNextStep(speechRate, focus)}</strong>
      </div>
    </section>
  );
}

function studentStrength(toneAccuracy: number, fluencyScore: number): string {
  if (toneAccuracy >= 80 && fluencyScore >= 75) {
    return "Your tones and rhythm are clear enough to build a longer sentence.";
  }
  if (toneAccuracy >= 75) {
    return "Your tone shape is recognizable.";
  }
  if (fluencyScore >= 75) {
    return "Your speaking rhythm is steady.";
  }
  return "You completed a recording. Now improve one small part.";
}

function studentFix(
  toneAccuracy: number,
  fluencyScore: number,
  speechRate: number,
  focus?: WordProsody,
): string {
  if (speechRate > 6.5) {
    return "Slow down so each Mandarin tone has time to finish.";
  }
  if (toneAccuracy < 65 && focus) {
    return `Make the tone movement clearer on "${focus.token}".`;
  }
  if (fluencyScore < 60) {
    return "Connect the words more smoothly without stopping between every character.";
  }
  if (focus) {
    return `Polish "${focus.token}" first.`;
  }
  return "Keep the sentence short and make every tone clear.";
}

function studentNextStep(speechRate: number, focus?: WordProsody): string {
  if (focus) {
    return `Say "${focus.token}" three times, then repeat the full sentence.`;
  }
  if (speechRate < 2.5) {
    return "Try the same sentence again with a little more flow.";
  }
  return "Record again and try to match the same clear rhythm.";
}

function ModelExampleCard({
  text,
  focusWord,
}: {
  text: string;
  focusWord?: string;
}) {
  const exampleText = text.trim() || "Today I am at school and I help a friend.";

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
    <section className="model-example-card" aria-label="100 score example">
      <div>
        <span>100-score example</span>
        <h3>Listen, then copy with your voice</h3>
        <p>{exampleText}</p>
      </div>
      <div className="model-example-actions">
        {focusWord && <em>Focus first: {focusWord}</em>}
        <button type="button" onClick={playExample}>
          Play example
        </button>
      </div>
    </section>
  );
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

async function readErrorResponse(response: Response): Promise<{ detail?: string }> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

function formatBackendError(error: unknown, backendUrl: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const networkFailures = [
    "Failed to fetch",
    "NetworkError",
    "Load failed",
    "The operation was aborted",
  ];

  if (networkFailures.some((failure) => message.includes(failure))) {
    return `Cannot reach the speech analysis backend at ${backendUrl}. Start the FastAPI backend on port 8000, then record again.`;
  }

  return message || "Speech analysis error occurred";
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

