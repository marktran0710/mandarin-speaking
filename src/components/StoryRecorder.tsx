import { type ChangeEvent, useEffect, useRef, useState } from "react";
import PitchChart from "../PitchChart";
import PraatTimeline from "./PraatTimeline";
import StoryConceptMap from "./StoryConceptMap";
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
  prompts?: string[];
  vocabulary: Record<number, string[]>;
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
  enableSorting?: boolean;
}

export default function StoryRecorder({
  topic,
  selectedImage,
  selectedImageIndex,
  onImageSelect,
  onImageChange,
  onAddRecord,
  enableSorting = false,
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

  // Learning phase: overview → sorting → conceptmap → practice
  const [phase, setPhase] = useState<"overview" | "sorting" | "conceptmap" | "practice">(
    enableSorting ? "overview" : "practice"
  );
  const [shuffledPool, setShuffledPool] = useState<string[]>([]);
  const [placedImages, setPlacedImages] = useState<Array<string | null>>([]);
  const [selectedPoolImage, setSelectedPoolImage] = useState<string | null>(null);
  const [validationStates, setValidationStates] = useState<Array<"correct" | "incorrect" | null>>([]);
  const [sortingFeedback, setSortingFeedback] = useState<string>("");
  const [, setSortingAttempts] = useState(0);

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

  const shuffleImages = (images: string[]) => {
    if (!images || images.length === 0) return [];
    let scrambled = [...images];
    // Fisher-Yates shuffle
    for (let i = scrambled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [scrambled[i], scrambled[j]] = [scrambled[j], scrambled[i]];
    }
    // Swap first two if order is unchanged
    const isSameOrder = scrambled.every((img, idx) => img === images[idx]);
    if (isSameOrder && scrambled.length > 1) {
      const temp = scrambled[0];
      scrambled[0] = scrambled[1];
      scrambled[1] = temp;
    }
    return scrambled;
  };

  useEffect(() => {
    setPhase(enableSorting ? "overview" : "practice");
    setSelectedPoolImage(null);
    setSortingFeedback("");
    setSortingAttempts(0);
    setValidationStates(new Array(topic.images.length).fill(null));
    const pool = shuffleImages(topic.images);
    setShuffledPool(pool);
    setPlacedImages(new Array(topic.images.length).fill(null));
  }, [topic.id, topic.images, enableSorting]);

  useEffect(() => {
    return () => {
      stopTracks();
      clearTimers();
    };
  }, []);

  useEffect(() => {
    setConceptDraft(createEmptyConceptMapDraft());
  }, [selectedImageIndex, topic.id]);

  // Sorting Challenge Handlers
  const handleDragStart = (e: React.DragEvent, image: string, source: "pool" | "slot", index?: number) => {
    e.dataTransfer.setData("text/plain", JSON.stringify({ image, source, index }));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const placePoolImageInSlot = (image: string, targetIndex: number) => {
    setPlacedImages((prev) => {
      const next = [...prev];
      const existingImage = next[targetIndex];
      next[targetIndex] = image;
      
      setShuffledPool((pool) => {
        let nextPool = pool.filter((img) => img !== image);
        if (existingImage) {
          nextPool.push(existingImage);
        }
        return nextPool;
      });

      return next;
    });
    setSelectedPoolImage(null);
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

  const swapSlots = (sourceIndex: number, targetIndex: number) => {
    setPlacedImages((prev) => {
      const next = [...prev];
      const temp = next[targetIndex];
      next[targetIndex] = next[sourceIndex];
      next[sourceIndex] = temp;
      return next;
    });
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

  const removeImageFromSlot = (slotIndex: number) => {
    const image = placedImages[slotIndex];
    if (!image) return;

    setPlacedImages((prev) => {
      const next = [...prev];
      next[slotIndex] = null;
      return next;
    });

    setShuffledPool((pool) => [...pool, image]);
    setSelectedPoolImage(null);
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

  const handleDropToSlot = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    try {
      const dataStr = e.dataTransfer.getData("text/plain");
      if (!dataStr) return;
      const data = JSON.parse(dataStr);
      const { image, source, index: sourceIndex } = data;

      if (source === "pool") {
        placePoolImageInSlot(image, targetIndex);
      } else if (source === "slot" && sourceIndex !== undefined) {
        swapSlots(sourceIndex, targetIndex);
      }
    } catch (err) {
      console.error("Drop to slot failed", err);
    }
  };

  const handleDropToPool = (e: React.DragEvent) => {
    e.preventDefault();
    try {
      const dataStr = e.dataTransfer.getData("text/plain");
      if (!dataStr) return;
      const data = JSON.parse(dataStr);
      const { source, index: sourceIndex } = data;

      if (source === "slot" && sourceIndex !== undefined) {
        removeImageFromSlot(sourceIndex);
      }
    } catch (err) {
      console.error("Drop to pool failed", err);
    }
  };

  const checkSequence = () => {
    const isAnySlotEmpty = placedImages.some((img) => img === null);
    if (isAnySlotEmpty) {
      setSortingFeedback("Please place all pictures into the scenes before checking!");
      return;
    }

    const nextValidationStates = placedImages.map((image, index) => {
      return image === topic.images[index] ? "correct" : "incorrect";
    });
    setValidationStates(nextValidationStates);

    const isAllCorrect = nextValidationStates.every((state) => state === "correct");
    setSortingAttempts((prev) => prev + 1);

    if (isAllCorrect) {
      setSortingFeedback("Spot on! Excellent job. You have arranged the scenes in the correct order!");
    } else {
      setSortingFeedback("Some pictures are not in the correct sequence. Check the red highlighted scenes and try again!");
    }
  };

  const resetSorting = () => {
    setPlacedImages(new Array(topic.images.length).fill(null));
    setShuffledPool([...topic.images]);
    setSelectedPoolImage(null);
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

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
  const conceptMapText = buildConceptMapText(conceptDraft);
  const practiceAnalysisText =
    conceptMapText || buildPracticeAnalysisText(selectedVocabulary);
  const hasWordProsody = Boolean(praatMetrics?.word_prosody?.length);
  const modelExampleText =
    currentTranscriptRef.current || practiceAnalysisText || "今天下雨，所以我帶傘。";
  const storyConnectors = ["一開始", "然後", "因為", "所以", "突然", "最後"];
  const sentenceStarters = [
    "一開始，",
    "他們在",
    "然後，",
    "突然，",
    "最後，",
  ];
  const recordingButtonDisabled = isTranscribing || isAnalyzing;


  const handlePrimaryRecordingAction = () => {
    if (isRecording) {
      stopRecording();
      return;
    }

    startRecording();
  };



  const allVocabulary = topic.images.flatMap((_, si) => topic.vocabulary[si] || []);

  const PHASES = [
    { key: "overview",    label: "Overview",        icon: "📖" },
    { key: "sorting",     label: "Arrange Scenes",  icon: "🧩" },
    { key: "conceptmap",  label: "Vocabulary Map",  icon: "🗺️" },
    { key: "practice",    label: "Speaking",        icon: "🎙️" },
  ] as const;

  const phaseOrder = PHASES.map(p => p.key);
  const currentPhaseIdx = phaseOrder.indexOf(phase);

  return (
    <div className="story-recorder">
      {/* ── Phase navigation bar ── */}
      <nav className="phase-nav" aria-label="Progress">
        {PHASES.map((p, i) => {
          const status = i < currentPhaseIdx ? "done" : i === currentPhaseIdx ? "active" : "upcoming";
          return (
            <div key={p.key} className={`phase-nav-step phase-nav-${status}`}>
              <span className="phase-nav-icon">{status === "done" ? "✓" : p.icon}</span>
              <span className="phase-nav-label">{p.label}</span>
              {i < PHASES.length - 1 && <span className="phase-nav-arrow">›</span>}
            </div>
          );
        })}
      </nav>

      {phase === "overview" && (
        <section className="story-overview">
          <div className="overview-hero">
            <p className="eyebrow">Story Challenge</p>
            <h1 className="overview-title">{topic.name}</h1>
            {topic.description && <p className="overview-desc">{topic.description}</p>}
            {(topic.level || topic.skillFocus) && (
              <div className="overview-meta">
                {topic.level && <span>{topic.level}</span>}
                {topic.skillFocus && <span>{topic.skillFocus}</span>}
              </div>
            )}
          </div>


          {allVocabulary.length > 0 && (
            <div className="overview-vocab-block">
              <h2>Key Vocabulary</h2>
              <div className="overview-vocab-chips">
                {allVocabulary.map((word, i) => (
                  <span key={`${word}-${i}`} className="overview-vocab-chip">{word}</span>
                ))}
              </div>
            </div>
          )}

          <div className="overview-steps-block">
            <h2>Your Challenge</h2>
            <div className="overview-steps">
              <div className="overview-step">
                <span className="overview-step-num">1</span>
                <div>
                  <strong>Arrange Scenes</strong>
                  <p>Put the story pictures in the right order</p>
                </div>
              </div>
              <div className="overview-step">
                <span className="overview-step-num">2</span>
                <div>
                  <strong>Vocabulary Map</strong>
                  <p>Match key words to each story scene</p>
                </div>
              </div>
              <div className="overview-step">
                <span className="overview-step-num">3</span>
                <div>
                  <strong>Speaking Practice</strong>
                  <p>Record your Mandarin story out loud</p>
                </div>
              </div>
            </div>
          </div>

          <div className="overview-cta">
            <button className="btn-start-challenge" onClick={() => setPhase("sorting")}>
              Let's Go! →
            </button>
          </div>
        </section>
      )}

      {phase === "sorting" && (
        <section className="sorting-challenge-container">

          {/* ── Header ── */}
          <div className="sorting-header">
            <div className="sorting-header-copy">
              <p className="eyebrow">Step 1 · Arrange Scenes</p>
              <h1>Put the Story in Order</h1>
              <p className="subtitle">
                Drag each picture into the correct scene slot, then verify the sequence to unlock speaking practice.
              </p>
            </div>
            <div className="sorting-progress">
              <div className="sorting-progress-label">
                {placedImages.filter(Boolean).length} / {placedImages.length} placed
              </div>
              <div className="sorting-progress-bar">
                <div
                  className="sorting-progress-fill"
                  style={{ width: `${(placedImages.filter(Boolean).length / placedImages.length) * 100}%` }}
                />
              </div>
            </div>
          </div>

          {sortingFeedback && (
            <div className={`sorting-feedback-banner ${sortingFeedback.includes("Spot on") ? "success" : "info"}`}>
              <span className="feedback-icon">{sortingFeedback.includes("Spot on") ? "🎉" : "💡"}</span>
              <p>{sortingFeedback}</p>
            </div>
          )}

          {/* ── Scene slots ── */}
          <div className="sorting-slots-grid">
            {placedImages.map((image, index) => {
              const validation = validationStates[index];
              const scenePrompt = topic.prompts?.[index];
              return (
                <div
                  key={`slot-${index}`}
                  className={`sorting-slot-card ${validation || ""} ${selectedPoolImage ? "droppable" : ""}`}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDropToSlot(e, index)}
                  onClick={() => {
                    if (selectedPoolImage) placePoolImageInSlot(selectedPoolImage, index);
                    else if (image) removeImageFromSlot(index);
                  }}
                >
                  <div className="slot-header">
                    <span className="slot-number">
                      <span className="slot-num-badge">{index + 1}</span>
                      Scene {index + 1}
                    </span>
                    {validation === "correct" && <span className="slot-badge correct">✓</span>}
                    {validation === "incorrect" && <span className="slot-badge incorrect">✗</span>}
                  </div>

                  <div className="slot-body">
                    {image ? (
                      <div className="slot-image-wrapper">
                        <img
                          src={image}
                          alt={`Scene ${index + 1}`}
                          draggable
                          onDragStart={(e) => handleDragStart(e, image, "slot", index)}
                        />
                        <button
                          type="button"
                          className="remove-slot-image"
                          onClick={(e) => { e.stopPropagation(); removeImageFromSlot(index); }}
                          aria-label="Remove"
                        >&times;</button>
                      </div>
                    ) : (
                      <div className="slot-placeholder">
                        <span className="placeholder-icon">🖼️</span>
                        <span className="placeholder-text">{selectedPoolImage ? "Click to place" : "Drag here"}</span>
                      </div>
                    )}
                  </div>

                  {scenePrompt && (
                    <div className="slot-footer">
                      <p className="slot-prompt">{scenePrompt}</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── Picture pool ── */}
          <div className="sorting-pool-section">
            <div className="sorting-pool-header">
              <h2>📷 Picture Bank</h2>
              <p className="pool-helper-text">
                {selectedPoolImage
                  ? "Click a scene slot above to place this picture."
                  : shuffledPool.length === 0
                    ? "All pictures placed — verify below!"
                    : "Drag a picture to a slot, or click to select then click a slot."}
              </p>
            </div>
            <div className="sorting-pool" onDragOver={handleDragOver} onDrop={handleDropToPool}>
              {shuffledPool.length === 0 ? (
                <div className="pool-empty-state">
                  <span className="star-icon">✨</span>
                  <p>All pictures placed!</p>
                </div>
              ) : (
                shuffledPool.map((image) => (
                  <div
                    key={image}
                    className={`sorting-pool-card ${selectedPoolImage === image ? "selected" : ""}`}
                    draggable
                    onDragStart={(e) => handleDragStart(e, image, "pool")}
                    onClick={() => setSelectedPoolImage(selectedPoolImage === image ? null : image)}
                  >
                    <img src={image} alt="Story picture" />
                    <span className="drag-handle">{selectedPoolImage === image ? "✓ Selected" : "Drag · Click"}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* ── Actions ── */}
          <div className="sorting-actions">
            <button type="button" className="btn-reset-sorting" onClick={resetSorting}>
              ↺ Reset
            </button>

            {validationStates.some((s) => s === "correct") && !validationStates.includes("incorrect") && placedImages.every(Boolean) ? (
              <button type="button" className="btn-start-speaking" onClick={() => setPhase("conceptmap")}>
                Continue to Vocabulary Map →
              </button>
            ) : (
              <button
                type="button"
                className="btn-verify-sorting"
                onClick={checkSequence}
                disabled={placedImages.some((img) => img === null)}
              >
                Verify Sequence
              </button>
            )}

            <button type="button" className="btn-skip-sorting" onClick={() => setPhase("conceptmap")}>
              Skip
            </button>
          </div>
        </section>
      )}

      {phase === "conceptmap" && (
        <section className="conceptmap-phase">
          <div className="conceptmap-phase-header">
            <p className="eyebrow">Step 2 · Vocabulary Map</p>
            <h1>Match Words to Scenes</h1>
            <p className="conceptmap-phase-sub">Drag each word from the bank into the correct scene box</p>
          </div>
          <StoryConceptMap topic={topic} defaultOpen />
          <div className="conceptmap-phase-actions">
            <button className="btn-back-phase" onClick={() => setPhase("sorting")}>
              ← Back to Scenes
            </button>
            <button className="btn-next-phase" onClick={() => setPhase("practice")}>
              Continue to Speaking →
            </button>
          </div>
        </section>
      )}

      {phase === "practice" && (
        <>
          {/* ── Scene selector strip ── */}
          <div className="practice-scene-strip">
            {topic.images.map((img, idx) => (
              <button
                type="button"
                key={img}
                className={`practice-scene-thumb${idx === selectedImageIndex ? " active" : ""}`}
                onClick={() => { onImageChange(img); onImageSelect(idx); }}
                disabled={isBusy}
              >
                <img src={img} alt={`Scene ${idx + 1}`} />
                <span>Scene {idx + 1}</span>
              </button>
            ))}
          </div>

          {/* ── Main two-column workspace ── */}
          <div className="practice-workspace">

            {/* Left: scene image + vocab chips + record button */}
            <div className="practice-scene-panel">
              <div className="practice-scene-image-wrap">
                <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
                <div className="practice-scene-badge">
                  Scene {selectedImageIndex + 1} / {topic.images.length}
                  {topic.prompts?.[selectedImageIndex] && (
                    <span> · {topic.prompts[selectedImageIndex]}</span>
                  )}
                </div>
              </div>

              {selectedVocabulary.length > 0 && (
                <div className="practice-vocab-ref">
                  <p className="practice-vocab-heading">📚 Scene vocabulary</p>
                  <div className="practice-vocab-chips">
                    {selectedVocabulary.map(w => <span key={w}>{w}</span>)}
                  </div>
                </div>
              )}

              <div className="practice-record-area">
                <button
                  type="button"
                  onClick={handlePrimaryRecordingAction}
                  disabled={recordingButtonDisabled}
                  className={`btn-practice-record${isRecording ? " is-recording" : ""}`}
                >
                  {isRecording ? "⏹ Stop Recording" : "🎙 Record"}
                </button>
                {isRecording && (
                  <div className="practice-timer">
                    <span>{recordingDuration}s</span>
                    {selectedModel === "webspeech" && (
                      <span className="practice-silence">silence {silenceDuration}s / 7s</span>
                    )}
                  </div>
                )}
                <label className={`btn-practice-upload${isBusy ? " disabled" : ""}`} role="button" tabIndex={isBusy ? -1 : 0}>
                  Upload audio
                  <input className="submit-voice-input" type="file" accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg" onChange={handleSubmitVoiceFile} disabled={isBusy} />
                </label>
                {submittedAudioName && <p className="submitted-audio-name">✓ {submittedAudioName}</p>}
              </div>
            </div>

            {/* Right: story guide */}
            <div className="practice-guide-panel">
              <div className="practice-guide-header">
                <span>🗺️</span>
                <div>
                  <h3>Story Guide</h3>
                  <p>Use your vocabulary map to build one or two sentences, then record.</p>
                </div>
              </div>

              <div className="practice-guide-qs">
                <div className="practice-guide-q">
                  <span className="guide-q-zh">誰?</span>
                  <span className="guide-q-en">Who is in this scene?</span>
                </div>
                <div className="practice-guide-q">
                  <span className="guide-q-zh">在哪裡?</span>
                  <span className="guide-q-en">Where are they?</span>
                </div>
                <div className="practice-guide-q">
                  <span className="guide-q-zh">做什麼?</span>
                  <span className="guide-q-en">What are they doing?</span>
                </div>
              </div>

              <div className="practice-chips-group">
                <p>Sentence starters</p>
                <div>
                  {sentenceStarters.map(s => <span key={s} className="practice-chip">{s}</span>)}
                </div>
              </div>

              <div className="practice-chips-group">
                <p>Connectors</p>
                <div>
                  {storyConnectors.map(c => <span key={c} className="practice-chip">{c}</span>)}
                </div>
              </div>

              <details className="practice-model-picker">
                <summary>Recording options</summary>
                <select
                  value={selectedModel}
                  onChange={e => setSelectedModel(e.target.value as SpeechModel)}
                  disabled={isBusy}
                >
                  <option value="webspeech">Browser (Traditional Chinese)</option>
                  <option value="ctwhisper">Whisper (Chinese / Taiwanese)</option>
                  <option value="vibevoice">VibeVoice-ASR (local file)</option>
                </select>
              </details>
            </div>
          </div>

          {(isTranscribing || isAnalyzing) && (
            <p className="loading">
              {isTranscribing ? "Transcribing speech…" : "Running Praat analysis…"}
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
        </>
      )}
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
