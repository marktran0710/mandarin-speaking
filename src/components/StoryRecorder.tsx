import {
  type ChangeEvent,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";
import {
  canUseDatabase,
  createStorySubmission,
  type SceneSubmission,
  type StoryFeedback,
} from "../services/database";
import PraatTimeline from "./PraatTimeline";
import StoryConceptMap from "./StoryConceptMap";
import StoryFeedbackCard from "./StoryFeedbackCard";
import { toPinyin } from "../utils/pinyin";
import "./StoryRecorder.css";
import { BiLabel, BiText } from "./BiLabel";
import "./BiLabel.css";
import { SkillFocusLabel } from "./TopicSelector";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

type SpeechModel = "webspeech" | "ctwhisper" | "groq" | "vibevoice";

interface AiProviderOption {
  id: string;
  label: string;
  available: boolean;
}

interface VocabGroup {
  name: string;
  words: string[];
}

interface Topic {
  id: string;
  name: string;
  description?: string;
  skillFocus?: string;
  level?: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
  grammarPatterns?: Record<number, string>;
  grammarExamples?: Record<number, string>;
  vocabularyPinyin?: Record<number, string[]>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenScripts?: Record<number, string>;
  linear?: boolean;
  lessonNumber?: number | null;
  narrativeMode?: "story" | "describe" | "listen_retell";
  firstFrameIsExample?: boolean;
}

interface PauseAnalysis {
  duration: number;
  utterance_count: number;
  pause_count: number;
  total_pause_duration: number;
  longest_pause: number;
  speech_ratio: number;
}

interface PraatMetrics {
  transcription?: string;
  transcription_model?: string;
  pitch_contour: Array<[number, number]>;
  word_prosody?: WordProsody[];
  detected_tone: number;
  tone_accuracy: number;
  formants: Record<string, number>;
  vowel_quality?: string;
  speech_rate: number;
  fluency_score: number;
  pitch_statistics: Record<string, number>;
  tone_direction?: string;
  pause_analysis?: PauseAnalysis;
  feedback: string;
  ai_feedback?: LanguageFeedback;
}

interface WordProsody {
  token: string;
  index: number;
  start_time: number;
  end_time: number;
  pitch_contour: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  mean_pitch: number;
  pitch_range: number;
  start_pitch: number;
  end_pitch: number;
  contour_shape: string;
  feedback: string;
  expected_tones?: number[];
  tone_accuracy?: number;
}

interface LanguageFeedback {
  provider: string;
  vocabulary_coverage: {
    score: number;
    used: string[];
    missing: string[];
    feedback: string;
  };
  coherence: {
    score: number;
    feedback: string;
    corrections: string[];
  };
  pronunciation_note: {
    score: number;
    feedback: string;
  };
  content_accuracy?: {
    score: number;
    feedback: string;
    matched_details: string[];
    missed_details: string[];
    accepted: boolean;
    judged: boolean;
  };
  corrective_feedback?: {
    errors: string[];
    hint: string;
    reveal_answer: boolean;
    correct_version: string;
  };
  improved_version: string;
  practice_prompt: string;
  // legacy fields kept for backward compat
  fluency?: { score: number; feedback: string };
  grammar?: { score: number; feedback: string; corrections: string[] };
  vocabulary?: { score: number; feedback: string; suggestions: string[] };
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
  }) => Promise<string | undefined> | void;
  enableSorting?: boolean;
  studentName?: string;
}

export default function StoryRecorder({
  topic,
  selectedImage,
  selectedImageIndex,
  onImageSelect,
  onImageChange,
  onAddRecord,
  enableSorting = false,
  studentName = "Student",
}: StoryRecorderProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<SpeechModel>("webspeech");
  const [aiProvider, setAiProvider] = useState<string>("");
  const [aiProviders, setAiProviders] = useState<AiProviderOption[]>([]);
  const [silenceDuration, setSilenceDuration] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);

  // Per-scene result maps — keyed by image index so switching scenes restores
  // the last analysis result for that scene instead of showing a blank state.
  const [praatMetricsMap, setPraatMetricsMap] = useState<Record<number, PraatMetrics | null>>({});
  const [analysisAudioBlobMap, setAnalysisAudioBlobMap] = useState<Record<number, Blob | null>>({});
  const [attemptHistoryMap, setAttemptHistoryMap] = useState<
    Record<number, Array<{ tone: number; fluency: number; attempt: number }>>
  >({});
  const [transcriptionsMap, setTranscriptionsMap] = useState<Record<number, TranscriptionItem[]>>({});

  // Derived values for the currently-selected scene — same names as before so
  // all downstream reads require no changes.
  const praatMetrics = praatMetricsMap[selectedImageIndex] ?? null;
  const analysisAudioBlob = analysisAudioBlobMap[selectedImageIndex] ?? null;
  const attemptHistory = attemptHistoryMap[selectedImageIndex] ?? [];
  const transcriptions = transcriptionsMap[selectedImageIndex] ?? [];

  // Setters scoped to the current scene index.
  const setPraatMetrics = (v: PraatMetrics | null) =>
    setPraatMetricsMap((prev) => ({ ...prev, [selectedImageIndex]: v }));
  const setAnalysisAudioBlob = (v: Blob | null) =>
    setAnalysisAudioBlobMap((prev) => ({ ...prev, [selectedImageIndex]: v }));
  const setAttemptHistory = (
    updater: Array<{ tone: number; fluency: number; attempt: number }> |
      ((prev: Array<{ tone: number; fluency: number; attempt: number }>) =>
        Array<{ tone: number; fluency: number; attempt: number }>),
  ) =>
    setAttemptHistoryMap((prev) => ({
      ...prev,
      [selectedImageIndex]:
        typeof updater === "function" ? updater(prev[selectedImageIndex] ?? []) : updater,
    }));
  const setTranscriptions = (
    updater: TranscriptionItem[] | ((prev: TranscriptionItem[]) => TranscriptionItem[]),
  ) =>
    setTranscriptionsMap((prev) => ({
      ...prev,
      [selectedImageIndex]:
        typeof updater === "function" ? updater(prev[selectedImageIndex] ?? []) : updater,
    }));
  // Per-scene progress: keyed by imageIndex
  const [sceneProgress, setSceneProgress] = useState<
    Record<number, { attempts: number; bestTone: number; bestFluency: number }>
  >({});
  const [submittedAudioName, setSubmittedAudioName] = useState("");
  // Completed scene snapshots for story submission
  const [sceneRecordings, setSceneRecordings] = useState<
    Record<number, SceneSubmission>
  >({});
  const [storySubmitted, setStorySubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [storyFeedbackResult, setStoryFeedbackResult] = useState<{
    concatenatedAudioUrl?: string | null;
    storyFeedback?: StoryFeedback | null;
  } | null>(null);
  const [showStartModal, setShowStartModal] = useState(false);

  // Learning phase: overview → sorting → conceptmap → practice
  const [phase, setPhase] = useState<
    "overview" | "sorting" | "conceptmap" | "practice"
  >(enableSorting ? "overview" : "practice");
  const [shuffledPool, setShuffledPool] = useState<string[]>([]);
  const [placedImages, setPlacedImages] = useState<Array<string | null>>([]);
  const [selectedPoolImage, setSelectedPoolImage] = useState<string | null>(
    null,
  );
  const [validationStates, setValidationStates] = useState<
    Array<"correct" | "incorrect" | null>
  >([]);
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

  // When firstFrameIsExample is set, skip frame 0 automatically on entering practice.
  useEffect(() => {
    if (topic.firstFrameIsExample && selectedImageIndex === 0 && topic.images.length > 1) {
      onImageSelect(1);
      onImageChange(topic.images[1]);
    }
  }, [topic.id, topic.firstFrameIsExample]);

  // Load the available AI feedback engines so the student can pick one.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${getBackendUrl()}/api/ai-providers`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !Array.isArray(data.providers)) return;
        setAiProviders(data.providers);
        const groqAvailable = data.providers.some(
          (p: AiProviderOption) => p.id === "groq" && p.available,
        );
        const defaultProvider = (groqAvailable ? "groq" : data.default) || "";
        setAiProvider((prev) => prev || defaultProvider);
        // Sync speech source: if Groq is the default AI provider, use Groq Whisper
        // for transcription too so ASR and feedback both come from the same engine.
        if (groqAvailable) {
          setSelectedModel((prev) => (prev === "webspeech" ? "groq" : prev));
        }
      } catch {
        // Backend unreachable — the picker just stays hidden.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setConceptDraft(createEmptyConceptMapDraft());
  }, [selectedImageIndex, topic.id]);

  // Sorting Challenge Handlers
  const handleDragStart = (
    e: React.DragEvent,
    image: string,
    source: "pool" | "slot",
    index?: number,
  ) => {
    e.dataTransfer.setData(
      "text/plain",
      JSON.stringify({ image, source, index }),
    );
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
      setSortingFeedback(
        "請先把所有圖片放進場景再檢查！Please place all pictures into the scenes before checking!",
      );
      return;
    }

    const nextValidationStates = placedImages.map((image, index) => {
      return image === topic.images[index] ? "correct" : "incorrect";
    });
    setValidationStates(nextValidationStates);

    const isAllCorrect = nextValidationStates.every(
      (state) => state === "correct",
    );
    setSortingAttempts((prev) => prev + 1);

    if (isAllCorrect) {
      setSortingFeedback(
        "完全正確！做得很好，你已經把場景排成正確順序了！Spot on! Excellent job. You have arranged the scenes in the correct order!",
      );
    } else {
      setSortingFeedback(
        "有些圖片順序不對。請檢查紅色標示的場景並再試一次！Some pictures are not in the correct sequence. Check the red highlighted scenes and try again!",
      );
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
          : "無法存取麥克風，請檢查權限設定。 Failed to access microphone. Please check permissions.",
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
        "此瀏覽器不支援 Web Speech API，請使用 Chrome、Edge 或 Safari。 Web Speech API is not supported in this browser. Use Chrome, Edge, or Safari.",
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
      // "network" means the browser can't reach Google's speech servers.
      // "no-speech" / "aborted" are benign. In all these cases the MediaRecorder
      // is still running, so just let the recording finish and fall back to the
      // backend Groq ASR for transcription.
      const nonFatal = ["network", "no-speech", "aborted"];
      if (nonFatal.includes(event.error)) {
        console.warn(`WebSpeech ${event.error} — will use backend ASR instead`);
        recognition.stop(); // triggers onend → stopAudioRecording → Groq ASR
      } else {
        setError(`Speech recognition error: ${event.error}`);
      }
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
      const sceneVocab = (topic.vocabulary[selectedImageIndex] || []).join(
        ", ",
      );
      if (sceneVocab) formData.append("vocab_hint", sceneVocab);

      const response = await fetch(`${backendUrl}/api/transcribe`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "轉錄失敗 Transcription failed");
      }

      const data = await response.json();
      const transcript = (data.text || "").trim();
      if (transcript) {
        addTranscription(transcript);
        currentTranscriptRef.current = transcript;
      }
      await analyzeSpeechAudio(wavBlob, transcript);
    } catch (err) {
      setError(
        formatBackendError(err, BACKEND_URL || "the configured backend"),
      );
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
      const analysisText = transcription.trim();
      formData.append("transcription", analysisText);
      if (asrModel) {
        formData.append("asr_model", asrModel);
      }
      // Scene context for smarter feedback
      const sceneVocab = (topic.vocabulary[selectedImageIndex] || []).join(
        ", ",
      );
      const scenePrompt = topic.prompts?.[selectedImageIndex] || topic.name;
      formData.append("scene_vocabulary", sceneVocab);
      formData.append("scene_prompt", scenePrompt);
      if (selectedImage) {
        formData.append("scene_image_url", selectedImage);
      }
      if (aiProvider) {
        formData.append("ai_provider", aiProvider);
      }
      const sceneGrammarPattern = topic.grammarPatterns?.[selectedImageIndex];
      if (sceneGrammarPattern) {
        formData.append("scene_grammar_pattern", sceneGrammarPattern);
      }
      const sceneSuggestedAnswer = topic.suggestedAnswers?.[selectedImageIndex];
      if (sceneSuggestedAnswer) {
        formData.append("scene_suggested_answer", sceneSuggestedAnswer);
      }
      formData.append("scene_attempt_number", String(attemptHistory.length + 1));

      const response = await fetch(`${backendUrl}/api/analyze`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "Praat 分析失敗 Praat analysis failed");
      }

      const metrics = (await response.json()) as PraatMetrics;
      const finalTranscription = (
        metrics.transcription ||
        analysisText ||
        practiceAnalysisText
      ).trim();
      if (
        finalTranscription &&
        finalTranscription !== currentTranscriptRef.current
      ) {
        currentTranscriptRef.current = finalTranscription;
        if (finalTranscription !== practiceAnalysisText) {
          addTranscription(finalTranscription, recordModel);
        }
      }
      setPraatMetrics(metrics);
      setAnalysisAudioBlob(wavBlob);
      setAttemptHistory((prev) => [
        ...prev,
        {
          tone: Math.round(metrics.tone_accuracy),
          fluency: Math.round(metrics.fluency_score),
          attempt: prev.length + 1,
        },
      ]);
      setSceneProgress((prev) => {
        const curr = prev[selectedImageIndex] ?? {
          attempts: 0,
          bestTone: 0,
          bestFluency: 0,
        };
        return {
          ...prev,
          [selectedImageIndex]: {
            attempts: curr.attempts + 1,
            bestTone: Math.max(
              curr.bestTone,
              Math.round(metrics.tone_accuracy),
            ),
            bestFluency: Math.max(
              curr.bestFluency,
              Math.round(metrics.fluency_score),
            ),
          },
        };
      });

      const recordResult = onAddRecord({
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

      // Save best snapshot for this scene (overwrite if better vocab score)
      const vc = metrics.ai_feedback?.vocabulary_coverage;
      const newSnap: SceneSubmission = {
        sceneIndex: selectedImageIndex,
        imageUrl: selectedImage,
        transcription: finalTranscription,
        vocabUsed: vc?.used ?? [],
        vocabMissing: vc?.missing ?? [],
        vocabScore: vc?.score ?? 0,
        toneAccuracy: Math.round(metrics.tone_accuracy),
        pronScore: averageWordProsodyAccuracy(metrics.word_prosody) ?? 0,
        fluencyScore: Math.round(metrics.fluency_score ?? 0),
        audioUrl: "",
      };
      setSceneRecordings((prev) => {
        const existing = prev[selectedImageIndex];
        if (!existing || newSnap.vocabScore >= existing.vocabScore) {
          return { ...prev, [selectedImageIndex]: newSnap };
        }
        return prev;
      });

      // Patch in the backend audio URL once the upload resolves
      const savedAudioUrl = await Promise.resolve(recordResult);
      if (savedAudioUrl) {
        setSceneRecordings((prev) => {
          const snap = prev[selectedImageIndex];
          if (!snap) return prev;
          return {
            ...prev,
            [selectedImageIndex]: { ...snap, audioUrl: savedAudioUrl },
          };
        });
      }
    } catch (err) {
      setError(
        formatBackendError(err, BACKEND_URL || "the configured backend"),
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleSubmitVoiceFile = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    if (!file.type.startsWith("audio/") && !hasAudioFileExtension(file.name)) {
      setError(`請上傳音訊檔案。不支援「${file.name}」。 Submit an audio file. "${file.name}" is not supported.`);
      return;
    }

    setError(null);
    setPraatMetrics(null);
    setAnalysisAudioBlob(null);
    setSubmittedAudioName(file.name);
    currentTranscriptRef.current = "";
    recordingStartRef.current = Date.now();
    setRecordingDuration(0);

    const uploadModel = selectedModel === "webspeech" ? "groq" : selectedModel;
    await analyzeSpeechAudio(file, "", uploadModel, uploadModel);
  };

  const addTranscription = (
    text: string,
    model: SpeechModel = selectedModel,
  ) => {
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
      1: "一聲 - 高平 Tone 1 - High Level (ma1)",
      2: "二聲 - 上升 Tone 2 - Rising (ma2)",
      3: "三聲 - 降升 Tone 3 - Falling-Rising (ma3)",
      4: "四聲 - 下降 Tone 4 - Falling (ma4)",
    };
    return toneNames[tone] || "聲調不明確 No clear tone";
  };

  const isBusy = isRecording || isTranscribing || isAnalyzing;
  const selectedVocabulary = topic.vocabulary[selectedImageIndex] || [];
  const conceptMapText = buildConceptMapText(conceptDraft);
  const practiceAnalysisText =
    conceptMapText || buildPracticeAnalysisText(selectedVocabulary);
  const hasWordProsody = Boolean(praatMetrics?.word_prosody?.length);
  const recordingButtonDisabled = isTranscribing || isAnalyzing;

  const handlePrimaryRecordingAction = () => {
    if (isRecording) {
      stopRecording();
      return;
    }

    startRecording();
  };

  const totalScenes = topic.images.length;
  const completedSceneCount = Object.keys(sceneRecordings).length;
  const allScenesRecorded = completedSceneCount >= totalScenes;

  const handleSubmitStory = useCallback(async () => {
    const scenes = Object.values(sceneRecordings).sort(
      (a, b) => a.sceneIndex - b.sceneIndex,
    );
    const submission = {
      id: `submission-${Date.now()}`,
      storyId: topic.id,
      storyTitle: topic.name,
      studentName,
      submittedAt: new Date().toISOString(),
      scenes,
    };
    try {
      if (canUseDatabase()) {
        const result = await createStorySubmission(submission);
        setStoryFeedbackResult({
          concatenatedAudioUrl: result.concatenatedAudioUrl,
          storyFeedback: result.storyFeedback,
        });
      }
      setStorySubmitted(true);
      setSubmitError(null);
    } catch {
      setSubmitError(
        "Could not submit story — check your connection and try again.",
      );
    }
  }, [sceneRecordings, topic, studentName]);

  const allVocabulary = topic.images.flatMap(
    (_, si) => topic.vocabulary[si] || [],
  );

  const PHASES = [
    { key: "overview", label: <BiLabel k="overview" />, icon: "📖" },
    ...(enableSorting
      ? [{ key: "sorting" as const, label: <BiLabel k="arrange_scenes" />, icon: "🧩" }]
      : []),
    { key: "conceptmap", label: <BiLabel k="vocabulary_map" />, icon: "🗺️" },
    { key: "practice", label: <BiLabel k="speaking" />, icon: "🎙️" },
  ] as const;

  const phaseOrder = PHASES.map((p) => p.key);
  const currentPhaseIdx = phaseOrder.indexOf(phase);

  return (
    <div className="story-recorder">
      {/* ── Phase navigation bar ── */}
      <nav className="phase-nav" aria-label="Progress">
        {PHASES.map((p, i) => {
          const status =
            i < currentPhaseIdx
              ? "done"
              : i === currentPhaseIdx
                ? "active"
                : "upcoming";
          return (
            <div key={p.key} className={`phase-nav-step phase-nav-${status}`}>
              <span className="phase-nav-icon">
                {status === "done" ? "✓" : p.icon}
              </span>
              <span className="phase-nav-label">{p.label}</span>
              {i < PHASES.length - 1 && (
                <span className="phase-nav-arrow">›</span>
              )}
            </div>
          );
        })}
      </nav>

      {phase === "overview" && (
        <section className="story-overview">
          <div className="overview-hero">
            <p className="eyebrow"><BiLabel k="story_challenge" /></p>
            {topic.lessonNumber != null && (
              <span className="lesson-number-badge">
                <BiLabel zh={`第 ${topic.lessonNumber} 課`} en={`Lesson ${topic.lessonNumber}`} />
              </span>
            )}
            <h1 className="overview-title">{topic.name}</h1>
            {topic.description && (
              <p className="overview-desc">{topic.description}</p>
            )}
            {(topic.level || topic.skillFocus) && (
              <div className="overview-meta">
                {topic.level && <span>{topic.level}</span>}
                {topic.skillFocus && <span><SkillFocusLabel skillFocus={topic.skillFocus} /></span>}
              </div>
            )}
          </div>

          {allVocabulary.length > 0 && (
            <div className="overview-vocab-block">
              <h2><BiLabel k="key_vocabulary" /></h2>
              {topic.images.map((_, si) => {
                const sceneWords = topic.vocabulary[si] || [];
                if (sceneWords.length === 0) return null;
                return (
                  <div key={si} className="overview-vocab-scene">
                    <span className="overview-vocab-scene-label">
                      <BiLabel zh={`場景 ${si + 1}`} en={`Scene ${si + 1}`} />
                    </span>
                    <div className="overview-vocab-chips">
                      {sceneWords.map((word, i) => {
                        const py = topic.vocabularyPinyin?.[si]?.[i] || toPinyin(word);
                        return (
                          <span
                            key={`${word}-${i}`}
                            className="overview-vocab-chip"
                          >
                            <span className="vocab-chip-hanzi">{word}</span>
                            {py && (
                              <span className="vocab-chip-pinyin">{py}</span>
                            )}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="overview-steps-block">
            <h2><BiLabel k="your_challenge" /></h2>
            <div className="overview-steps">
              {enableSorting && (
                <div className="overview-step">
                  <span className="overview-step-num">1</span>
                  <div>
                    <strong><BiLabel k="arrange_scenes" /></strong>
                    <p><BiText k="put_the_story_pictures_in_the_right_orde" /></p>
                  </div>
                </div>
              )}
              <div className="overview-step">
                <span className="overview-step-num">{enableSorting ? 2 : 1}</span>
                <div>
                  <strong><BiLabel k="vocabulary_map" /></strong>
                  <p><BiText k="match_key_words_to_each_story_scene" /></p>
                </div>
              </div>
              <div className="overview-step">
                <span className="overview-step-num">{enableSorting ? 3 : 2}</span>
                <div>
                  <strong><BiLabel k="speaking_practice" /></strong>
                  <p><BiText k="record_your_mandarin_story_out_loud" /></p>
                </div>
              </div>
            </div>
          </div>

          <div className="overview-cta">
            <button
              className="btn-start-challenge"
              onClick={() => setShowStartModal(true)}
            >
<BiLabel k="let_s_go" />
            </button>
          </div>
        </section>
      )}

      {showStartModal && (
        <div className="start-practice-modal-overlay" role="dialog" aria-modal="true">
          <div className="start-practice-modal">
            <span className="start-practice-modal-icon">🎬</span>
            <h2><BiLabel k="start_practicing_title" /></h2>
            <ul className="start-practice-modal-list">
              <li><BiText k="create_story_based_on_images" /></li>
              <li><BiText k="for_each_image_record_and_see_feedback" /></li>
              <li><BiText k="complete_when_you_finish_all_images" /></li>
            </ul>
            <button
              type="button"
              className="btn-start-challenge"
              onClick={() => {
                setShowStartModal(false);
                setPhase(enableSorting ? "sorting" : "practice");
              }}
            >
              <BiLabel k="got_it_lets_start" />
            </button>
          </div>
        </div>
      )}

      {phase === "sorting" && (
        <section className="sorting-challenge-container">
          {/* ── Header ── */}
          <div className="sorting-header">
            <div className="sorting-header-copy">
              <p className="eyebrow"><BiLabel k="step_1_arrange_scenes" /></p>
              <h1><BiLabel k="put_the_story_in_order" /></h1>
              <p className="subtitle">
                <BiText k="drag_each_picture_into_the_correct_scene" />
              </p>
            </div>
            <div className="sorting-progress">
              <div className="sorting-progress-label">
                <BiLabel
                  zh={`已放置 ${placedImages.filter(Boolean).length} / ${placedImages.length}`}
                  en={`${placedImages.filter(Boolean).length} / ${placedImages.length} placed`}
                />
              </div>
              <div className="sorting-progress-bar">
                <div
                  className="sorting-progress-fill"
                  style={{
                    width: `${placedImages.length === 0 ? 0 : (placedImages.filter(Boolean).length / placedImages.length) * 100}%`,
                  }}
                />
              </div>
            </div>
          </div>

          {sortingFeedback && (
            <div
              className={`sorting-feedback-banner ${sortingFeedback.includes("Spot on") ? "success" : "info"}`}
            >
              <span className="feedback-icon">
                {sortingFeedback.includes("Spot on") ? "🎉" : "💡"}
              </span>
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
                    if (selectedPoolImage)
                      placePoolImageInSlot(selectedPoolImage, index);
                    else if (image) removeImageFromSlot(index);
                  }}
                >
                  <div className="slot-header">
                    <span className="slot-number">
                      <span className="slot-num-badge">{index + 1}</span>
                      <BiLabel zh={`場景 ${index + 1}`} en={`Scene ${index + 1}`} />
                    </span>
                    {validation === "correct" && (
                      <span className="slot-badge correct">✓</span>
                    )}
                    {validation === "incorrect" && (
                      <span className="slot-badge incorrect">✗</span>
                    )}
                  </div>

                  <div className="slot-body">
                    {image ? (
                      <div className="slot-image-wrapper">
                        <img
                          src={image}
                          alt={`Scene ${index + 1}`}
                          draggable
                          onDragStart={(e) =>
                            handleDragStart(e, image, "slot", index)
                          }
                        />
                        <button
                          type="button"
                          className="remove-slot-image"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeImageFromSlot(index);
                          }}
                          aria-label="Remove"
                        >
                          &times;
                        </button>
                      </div>
                    ) : (
                      <div className="slot-placeholder">
                        <span className="placeholder-icon">🖼️</span>
                        <span className="placeholder-text">
                          {selectedPoolImage ? (
                            <BiLabel k="click_to_place" />
                          ) : (
                            <BiLabel k="drag_here" />
                          )}
                        </span>
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
              <h2>📷 <BiLabel k="picture_bank" /></h2>
              <p className="pool-helper-text">
                {selectedPoolImage ? (
                  <BiText k="click_a_scene_slot_above_to_place_this_p" />
                ) : shuffledPool.length === 0 ? (
                  <BiText k="all_pictures_placed_verify_below" />
                ) : (
                  <BiText k="drag_a_picture_to_a_slot_or_click_to_sel" />
                )}
              </p>
            </div>
            <div
              className="sorting-pool"
              onDragOver={handleDragOver}
              onDrop={handleDropToPool}
            >
              {shuffledPool.length === 0 ? (
                <div className="pool-empty-state">
                  <span className="star-icon">✨</span>
                  <p><BiLabel k="all_pictures_placed" /></p>
                </div>
              ) : (
                shuffledPool.map((image, poolIdx) => (
                  <div
                    key={poolIdx}
                    className={`sorting-pool-card ${selectedPoolImage === image ? "selected" : ""}`}
                    draggable
                    onDragStart={(e) => handleDragStart(e, image, "pool")}
                    onClick={() =>
                      setSelectedPoolImage(
                        selectedPoolImage === image ? null : image,
                      )
                    }
                  >
                    <img src={image} alt="Story picture" />
                    <span className="drag-handle">
                      {selectedPoolImage === image ? (
                        <BiLabel k="selected" />
                      ) : (
                        <BiLabel k="drag_click" />
                      )}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* ── Actions ── */}
          <div className="sorting-actions">
            <button
              type="button"
              className="btn-reset-sorting"
              onClick={resetSorting}
            >
↺ <BiLabel k="reset" />
            </button>

            {validationStates.some((s) => s === "correct") &&
            !validationStates.includes("incorrect") &&
            placedImages.every(Boolean) ? (
              <button
                type="button"
                className="btn-start-speaking"
                onClick={() => setPhase("conceptmap")}
              >
                <BiLabel k="continue_to_vocabulary_map" />
              </button>
            ) : (
              <button
                type="button"
                className="btn-verify-sorting"
                onClick={checkSequence}
                disabled={placedImages.some((img) => img === null)}
              >
                <BiLabel k="verify_sequence" />
              </button>
            )}

            <button
              type="button"
              className="btn-skip-sorting"
              onClick={() => setPhase("practice")}
            >
              <BiLabel k="skip" />
            </button>
          </div>
        </section>
      )}

      {false && phase === "conceptmap" && (
        <section className="conceptmap-phase">
          <div className="conceptmap-phase-header">
            <p className="eyebrow"><BiLabel k="step_2_vocabulary_map" /></p>
            <h1><BiLabel k="grammar_pattern_canvas" /></h1>
            <p className="conceptmap-phase-sub">
              <BiText k="drag_each_word_into_its_sentence_role_su" />
            </p>
          </div>
          <StoryConceptMap topic={topic} defaultOpen />
          <div className="conceptmap-phase-actions">
            {enableSorting && (
              <button
                className="btn-back-phase"
                onClick={() => setPhase("sorting")}
              >
                <BiLabel k="back_to_scenes" />
              </button>
            )}
            <button
              className="btn-next-phase"
              onClick={() => setPhase("practice")}
            >
              <BiLabel k="continue_to_speaking" />
            </button>
          </div>
        </section>
      )}

      {phase === "practice" && (
        <>
          {/* ── Teacher example frame (read-only, shown before recording starts) ── */}
          {topic.firstFrameIsExample && topic.images.length > 1 && (
            <div className="example-frame-panel">
              <div className="example-frame-label">
                <span className="example-frame-icon">🎯</span>
                <BiLabel zh="老師示範" en="Teacher Model Example" />
              </div>
              <div className="example-frame-body">
                {topic.images[0] && (
                  <img
                    src={topic.images[0]}
                    alt="Teacher example"
                    className="example-frame-image"
                  />
                )}
                <div className="example-frame-content">
                  {topic.prompts?.[0] && (
                    <p className="example-frame-prompt">{topic.prompts[0]}</p>
                  )}
                  {(topic.listenAudioUrls?.[0]) && (
                    <audio
                      controls
                      src={topic.listenAudioUrls[0]}
                      className="example-frame-audio"
                    />
                  )}
                  {(topic.suggestedAnswers?.[0] || topic.listenScripts?.[0]) && (
                    <div className="example-frame-script-block">
                      <p className="example-frame-script-label">
                        <BiLabel zh="示範腳本" en="Model script" />
                      </p>
                      <p className="example-frame-script" lang="zh-TW">
                        {topic.suggestedAnswers?.[0] || topic.listenScripts?.[0]}
                      </p>
                    </div>
                  )}
                  {(topic.vocabulary?.[0] ?? []).length > 0 && (
                    <div className="example-frame-vocab">
                      {topic.vocabulary[0].map((w) => (
                        <span key={w} className="vocab-chip">{w}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── Scene selector strip ── */}
          <div className="practice-scene-strip">
            {topic.images.map((img, idx) => {
              if (topic.firstFrameIsExample && idx === 0) return null;
              const prog = sceneProgress[idx];
              const ready = prog ? sceneReady(prog) : false;
              const started = prog && prog.attempts > 0;
              return (
                <button
                  type="button"
                  key={idx}
                  className={`practice-scene-thumb${idx === selectedImageIndex ? " active" : ""}${ready ? " scene-ready" : ""}`}
                  onClick={() => {
                    onImageChange(img);
                    onImageSelect(idx);
                    currentTranscriptRef.current = "";
                  }}
                  disabled={isBusy}
                >
                  <img src={img} alt={`Scene ${idx + 1}`} />
                  <BiLabel zh={`場景 ${idx + 1}`} en={`Scene ${idx + 1}`} />
                  <span
                    className={`scene-badge ${ready ? "badge-ready" : started ? "badge-progress" : "badge-empty"}`}
                  >
                    {ready ? "✓" : started ? `${prog.attempts}×` : "○"}
                  </span>
                </button>
              );
            })}
          </div>

          {/* ── Scene readiness banner ── */}
          {(() => {
            const prog = sceneProgress[selectedImageIndex];
            if (!prog) return null;
            const ready = sceneReady(prog);
            const nextIdx = selectedImageIndex + 1;
            const hasNext = nextIdx < topic.images.length;
            if (ready && hasNext) {
              return (
                <div className="scene-ready-banner">
                  <div>
                    <strong><BiLabel zh={`場景 ${selectedImageIndex + 1} 完成`} en={`Scene ${selectedImageIndex + 1} complete`} /></strong>
                    <p>
                      <BiLabel
                        zh={`最佳聲調：${prog.bestTone}% · ${prog.attempts} 次嘗試`}
                        en={`Best tone: ${prog.bestTone}% · ${prog.attempts} attempt${prog.attempts > 1 ? "s" : ""}`}
                      />
                    </p>
                  </div>
                  <button
                    type="button"
                    className="scene-next-btn"
                    onClick={() => {
                      const nextImg = topic.images[nextIdx];
                      onImageChange(nextImg);
                      onImageSelect(nextIdx);
                      currentTranscriptRef.current = "";
                    }}
                  >
                    <BiLabel k="next_scene" />
                  </button>
                </div>
              );
            }
            if (ready && !hasNext) {
              return (
                <div className="scene-ready-banner scene-story-done">
                  <strong><BiLabel k="all_scenes_practiced" /></strong>
                  <p>
                    <BiText k="you_ve_completed_the_full_story_review_y" />
                  </p>
                </div>
              );
            }
            if (!ready && prog.attempts > 0) {
              const charCount = (praatMetrics?.transcription || "").replace(
                /[^一-鿿]/g,
                "",
              ).length;
              const threshold = charCount <= 6 ? 70 : 65;
              const best = charCount <= 6 ? prog.bestTone : prog.bestFluency;
              const gap = threshold - best;
              return (
                <div className="scene-progress-hint">
                  {gap > 0 ? (
                    <BiLabel
                      zh={`還需要 ${gap} 分才能解鎖下一場景 — 繼續加油。`}
                      en={`${gap} more points needed to unlock the next scene — keep going.`}
                    />
                  ) : (
                    <BiLabel k="keep_practicing_try_to_make_the_tone_sha" />
                  )}
                </div>
              );
            }
            return null;
          })()}

          {/* ── Main two-column workspace ── */}
          <div className="practice-workspace">
            {/* Left: scene image + vocab chips + record button */}
            <div className="practice-scene-panel">
              <div className="practice-scene-image-wrap">
                <img
                  src={selectedImage}
                  alt={`Scene ${selectedImageIndex + 1}`}
                />
              </div>

              {(topic.grammarPatterns?.[selectedImageIndex] || topic.grammarExamples?.[selectedImageIndex]) && (
                <div className="practice-grammar-hint">
                  <p className="block-label practice-grammar-label">
                    <BiLabel k="grammar_pattern_to_use" />
                  </p>
                  {topic.grammarPatterns?.[selectedImageIndex] && (
                    <span className="practice-grammar-pattern">
                      {topic.grammarPatterns[selectedImageIndex]}
                    </span>
                  )}
                  {topic.grammarExamples?.[selectedImageIndex] && (
                    <span className="practice-grammar-example">
                      {topic.grammarExamples[selectedImageIndex]}
                    </span>
                  )}
                </div>
              )}


              {selectedVocabulary.length > 0 && (
                <div className="practice-vocab-ref">
                  <p className="block-label practice-vocab-heading">
                    <BiLabel k="scene_vocabulary" />
                    {praatMetrics && (
                      <span className="vocab-check-hint">
                        {" "}
                        — <BiLabel k="check_which_words_you_used" />
                      </span>
                    )}
                  </p>
                  <div className="practice-vocab-chips">
                    {selectedVocabulary.map((w, wi) => {
                      // Prefer backend phonetic-match result; fall back to character search
                      const aiVC =
                        praatMetrics?.ai_feedback?.vocabulary_coverage;
                      let used: boolean | null = null;
                      if (aiVC) {
                        if (aiVC.used?.includes(w)) used = true;
                        else if (aiVC.missing?.includes(w)) used = false;
                      } else if (praatMetrics?.transcription) {
                        used = praatMetrics.transcription.includes(w);
                      }
                      return (
                        <span
                          key={w}
                          className={`vocab-chip ${used === true ? "vocab-used" : used === false ? "vocab-missed" : ""}`}
                          title={
                            used === true
                              ? "你使用了這個詞彙 ✓ You used this word"
                              : used === false
                                ? "試著加入這個詞彙 Try to include this word"
                                : ""
                          }
                        >
                          <span className="vocab-chip-row">
                            <span className="vocab-chip-hanzi">{w}</span>
                            {used === true && (
                              <span className="vocab-tick">✓</span>
                            )}
                            {used === false && (
                              <span className="vocab-tick">✗</span>
                            )}
                          </span>
                          {(() => {
                            const py = topic.vocabularyPinyin?.[selectedImageIndex]?.[wi] || toPinyin(w);
                            return py ? <span className="vocab-chip-pinyin">{py}</span> : null;
                          })()}
                        </span>
                      );
                    })}
                  </div>
                  {praatMetrics?.ai_feedback?.vocabulary_coverage && (
                    <p className="vocab-coverage-line">
                      {(() => {
                        const vc =
                          praatMetrics.ai_feedback!.vocabulary_coverage!;
                        const usedList = vc.used ?? [];
                        const missedList = vc.missing ?? [];
                        if (missedList.length === 0)
                          return (
                            <BiLabel k="all_vocabulary_words_used_excellent" />
                          );
                        if (usedList.length === 0)
                          return (
                            <BiLabel
                              zh={`試著加入：${missedList.slice(0, 3).join("、")}`}
                              en={`Try to include: ${missedList.slice(0, 3).join("、")}`}
                            />
                          );
                        return (
                          <BiLabel
                            zh={`已使用 ${usedList.length}/${selectedVocabulary.length}。試著加入：${missedList.slice(0, 2).join("、")}`}
                            en={`Used ${usedList.length}/${selectedVocabulary.length}. Try adding: ${missedList.slice(0, 2).join("、")}`}
                          />
                        );
                      })()}
                    </p>
                  )}
                </div>
              )}

            </div>

            {/* Right: record controls */}
            <div className="practice-guide-panel">
              <div className="practice-guide-header">
                <span>🎙️</span>
                <div>
                  <h3><BiLabel k="record_your_story" /></h3>
                </div>
              </div>

              <div className="practice-record-area">
                {aiProviders.length > 0 && (
                  <div
                    className="record-engine-switch"
                    role="group"
                    aria-label="AI feedback engine"
                  >
                    <label className="record-engine-switch-label" htmlFor="ai-engine-select">
                      <BiLabel k="ai_engine" />
                    </label>
                    <select
                      id="ai-engine-select"
                      className="record-engine-switch-options"
                      value={aiProvider}
                      onChange={(e) => {
                        const next = e.target.value;
                        setAiProvider(next);
                        // Groq handles Whisper transcription as well as feedback,
                        // so align the speech source automatically.
                        if (next === "groq") setSelectedModel("groq");
                      }}
                      disabled={isBusy}
                    >
                      {aiProviders.map((p) => (
                        <option
                          key={p.id}
                          value={p.id}
                          disabled={!p.available || p.id === "local"}
                        >
                          {p.label}
                          {p.available && p.id !== "local" ? "" : " 🔒"}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <button
                  type="button"
                  onClick={handlePrimaryRecordingAction}
                  disabled={recordingButtonDisabled}
                  className={`btn-practice-record${isRecording ? " is-recording" : ""}`}
                >
                  {isRecording ? <BiLabel k="stop_recording" /> : <BiLabel k="record" />}
                </button>
                {isRecording && (
                  <div className="practice-timer">
                    <span>{recordingDuration}s</span>
                    {selectedModel === "webspeech" && (
                      <span className="practice-silence">
                        <BiLabel zh={`靜音 ${silenceDuration}s / 7s`} en={`silence ${silenceDuration}s / 7s`} />
                      </span>
                    )}
                  </div>
                )}
                <label
                  className={`btn-practice-upload${isBusy ? " disabled" : ""}`}
                  role="button"
                  tabIndex={isBusy ? -1 : 0}
                >
                  <BiLabel k="upload_audio" />
                  <input
                    className="submit-voice-input"
                    type="file"
                    accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg"
                    onChange={handleSubmitVoiceFile}
                    disabled={isBusy}
                  />
                </label>
                {submittedAudioName && (
                  <p className="submitted-audio-name">✓ {submittedAudioName}</p>
                )}
              </div>

              <div className="transcriptions">
                <h2><BiLabel k="speech_transcript" /></h2>
                {praatMetrics?.transcription && (
                  <div className="transcription-item transcription-asr-primary">
                    <div className="item-header">
                      <span className="time"><BiLabel k="asr_result" /></span>
                      <span className="model-badge">
                        {(praatMetrics.transcription_model || "ASR").toUpperCase()}
                      </span>
                    </div>
                    <p lang="zh-TW">{praatMetrics.transcription}</p>
                  </div>
                )}
                {transcriptions.length === 0 && !praatMetrics?.transcription ? (
                  <p className="empty">
                    <BiText k="your_transcript_will_appear_after_record" />
                  </p>
                ) : (
                  <div className="transcriptions-scroll">
                    {transcriptions.map((item) => (
                      <div
                        key={`${item.timestamp}-${item.text}`}
                        className="transcription-item"
                      >
                        <div className="item-header">
                          <span className="time">{item.timestamp}</span>
                          <span className="model-badge">
                            {item.model.toUpperCase()}
                          </span>
                        </div>
                        <p>{item.text}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <details className="practice-model-picker">
                <summary><BiLabel k="recording_options" /></summary>
                <label className="practice-model-label" htmlFor="speech-source">
                  <BiLabel k="speech_source" />
                </label>
                <select
                  id="speech-source"
                  value={selectedModel}
                  onChange={(e) =>
                    setSelectedModel(e.target.value as SpeechModel)
                  }
                  disabled={isBusy}
                >
                  <option value="webspeech">
                    瀏覽器（繁體中文） Browser (Traditional Chinese)
                  </option>
                  <option value="groq">Groq Whisper（免費，雲端） Groq Whisper (free, cloud)</option>
                  <option value="ctwhisper">
                    Whisper（中文／台語，本地） Whisper (Chinese / Taiwanese, local)
                  </option>
                  <option value="vibevoice">VibeVoice-ASR（本地檔案） VibeVoice-ASR (local file)</option>
                </select>
              </details>
            </div>
          </div>

          {(isTranscribing || isAnalyzing) && (
            <div className="analysis-loading-card">
              <div className="analysis-loading-spinner" />
              <div className="analysis-loading-text">
                <p className="analysis-loading-title">
                  {isTranscribing ? (
                    <BiLabel k="listening_to_your_voice" />
                  ) : (
                    <BiLabel k="analyzing_pronunciation" />
                  )}
                </p>
                <p className="analysis-loading-sub">
                  {isTranscribing ? (
                    <BiLabel k="converting_speech_to_text" />
                  ) : (
                    <BiLabel k="checking_tones_rhythm_and_vocabulary" />
                  )}
                </p>
              </div>
              <div className="analysis-loading-steps">
                <span
                  className={`loading-step ${isTranscribing ? "active" : "done"}`}
                >
                  <BiLabel k="transcribe" />
                </span>
                <span className="loading-step-arrow">→</span>
                <span
                  className={`loading-step ${isAnalyzing && !isTranscribing ? "active" : ""}`}
                >
                  Praat
                </span>
                <span className="loading-step-arrow">→</span>
                <span className="loading-step"><BiLabel k="feedback" /></span>
              </div>
            </div>
          )}
          {error && <p className="error">{error}</p>}

          {praatMetrics && (
            <section className="analysis-panel">
              {/* ── Main grid: left = scores & language feedback, right = playback ── */}
              <div className="ap-grid">
              <div className="ap-feedback-col">
              {/* ── Zone 1: Summary ─────────────────────────────────────── */}
              <FeedbackSummary
                praatMetrics={praatMetrics}
                attemptHistory={attemptHistory}
                transcription={praatMetrics.transcription || ""}
              />

              {/* ── Indirect corrective feedback: hint-only for the first two
                  attempts; the correct version is revealed only after that. ── */}
              {topic.narrativeMode !== "listen_retell" &&
                (() => {
                  const cf = praatMetrics.ai_feedback?.corrective_feedback;
                  const accepted = isContentAccepted(praatMetrics);
                  const missing =
                    praatMetrics.ai_feedback?.vocabulary_coverage?.missing ?? [];

                  // Already correct — nothing to correct, so stay quiet here;
                  // FeedbackSummary already shows the success state.
                  if (accepted && missing.length === 0) return null;

                  if (cf?.reveal_answer && cf.correct_version) {
                    return (
                      <div className="practice-suggested-answer">
                        <p className="block-label practice-suggested-answer-heading">
                          <BiLabel zh="正確答案" en="Correct version" />
                        </p>
                        {cf.errors.length > 0 && (
                          <p className="practice-suggested-answer-text">
                            <BiLabel zh="可能的錯誤：" en="Possible errors: " />
                            {cf.errors.join("；")}
                          </p>
                        )}
                        <p className="practice-suggested-answer-text">
                          <strong>{cf.correct_version}</strong>
                        </p>
                      </div>
                    );
                  }

                  if (cf && (cf.errors.length > 0 || cf.hint)) {
                    return (
                      <div className="practice-suggested-answer is-hint">
                        <p className="block-label practice-suggested-answer-heading">
                          <BiLabel zh="提示" en="Hint" />
                        </p>
                        {cf.errors.length > 0 && (
                          <p className="practice-suggested-answer-text">
                            <BiLabel zh="可能的錯誤：" en="Possible errors: " />
                            {cf.errors.join("；")}
                          </p>
                        )}
                        {cf.hint && (
                          <p className="practice-suggested-answer-text">{cf.hint}</p>
                        )}
                        <p className="practice-suggested-answer-text">
                          <BiLabel zh="請再試一次。" en="Please try again." />
                        </p>
                      </div>
                    );
                  }
                  return null;
                })()}
              </div>{/* /ap-feedback-col */}

              {/* ── Right column: scene thumbnail + playback + positive signals ── */}
              <div className="ap-sidebar-col">
              {/* Scene thumbnail */}
              <div className="ap-scene-card">
                <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} className="ap-scene-img" />
                <div className="ap-scene-label">
                  <span><BiLabel zh={`場景 ${selectedImageIndex + 1}`} en={`Scene ${selectedImageIndex + 1}`} /></span>
                  {sceneProgress[selectedImageIndex] && (
                    <span className="ap-scene-attempts">
                      <BiLabel
                        zh={`${sceneProgress[selectedImageIndex].attempts} 次嘗試`}
                        en={`${sceneProgress[selectedImageIndex].attempts} attempt${sceneProgress[selectedImageIndex].attempts > 1 ? "s" : ""}`}
                      />
                    </span>
                  )}
                </div>
              </div>
              {/* ── Vocabulary for this scene ── */}
              {selectedVocabulary.length > 0 && (
                <div className="ap-vocab-ref">
                  <p className="block-label ap-vocab-heading"><BiLabel k="scene_vocabulary" /></p>
                  <div className="ap-vocab-chips">
                    {selectedVocabulary.map((w, wi) => {
                      const aiVC = praatMetrics?.ai_feedback?.vocabulary_coverage;
                      let used: boolean | null = null;
                      if (aiVC) {
                        if (aiVC.used?.includes(w)) used = true;
                        else if (aiVC.missing?.includes(w)) used = false;
                      }
                      const py = topic.vocabularyPinyin?.[selectedImageIndex]?.[wi] || toPinyin(w);
                      return (
                        <span
                          key={w}
                          className={`vocab-chip ${used === true ? "vocab-used" : used === false ? "vocab-missed" : ""}`}
                        >
                          <span className="vocab-chip-row">
                            <span className="vocab-chip-hanzi">{w}</span>
                            {used === true && <span className="vocab-tick">✓</span>}
                            {used === false && <span className="vocab-tick">✗</span>}
                          </span>
                          {py && <span className="vocab-chip-pinyin">{py}</span>}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ── Zone 3: Listen back ──────────────────────────────────── */}
              <div className="listen-try-zone">
                {analysisAudioBlob && (
                  <RecordingPlayback blob={analysisAudioBlob} />
                )}
              </div>

              {(praatMetrics.ai_feedback?.vocabulary_coverage?.missing
                ?.length ?? 0) === 0 && (
                <div className="try-again-complete">
                  <span className="try-again-complete-icon">✓</span>
                  <div>
                    <p className="try-again-complete-title">
                      <BiLabel k="all_vocabulary_words_used" />
                    </p>
                    <p className="try-again-complete-hint">
                      <BiText k="now_work_on_pronunciation_record_again_a" />
                    </p>
                  </div>
                </div>
              )}
              </div>{/* /ap-sidebar-col */}
              </div>{/* /ap-grid */}

              <div className="word-prosody-section">
                <div className="word-prosody-header">
                  <h3><BiLabel k="character_by_character_prosody" /></h3>
                  <p><BiText k="pitch_movement_estimated_for_each_mandar" /></p>
                </div>
                {hasWordProsody ? (
                  <div className="word-prosody-grid">
                    {praatMetrics.word_prosody?.map((item) => (
                      <WordProsodyCard
                        key={`${item.token}-${item.index}`}
                        item={item}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="word-prosody-empty">
                    <strong><BiLabel k="no_character_feedback_yet" /></strong>
                    <p>
                      <BiText k="needs_a_clear_pitch_contour_and_transcri" />
                    </p>
                  </div>
                )}
              </div>

              {/* ── Zone 4: Advanced details (collapsed) ────────────────── */}
              <details className="advanced-praat-details">
                <summary><BiLabel k="advanced_analysis_details" /></summary>

                <div className="metrics-section">
                  <div className="metric-card tone-card">
                    <div className="metric-label"><BiLabel k="dominant_pitch_shape" /></div>
                    <div className="metric-value compact">
                      {getToneName(praatMetrics.detected_tone)}
                    </div>
                    <div className="metric-subtext">
                      <BiLabel k="tone_accuracy_score_shown_in_the_summary" />
                    </div>
                  </div>
                  <div className="metric-card rate-card">
                    <div className="metric-label"><BiLabel k="speech_rate" /></div>
                    <div className="metric-value">
                      {praatMetrics.speech_rate.toFixed(1)}
                    </div>
                    <div className="metric-subtext">
                      {praatMetrics.speech_rate < 2.5 ? (
                        <BiLabel k="too_slow_add_more_flow" />
                      ) : praatMetrics.speech_rate > 6.5 ? (
                        <BiLabel k="too_fast_slow_each_tone" />
                      ) : (
                        <BiLabel k="syllables_sec_good_pace" />
                      )}
                    </div>
                  </div>
                  {praatMetrics.pause_analysis &&
                  praatMetrics.pause_analysis.duration > 0 ? (
                    <div className="metric-card pause-card">
                      <div className="metric-label"><BiLabel k="pauses" /></div>
                      <div className="metric-value">
                        {praatMetrics.pause_analysis.pause_count}
                      </div>
                      <div className="metric-subtext">
                        {praatMetrics.pause_analysis.pause_count === 0 ? (
                          <BiLabel k="no_long_pauses_smooth_delivery" />
                        ) : praatMetrics.pause_analysis.longest_pause >= 0.8 ? (
                          <BiLabel
                            zh={`最長間隔：${praatMetrics.pause_analysis.longest_pause.toFixed(1)}s`}
                            en={`Longest gap: ${praatMetrics.pause_analysis.longest_pause.toFixed(1)}s`}
                          />
                        ) : (
                          <BiLabel
                            zh={`${praatMetrics.pause_analysis.pause_count} 次短停頓 — 接近流暢`}
                            en={`${praatMetrics.pause_analysis.pause_count} short pause${praatMetrics.pause_analysis.pause_count > 1 ? "s" : ""} — nearly fluent`}
                          />
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="metric-card fluency-card">
                      <div className="metric-label"><BiLabel k="fluency" /></div>
                      <div className="metric-value">
                        {Math.round(praatMetrics.fluency_score)}
                      </div>
                      <div className="metric-bar">
                        <div
                          className="metric-fill"
                          style={{ width: `${praatMetrics.fluency_score}%` }}
                        />
                      </div>
                    </div>
                  )}
                  {praatMetrics.vowel_quality && (
                    <div className="metric-card vowel-card">
                      <div className="metric-label"><BiLabel k="vowel_quality" /></div>
                      <div className="metric-value compact">
                        {praatMetrics.vowel_quality.split(" — ")[0]}
                      </div>
                      <div className="metric-subtext">
                        {praatMetrics.vowel_quality.split(" — ")[1] || ""}
                      </div>
                    </div>
                  )}
                </div>

                <StudentFeedbackCards
                  toneAccuracy={praatMetrics.tone_accuracy}
                  fluencyScore={praatMetrics.fluency_score}
                  speechRate={praatMetrics.speech_rate}
                  wordProsody={praatMetrics.word_prosody || []}
                  pauseAnalysis={praatMetrics.pause_analysis}
                />

                <PraatTimeline
                  audioBlob={analysisAudioBlob}
                  pitchContour={praatMetrics.pitch_contour}
                  wordProsody={praatMetrics.word_prosody}
                  transcription={currentTranscriptRef.current}
                />

                <div className="formants-detail">
                  <h3><BiLabel k="formant_measurements" /></h3>
                  <div className="formants-grid">
                    {["F1", "F2", "F3"].map((f) => (
                      <div className="formant" key={f}>
                        <span>{f}</span>
                        <strong>
                          {Math.round(praatMetrics.formants[f] || 0)} Hz
                        </strong>
                      </div>
                    ))}
                  </div>
                </div>
              </details>
            </section>
          )}

          {/* ── Submit Story ────────────────────────────────────────── */}
          {storySubmitted ? (
            <>
              <div className="story-submit-panel story-submit-success">
                <span className="story-submit-icon">✓</span>
                <div>
                  <p className="story-submit-title"><BiLabel k="story_submitted" /></p>
                  <p className="story-submit-hint">
                    <BiLabel
                      zh={`你的老師現在可以檢視全部 ${totalScenes} 個場景。`}
                      en={`Your teacher can now review all ${totalScenes} scenes.`}
                    />
                  </p>
                </div>
              </div>
              <StoryFeedbackCard
                feedback={storyFeedbackResult?.storyFeedback}
                concatenatedAudioUrl={storyFeedbackResult?.concatenatedAudioUrl}
              />
            </>
          ) : (
            <div className="story-submit-panel">
              <div className="story-submit-progress">
                {topic.images.map((_, si) => (
                  <div
                    key={si}
                    className={`story-submit-dot ${sceneRecordings[si] ? "done" : "pending"}`}
                    title={`場景 ${si + 1}${sceneRecordings[si] ? " ✓ 已完成" : " — 尚未錄音 not yet recorded"} Scene ${si + 1}`}
                  />
                ))}
              </div>
              <p className="story-submit-label">
                {allScenesRecorded ? (
                  <BiLabel k="all_scenes_recorded_ready_to_submit" />
                ) : (
                  <BiLabel
                    zh={`已錄製 ${completedSceneCount} / ${totalScenes} 個場景`}
                    en={`${completedSceneCount} of ${totalScenes} scenes recorded`}
                  />
                )}
              </p>
              {submitError && (
                <p className="story-submit-error">{submitError}</p>
              )}
              <button
                className="btn-submit-story"
                disabled={!allScenesRecorded}
                onClick={handleSubmitStory}
              >
                <BiLabel k="submit_story_to_teacher" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Maps a Mandarin tone number to the TONE_SHAPES key for its target pitch shape. */
const TONE_NUMBER_TO_SHAPE: Record<number, string> = {
  1: "level",
  2: "rising",
  3: "dip",
  4: "falling",
};

/** Actionable improvement tip for this character — only shown when the
 * character actually needs work. Gated directly off item.feedback's own
 * verdict (backend's _word_prosody_feedback), not a separate threshold
 * re-check, so the tip can never disagree with the feedback text shown right
 * above it. When there's an expected Mandarin tone, the tip points at THAT
 * tone's target shape, not whatever (possibly wrong) shape the attempt
 * happened to produce. */
function prosodyImprovementTip(item: WordProsody): string | null {
  const feedback = item.feedback ?? "";

  if (item.expected_tones && item.expected_tones.length > 0) {
    // item.feedback already says "Good match for ..." vs "Recognizable ...
    // but contrast could be sharper" / "Expected ... doesn't match yet" —
    // key off that text directly instead of re-deriving from tone_accuracy.
    if (feedback.startsWith("Good match")) return null;

    // Tone 5 (neutral) has no fixed target shape — it's short, light, and
    // takes its pitch from the preceding syllable — so don't claim "no clear
    // shape detected" (false; a shape WAS detected, it just isn't graded
    // against rising/falling/level/dip the way tones 1-4 are).
    if (item.expected_tones[0] === 5) {
      return "輕聲沒有固定的音高形狀 — 試著把這個字說得更短、更輕。 Neutral tone has no fixed pitch shape — try making this syllable shorter and lighter instead.";
    }

    const targetKey = TONE_NUMBER_TO_SHAPE[item.expected_tones[0]] ?? "variable";
    const target = TONE_SHAPES[targetKey];
    return `目標形狀：${target.tip} 刻意誇大這個音高變化，再說一次。 Target shape: ${target.tip} Exaggerate that pitch movement and try again.`;
  }

  // No expected tone (open-vocabulary): backend only flags a problem when no
  // clear shape was detected, which is the same "variable" case here.
  if (item.contour_shape !== "variable") return null;
  return TONE_SHAPES.variable.drill;
}

function WordProsodyCard({ item }: { item: WordProsody }) {
  const improvementTip = prosodyImprovementTip(item);
  const hasReference = (item.reference_contour?.length ?? 0) > 1;
  return (
    <div className="word-prosody-card">
      <div className="word-prosody-topline">
        <strong>{item.token}</strong>
        <span>{formatContourShape(item.contour_shape)}</span>
      </div>
      <div className="mini-contour" aria-label={`${item.token} pitch contour vs target shape`}>
        <MiniContourChart actual={item.pitch_contour} reference={item.reference_contour} />
      </div>
      {hasReference && (
        <div className="mini-contour-legend">
          <span className="mini-contour-legend-actual">
            <BiLabel zh="你的音高" en="Your pitch" />
          </span>
          <span className="mini-contour-legend-reference">
            <BiLabel zh="目標形狀" en="Target shape" />
          </span>
        </div>
      )}
      <div className="word-prosody-stats">
        <BiLabel zh={`平均 ${Math.round(item.mean_pitch)} Hz`} en={`${Math.round(item.mean_pitch)} Hz avg`} />
        <BiLabel zh={`範圍 ${Math.round(item.pitch_range)} Hz`} en={`${Math.round(item.pitch_range)} Hz range`} />
      </div>
      <p>{item.feedback}</p>
      {improvementTip && (
        <p className="word-prosody-tip">💡 {improvementTip}</p>
      )}
      <WordPracticeDrill word={item} />
    </div>
  );
}

/** Lets a student drill just this one character/word in place, right where its
 * sentence feedback appeared — record it alone as many times as they like and
 * see the chart update, instead of having to re-record the whole sentence to
 * fix one weak syllable. Sends the known token as `transcription`, which makes
 * the backend skip ASR entirely and score the recording directly against this
 * word's real expected tone(s) — so a re-record here is never limited by
 * speech-recognition accuracy. */
function WordPracticeDrill({ word }: { word: WordProsody }) {
  const [open, setOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [attempts, setAttempts] = useState<WordProsody[]>([]);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const latest = attempts[attempts.length - 1];
  const previous = attempts[attempts.length - 2];
  const trend =
    latest && previous
      ? Math.round((latest.tone_accuracy ?? 0) - (previous.tone_accuracy ?? 0))
      : undefined;

  const startRecording = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const preferredType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = new MediaRecorder(stream, preferredType ? { mimeType: preferredType } : undefined);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        const rawBlob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        await analyzeAttempt(rawBlob);
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "無法使用麥克風 Could not access the microphone.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  const analyzeAttempt = async (rawBlob: Blob) => {
    setIsAnalyzing(true);
    try {
      const wavBlob = await convertBlobToWav(rawBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "word-practice.wav");
      formData.append("transcription", word.token);
      formData.append("ai_provider", "local");

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Analysis failed.");
      }

      const data = await response.json();
      const segment: WordProsody | undefined = data.word_prosody?.[0];
      if (!segment) {
        setError(
          "沒聽清楚，靠近麥克風、把音拉長一點再試一次。 Didn't catch enough of that — move closer to the mic and hold the sound a little longer.",
        );
        return;
      }
      setAttempts((prev) => [...prev, segment]);
    } catch (err) {
      setError(formatBackendError(err, BACKEND_URL || "the configured backend"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleImportFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!file.type.startsWith("audio/") && !/\.(wav|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name)) {
      setError(`「${file.name}」不是音訊檔。 "${file.name}" isn't an audio file.`);
      return;
    }

    setError("");
    await analyzeAttempt(file);
  };

  return (
    <div className="word-practice-drill">
      <button
        type="button"
        className="word-practice-toggle"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        {open ? (
          <BiLabel zh="收起單字練習" en="Hide word practice" />
        ) : (
          <BiLabel zh={`🎙 單獨練習「${word.token}」`} en={`🎙 Practice "${word.token}" alone`} />
        )}
      </button>

      {open && (
        <div className="word-practice-panel">
          <div className="word-practice-controls">
            <button
              type="button"
              className={`btn-mini ${isRecording ? "recording" : ""}`}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isAnalyzing}
            >
              {isRecording ? (
                <BiLabel zh="停止" en="Stop" />
              ) : attempts.length > 0 ? (
                <BiLabel zh="再錄一次" en="Record again" />
              ) : (
                <BiLabel zh="錄音" en="Record" />
              )}
            </button>
            <label
              className={`btn-mini btn-mini-secondary word-practice-upload-label ${
                isRecording || isAnalyzing ? "disabled" : ""
              }`}
              role="button"
              tabIndex={isRecording || isAnalyzing ? -1 : 0}
            >
              <BiLabel zh="上傳音檔" en="Upload audio" />
              <input
                type="file"
                accept="audio/*,.wav,.webm,.mp3,.m4a,.ogg,.aac,.flac"
                className="word-practice-upload-input"
                onChange={handleImportFile}
                disabled={isRecording || isAnalyzing}
              />
            </label>
            {isAnalyzing && (
              <span className="word-practice-status">
                <BiLabel zh="分析中…" en="Analyzing…" />
              </span>
            )}
            {attempts.length > 0 && (
              <span className="word-practice-attempt-count">
                <BiLabel zh="第" en="Try" /> {attempts.length}
              </span>
            )}
          </div>

          {error && <p className="word-practice-error">{error}</p>}

          {latest && !isAnalyzing && (
            <div className={`word-practice-result ${scoreBand(latest.tone_accuracy ?? 0)}`}>
              <div className="mini-contour" aria-label={`Practice attempt pitch for ${word.token}`}>
                <MiniContourChart actual={latest.pitch_contour} reference={latest.reference_contour} />
              </div>
              <div className="word-practice-result-meta">
                <strong>{Math.round(latest.tone_accuracy ?? 0)}%</strong>
                {typeof trend === "number" && trend !== 0 && (
                  <em className={trend > 0 ? "trend-up" : "trend-down"}>
                    {trend > 0 ? "↑" : "↓"} {Math.abs(trend)}%
                  </em>
                )}
              </div>
              <p>{latest.feedback}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function scoreBand(score: number): "good" | "ok" | "low" {
  if (score >= 68) return "good";
  if (score >= 48) return "ok";
  return "low";
}

/** Overlays the student's measured pitch curve against the idealized target
 * shape for the expected tone(s) — both scaled to a shared time/pitch range
 * so the two lines are directly comparable, making the exact mismatch
 * (wrong direction, not enough movement, dip too shallow, etc.) visible
 * rather than something the student has to infer from a text description. */
function MiniContourChart({
  actual,
  reference,
}: {
  actual: Array<[number, number]>;
  reference?: Array<[number, number]>;
}) {
  const width = 160;
  const height = 66;
  const padY = 8;

  const points = reference && reference.length > 1 ? [...actual, ...reference] : actual;
  if (points.length < 2) {
    return <svg viewBox={`0 0 ${width} ${height}`} className="mini-contour-svg" aria-hidden="true" />;
  }

  const times = points.map((p) => p[0]);
  const freqs = points.map((p) => p[1]);
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  const minF = Math.min(...freqs);
  const maxF = Math.max(...freqs);
  const timeSpan = Math.max(maxT - minT, 0.001);
  const freqSpan = Math.max(maxF - minF, 1);

  const toPath = (series: Array<[number, number]>) =>
    series
      .map(([t, f], index) => {
        const x = ((t - minT) / timeSpan) * width;
        const y = height - padY - ((f - minF) / freqSpan) * (height - padY * 2);
        return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="mini-contour-svg"
      role="img"
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      {reference && reference.length > 1 && (
        <path d={toPath(reference)} className="mini-contour-reference" fill="none" />
      )}
      {actual.length > 1 && (
        <path d={toPath(actual)} className="mini-contour-actual" fill="none" />
      )}
    </svg>
  );
}

function sceneReady(prog: {
  attempts: number;
  bestTone: number;
  bestFluency: number;
}): boolean {
  // Short-phrase threshold: tone accuracy ≥ 70%
  // Long-sentence threshold: fluency ≥ 65%
  // Override: 4+ attempts always unlocks next scene
  return prog.bestTone >= 70 || prog.bestFluency >= 65 || prog.attempts >= 4;
}

/** Real, measured prosody score — the average per-character tone_accuracy from
 * word_prosody — as opposed to the AI's generic pronunciation_note.score, which
 * isn't grounded in the actual measured pitch data. */
/** Pronunciation feedback only matters once the sentence's meaning is accepted. */
function isContentAccepted(praatMetrics: PraatMetrics): boolean {
  const contentAccuracy = praatMetrics.ai_feedback?.content_accuracy;
  if (!contentAccuracy?.feedback) return true;
  return contentAccuracy.accepted !== false;
}

function averageWordProsodyAccuracy(wordProsody?: WordProsody[]): number | null {
  const accuracies = (wordProsody ?? [])
    .map((item) => item.tone_accuracy)
    .filter((value): value is number => typeof value === "number");
  if (accuracies.length === 0) return null;
  return Math.round(
    accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length,
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
    dip: "低降 Dipping",
    falling: "下降 Falling",
    level: "平直 Level",
    rising: "上升 Rising",
    variable: "變化 Variable",
  };
  return labels[shape] || "變化 Variable";
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
  pauseAnalysis,
}: {
  toneAccuracy: number;
  fluencyScore: number;
  speechRate: number;
  wordProsody: WordProsody[];
  pauseAnalysis?: PauseAnalysis;
}) {
  const focus = getToneFocusItems(wordProsody)[0];

  return (
    <section className="student-feedback-cards" aria-label="Student feedback">
      <div className="student-feedback-card good">
        <BiLabel k="good" />
        <strong>{studentStrength(toneAccuracy, fluencyScore)}</strong>
      </div>
      <div className="student-feedback-card fix">
        <BiLabel k="fix" />
        <strong>
          {studentFix(
            toneAccuracy,
            fluencyScore,
            speechRate,
            focus,
            pauseAnalysis,
          )}
        </strong>
      </div>
      <div className="student-feedback-card next">
        <BiLabel k="next_try" />
        <strong>{studentNextStep(speechRate, focus, pauseAnalysis)}</strong>
      </div>
    </section>
  );
}

function studentStrength(toneAccuracy: number, fluencyScore: number): string {
  if (toneAccuracy >= 68 && fluencyScore >= 65) {
    return "你的聲調和節奏夠清楚，可以試著造更長的句子。 Your tones and rhythm are clear enough to build a longer sentence.";
  }
  if (toneAccuracy >= 60) {
    return "你的聲調形狀可以辨識。 Your tone shape is recognizable.";
  }
  if (fluencyScore >= 62) {
    return "你的說話節奏很穩定。 Your speaking rhythm is steady.";
  }
  return "你完成了一次錄音，現在改進一個小地方。 You completed a recording. Now improve one small part.";
}

function studentFix(
  toneAccuracy: number,
  fluencyScore: number,
  speechRate: number,
  focus?: WordProsody,
  pauseAnalysis?: PauseAnalysis,
): string {
  if (speechRate > 6.5) {
    return "放慢速度 — 每個普通話聲調都需要時間才能完整呈現。 Slow down — each Mandarin tone needs time to complete its shape.";
  }
  if (pauseAnalysis && pauseAnalysis.longest_pause >= 0.8) {
    return `你停頓了 ${pauseAnalysis.longest_pause.toFixed(1)} 秒 — 試著把這些詞連起來不要停。 You paused ${pauseAnalysis.longest_pause.toFixed(1)}s — try linking those words without stopping.`;
  }
  if (toneAccuracy < 50 && focus) {
    return `把「${focus.token}」的聲調變化說得更清楚 — 先誇張一點，再放鬆。 Make the tone movement clearer on "${focus.token}" — exaggerate it first, then smooth it out.`;
  }
  if (fluencyScore < 48) {
    return "把每個字連成一口氣 — 不要在每個詞之間停頓。 Connect the characters into one breath — don't stop between every word.";
  }
  if (focus) {
    return `「${focus.token}」的音高不穩 — 先單獨說兩次，再說完整句子。 "${focus.token}" has uneven pitch — isolate it, say it twice, then say the full sentence.`;
  }
  return "把句子說短一點，並讓每個聲調形狀都清晰分明。 Keep the sentence short and make every tone shape distinct.";
}

function studentNextStep(
  speechRate: number,
  focus?: WordProsody,
  pauseAnalysis?: PauseAnalysis,
): string {
  if (focus) {
    return `練習「${focus.token}」：單獨說 3 次，再放回句子裡。 Drill "${focus.token}": say it alone 3×, then put it back in the sentence.`;
  }
  if (pauseAnalysis && pauseAnalysis.pause_count > 2) {
    return "再錄一次，試著一口氣說完整個句子。 Record again but try to say the whole sentence in one breath.";
  }
  if (speechRate < 2.5) {
    return "再試一次這個句子 — 稍微快一點，並保持聲調清晰。 Try the sentence again — a little faster, keeping the tones clear.";
  }
  return "再錄一次，把聲調形狀做得更誇張一些。 Record again and push the tone shapes a bit further (exaggerate).";
}

// ─── Learning Scaffold ────────────────────────────────────────────────────────

function FeedbackSummary({
  praatMetrics,
  attemptHistory,
  transcription,
}: {
  praatMetrics: PraatMetrics;
  attemptHistory: Array<{ tone: number; fluency: number; attempt: number }>;
  transcription: string;
}) {
  const ai = praatMetrics.ai_feedback;
  const vocabScore = ai?.vocabulary_coverage?.score ?? null;
  const pronScore = averageWordProsodyAccuracy(praatMetrics.word_prosody);
  const toneScore = Math.round(praatMetrics.tone_accuracy);
  const contentAccuracy = ai?.content_accuracy;
  // Only a real score when a vision-capable engine actually judged it —
  // otherwise it's a 0 placeholder (e.g. Groq/local can't see the image)
  // that would misleadingly render as a failing score bar.
  const contentScore = contentAccuracy?.judged ? contentAccuracy.score : null;

  const missingVocab = (ai?.vocabulary_coverage?.missing?.length ?? 0) > 0;
  const vocabListExists = ai?.vocabulary_coverage !== undefined;

  const contentAccepted = isContentAccepted(praatMetrics);
  const weakToneItems = weakToneGuideItems(praatMetrics.word_prosody || []);

  const overallScore =
    vocabScore !== null && pronScore !== null
      ? Math.round((vocabScore + pronScore + toneScore) / 3)
      : toneScore;

  const overallLabel = !contentAccepted
    ? "先確認句子的意思 Check your sentence's meaning first"
    : vocabListExists && missingVocab
      ? "先使用所有詞彙 Use all vocab first"
      : overallScore >= 85
        ? "太棒了！ Excellent!"
        : overallScore >= 70
          ? "進步良好 Good progress"
          : "繼續加油 Keep going";

  const prev =
    attemptHistory.length > 1
      ? attemptHistory[attemptHistory.length - 2]
      : null;
  const curr =
    attemptHistory.length > 0
      ? attemptHistory[attemptHistory.length - 1]
      : null;
  const trendDiff = prev && curr ? curr.tone - prev.tone : null;

  return (
    <div className="feedback-summary">
      <div className="feedback-summary-top">
        <div className="feedback-summary-meta">
          <p className="feedback-summary-label">{overallLabel}</p>
          <p className="feedback-summary-attempt">
            <BiLabel zh={`第 ${attemptHistory.length || 1} 次嘗試`} en={`Attempt ${attemptHistory.length || 1}`} />
          </p>
          {trendDiff !== null && (
            <p
              className={`feedback-summary-trend ${trendDiff > 0 ? "up" : trendDiff < 0 ? "down" : ""}`}
            >
              {trendDiff > 0 ? (
                <BiLabel zh={`↑ 比上次 +${trendDiff}%`} en={`↑ +${trendDiff}% from last try`} />
              ) : trendDiff < 0 ? (
                <BiLabel zh={`↓ ${trendDiff}% — 繼續加油`} en={`↓ ${trendDiff}% — keep going`} />
              ) : (
                <BiLabel k="same_as_last_try" />
              )}
            </p>
          )}
        </div>
      </div>

      {transcription && (
        <p className="feedback-summary-transcript">
          <BiLabel k="you_said" /> <em lang="zh-TW">"{transcription}"</em>
        </p>
      )}

      {/* ── Meaning check comes first: does the sentence actually fit the picture? ── */}
      {/* judged:true means a vision model actually evaluated it; false = placeholder */}
      {contentAccuracy?.judged && contentAccuracy.feedback && (
        <div className={`content-accuracy-panel ${contentAccepted ? "is-accepted" : "is-rejected"}`}>
          <p className="score-guide-heading">
            <BiLabel k="does_it_match_the_image" />
          </p>
          <p className="content-accuracy-feedback">{contentAccuracy.feedback}</p>
          {contentAccuracy.matched_details.length > 0 && (
            <p className="content-accuracy-matched">
              ✓ {contentAccuracy.matched_details.join(", ")}
            </p>
          )}
          {contentAccuracy.missed_details.length > 0 && (
            <p className="content-accuracy-missed">
              ✗ {contentAccuracy.missed_details.join(", ")}
            </p>
          )}
          {!contentAccepted && (
            <p className="content-accuracy-gate-hint">
              <BiLabel
                zh="先修正句子的意思，再看發音回饋。"
                en="Fix what your sentence means first — pronunciation feedback comes after that."
              />
            </p>
          )}
        </div>
      )}

      {/* ── Pronunciation feedback only once the meaning is accepted ── */}
      {contentAccepted && (
        <>
          {(() => {
            const bars = [
              ...(vocabScore !== null
                ? [{ label: "詞彙 Vocabulary", score: vocabScore, color: "var(--seal)" }]
                : []),
              { label: "聲調 Tone accuracy", score: toneScore, color: "var(--gold)" },
              ...(contentScore !== null
                ? [{ label: "內容準確度 Content accuracy", score: contentScore, color: "var(--jade)" }]
                : []),
            ];
            return bars.length > 0 ? (
              <div className="feedback-summary-bars">
                {bars.map(({ label, score, color }) => (
                  <div key={label} className="feedback-summary-bar-card">
                    <span className="feedback-summary-bar-label">{label}</span>
                    <span className="feedback-summary-bar-pct" style={{ color }}>{score}%</span>
                    <div className="feedback-summary-bar-track">
                      <div
                        className="feedback-summary-bar-fill"
                        style={{ width: `${score}%`, background: color }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : null;
          })()}

          {toneScore > 0 && (
            <div className="score-guide">
              <p className="score-guide-heading"><BiLabel k="how_to_reach_100" /></p>
              <div className="score-guide-rows">
                {toneScore < 100 && (
                  <div className="score-guide-row">
                    <span className="score-guide-label"><BiLabel k="tone_accuracy" /></span>
                    <ul className="score-guide-tips">
                      {weakToneItems.length > 0 ? (
                        <>
                          {weakToneItems.map((item) => {
                            const tone = item.expected_tones![0];
                            const shapeKey = TONE_NUMBER_TO_SHAPE[tone] ?? "variable";
                            return (
                              <li key={`${item.token}-${item.index}`}>
                                <strong>
                                  「{item.token}」 {TONE_NUMBER_ARROW_LABEL[tone] ?? ""}
                                </strong>{" "}
                                {TONE_SHAPES[shapeKey].tip} ({Math.round(item.tone_accuracy ?? 0)}%)
                              </li>
                            );
                          })}
                          <li>
                            <BiText k="isolate_problem_characters_from_the_tone" />
                          </li>
                        </>
                      ) : (
                        <>
                          <li>
                            <strong>一聲 Tone 1 (ā) →</strong> <BiText k="keep_pitch_high_and_completely_flat_thro" />
                          </li>
                          <li>
                            <strong>二聲 Tone 2 (á) ↗</strong> <BiText k="start_mid_push_pitch_up_to_the_top_like_" />
                          </li>
                          <li>
                            <strong>三聲 Tone 3 (ǎ) ↘↗</strong> <BiText k="dip_down_first_then_rise_back_the_lowest" />
                          </li>
                          <li>
                            <strong>四聲 Tone 4 (à) ↘</strong> <BiText k="start_as_high_as_you_can_and_drop_sharpl" />
                          </li>
                          <li>
                            <BiText k="isolate_problem_characters_from_the_tone" />
                          </li>
                        </>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const TONE_SHAPES: Record<
  string,
  { label: string; arrow: string; tip: string; drill: string }
> = {
  level: {
    label: "平直 Level →",
    arrow: "→",
    tip: "全程保持平直。 Stays flat throughout.",
    drill: "再說一次，試著加入更多變化 — 上升或下降。 Say it again and try to add more movement — either rise or fall.",
  },
  rising: {
    label: "上升 Rising ↗",
    arrow: "↗",
    tip: "音高從頭到尾上升。 Pitch rises start to end.",
    drill: "上升形狀不錯。把開頭降低一點，結尾再推高一點。 Good upward shape. Make the start lower and push the end higher.",
  },
  falling: {
    label: "下降 Falling ↘",
    arrow: "↘",
    tip: "音高從頭到尾下降。 Pitch falls start to end.",
    drill: "下降形狀不錯。開頭要高，然後急速下降。 Good downward shape. Start high and let it drop sharply.",
  },
  dip: {
    label: "低降 Dip ↘↗",
    arrow: "↘↗",
    tip: "先下降再上升。 Dips down, then rises.",
    drill: "低降形狀不錯。最低點要更深一點再回升。 Good dip shape. Make the lowest point deeper before rising back.",
  },
  variable: {
    label: "不清楚 Unclear ??",
    arrow: "??",
    tip: "未偵測到清楚的形狀。 No clear shape was detected.",
    drill: "把這個字單獨拿出來，慢慢說 3 次，再放回句子。 Isolate this character, say it 3 times slowly, then put it back.",
  },
};

function RecordingPlayback({ blob }: { blob: Blob }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  if (!url) return null;

  return (
    <div className="recording-playback">
      <p className="recording-playback-label"><BiLabel k="your_recording" /></p>
      <audio controls src={url} className="recording-playback-audio" />
    </div>
  );
}

const TONE_NUMBER_ARROW_LABEL: Record<number, string> = {
  1: "一聲 Tone 1 (ā) →",
  2: "二聲 Tone 2 (á) ↗",
  3: "三聲 Tone 3 (ǎ) ↘↗",
  4: "四聲 Tone 4 (à) ↘",
};

/** The characters actually dragging this attempt's tone score down — used to
 * personalize the "how to reach 100%" guide with the specific tone(s) this
 * student got wrong, instead of a generic list of all four tones every time.
 * Threshold and neutral-tone exclusion match prosodyImprovementTip's own
 * "Good match" cutoff so the two never disagree about what needs work. */
function weakToneGuideItems(wordProsody: WordProsody[], limit = 3): WordProsody[] {
  return wordProsody
    .filter(
      (item) =>
        (item.expected_tones?.length ?? 0) > 0 &&
        item.expected_tones![0] !== 5 &&
        (item.tone_accuracy ?? 100) < 68,
    )
    .sort((a, b) => (a.tone_accuracy ?? 0) - (b.tone_accuracy ?? 0))
    .slice(0, limit);
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

async function readErrorResponse(
  response: Response,
): Promise<{ detail?: string }> {
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
    return `無法連線到語音分析後端 ${backendUrl}。請先啟動 FastAPI 後端（連接埠 8000），再重新錄音。 Cannot reach the speech analysis backend at ${backendUrl}. Start the FastAPI backend on port 8000, then record again.`;
  }

  return message || "語音分析發生錯誤 Speech analysis error occurred";
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

function VocabCategorizer({
  words,
  groups,
}: {
  words: string[];
  groups: VocabGroup[];
}) {
  const [placement, setPlacement] = useState<Record<string, number | null>>(
    () => Object.fromEntries(words.map((w) => [w, null])),
  );
  const [checked, setChecked] = useState(false);
  const [dragWord, setDragWord] = useState<string | null>(null);

  const unplaced = words.filter((w) => placement[w] === null);
  const allPlaced = unplaced.length === 0;

  const correctGroupIndex = (word: string): number =>
    groups.findIndex((g) => g.words.includes(word));

  const isCorrect = (word: string, groupIndex: number): boolean =>
    correctGroupIndex(word) === groupIndex;

  const placeWord = (word: string, groupIndex: number) => {
    setPlacement((p) => ({ ...p, [word]: groupIndex }));
    setChecked(false);
  };

  const unplaceWord = (word: string) => {
    setPlacement((p) => ({ ...p, [word]: null }));
    setChecked(false);
  };

  const handleCheck = () => setChecked(true);
  const handleReset = () => {
    setPlacement(Object.fromEntries(words.map((w) => [w, null])));
    setChecked(false);
  };

  const correctCount = checked
    ? words.filter((w) => {
        const gi = placement[w];
        return gi !== null && isCorrect(w, gi);
      }).length
    : 0;

  return (
    <div className="vocab-categorizer">
      <div className="vocab-categorizer-header">
        <span className="vocab-categorizer-title">
          <BiLabel zh="把詞彙分類" en="Sort words into groups" />
        </span>
        {checked && (
          <span
            className={`vocab-categorizer-score ${correctCount === words.length ? "vc-score-perfect" : ""}`}
          >
            <BiLabel zh={`${correctCount}/${words.length} 正確`} en={`${correctCount}/${words.length} correct`} />
          </span>
        )}
      </div>

      {unplaced.length > 0 && (
        <div className="vocab-categorizer-bank">
          <span className="vc-bank-label">
            <BiLabel zh="拖曳或點擊一個詞，再放到下方的分類中" en="Drag or click a word, then drop it into a group below" />
          </span>
          <div className="vc-bank-chips">
            {unplaced.map((word) => (
              <span
                key={word}
                className="vc-chip vc-chip-bank"
                draggable
                onDragStart={() => setDragWord(word)}
                onDragEnd={() => setDragWord(null)}
              >
                {word}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="vocab-categorizer-groups">
        {groups.map((group, gi) => {
          const wordsHere = words.filter((w) => placement[w] === gi);
          const isDragTarget = dragWord !== null;
          return (
            <div
              key={gi}
              className={`vc-group ${isDragTarget ? "vc-group-droppable" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragWord) {
                  placeWord(dragWord, gi);
                  setDragWord(null);
                }
              }}
            >
              <div className="vc-group-name">{group.name}</div>
              <div className="vc-group-words">
                {wordsHere.map((word) => {
                  const correct = isCorrect(word, gi);
                  const status = checked
                    ? correct
                      ? "correct"
                      : "wrong"
                    : "placed";
                  const hintGroup =
                    !correct && checked
                      ? groups[correctGroupIndex(word)]?.name
                      : null;
                  return (
                    <span key={word} className="vc-word-wrap">
                      <span
                        className={`vc-chip vc-chip-${status}`}
                        onClick={() => !checked && unplaceWord(word)}
                        title={!checked ? "點擊移回 Click to move back" : undefined}
                      >
                        {word}
                        {checked && correct && (
                          <span className="vc-icon">✓</span>
                        )}
                        {checked && !correct && (
                          <span className="vc-icon">✗</span>
                        )}
                      </span>
                      {hintGroup && (
                        <span className="vc-hint">→ {hintGroup}</span>
                      )}
                    </span>
                  );
                })}
                {wordsHere.length === 0 && (
                  <span className="vc-group-empty">
                    <BiLabel zh="放在這裡" en="Drop here" />
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="vocab-categorizer-actions">
        {!checked ? (
          <button
            type="button"
            className="vc-btn-check"
            disabled={!allPlaced}
            onClick={handleCheck}
          >
            {allPlaced ? (
              <BiLabel zh="檢查答案" en="Check answers" />
            ) : (
              <BiLabel
                zh={`還有 ${unplaced.length} 個詞待放置`}
                en={`${unplaced.length} word${unplaced.length > 1 ? "s" : ""} left to place`}
              />
            )}
          </button>
        ) : (
          <div className="vc-result-row">
            {correctCount === words.length ? (
              <span className="vc-all-correct">
                <BiLabel
                  zh="全部正確！現在用這些詞錄製你的句子吧。"
                  en="All correct! Now record your sentence using these words."
                />
              </span>
            ) : (
              <>
                <span className="vc-wrong-hint">
                  <BiLabel
                    zh="標示 ✗ 的詞會顯示正確分類 — 修正後再試一次。"
                    en="Words marked ✗ show the correct group — fix them and try again."
                  />
                </span>
                <button
                  type="button"
                  className="vc-btn-retry"
                  onClick={handleReset}
                >
                  <BiLabel zh="再試一次" en="Try again" />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
