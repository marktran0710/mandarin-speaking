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
} from "../database";
import PitchChart from "../PitchChart";
import PraatTimeline from "./PraatTimeline";
import StoryConceptMap from "./StoryConceptMap";
import { toPinyin } from "../utils/pinyin";
import "./StoryRecorder.css";
import { BiLabel, BiText } from "./BiLabel";
import "./BiLabel.css";

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
  mean_pitch: number;
  pitch_range: number;
  start_pitch: number;
  end_pitch: number;
  contour_shape: string;
  feedback: string;
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
  const [transcriptions, setTranscriptions] = useState<TranscriptionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<SpeechModel>("webspeech");
  const [aiProvider, setAiProvider] = useState<string>("");
  const [aiProviders, setAiProviders] = useState<AiProviderOption[]>([]);
  const [silenceDuration, setSilenceDuration] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [praatMetrics, setPraatMetrics] = useState<PraatMetrics | null>(null);
  const [analysisAudioBlob, setAnalysisAudioBlob] = useState<Blob | null>(null);
  const [attemptHistory, setAttemptHistory] = useState<
    Array<{ tone: number; fluency: number; attempt: number }>
  >([]);
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
        setAiProvider((prev) => prev || data.default || "");
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
        "Please place all pictures into the scenes before checking!",
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
        "Spot on! Excellent job. You have arranged the scenes in the correct order!",
      );
    } else {
      setSortingFeedback(
        "Some pictures are not in the correct sequence. Check the red highlighted scenes and try again!",
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
        throw new Error(errorData.detail || "Transcription failed");
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
      if (aiProvider) {
        formData.append("ai_provider", aiProvider);
      }

      const response = await fetch(`${backendUrl}/api/analyze`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
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
        pronScore: metrics.ai_feedback?.pronunciation_note?.score ?? 0,
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
  // Model sentence: teacher's scene prompt is the canonical reference.
  // Student's own transcript is NOT used here — students should imitate the
  // scene prompt, not hear their own words played back as a "perfect example".
  const scenePromptText = topic.prompts?.[selectedImageIndex] || "";
  const modelExampleText =
    scenePromptText ||
    buildPracticeAnalysisText(selectedVocabulary) ||
    "今天下雨，所以我帶傘。";
  const storyConnectors = ["一開始", "然後", "因為", "所以", "突然", "最後"];
  const sentenceStarters = ["一開始，", "他們在", "然後，", "突然，", "最後，"];
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
        await createStorySubmission(submission);
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
    { key: "overview", label: <BiLabel zh="總覽" en="Overview" />, icon: "📖" },
    { key: "sorting", label: <BiLabel zh="排列場景" en="Arrange Scenes" />, icon: "🧩" },
    { key: "conceptmap", label: <BiLabel zh="詞彙地圖" en="Vocabulary Map" />, icon: "🗺️" },
    { key: "practice", label: <BiLabel zh="口說練習" en="Speaking" />, icon: "🎙️" },
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
            <p className="eyebrow"><BiLabel zh="故事挑戰" en="Story Challenge" /></p>
            <h1 className="overview-title">{topic.name}</h1>
            {topic.description && (
              <p className="overview-desc">{topic.description}</p>
            )}
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
              {topic.images.map((_, si) => {
                const sceneWords = topic.vocabulary[si] || [];
                if (sceneWords.length === 0) return null;
                return (
                  <div key={si} className="overview-vocab-scene">
                    <span className="overview-vocab-scene-label">
                      Scene {si + 1}
                    </span>
                    <div className="overview-vocab-chips">
                      {sceneWords.map((word, i) => (
                        <span
                          key={`${word}-${i}`}
                          className="overview-vocab-chip"
                        >
                          <span className="vocab-chip-hanzi">{word}</span>
                          {toPinyin(word) && (
                            <span className="vocab-chip-pinyin">
                              {toPinyin(word)}
                            </span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="overview-steps-block">
            <h2><BiLabel zh="你的挑戰" en="Your Challenge" /></h2>
            <div className="overview-steps">
              <div className="overview-step">
                <span className="overview-step-num">1</span>
                <div>
                  <strong><BiLabel zh="排列場景" en="Arrange Scenes" /></strong>
                  <p><BiText zh="把故事圖片排成正確順序" en="Put the story pictures in the right order" /></p>
                </div>
              </div>
              <div className="overview-step">
                <span className="overview-step-num">2</span>
                <div>
                  <strong><BiLabel zh="詞彙地圖" en="Vocabulary Map" /></strong>
                  <p><BiText zh="把關鍵詞彙配對到每個故事場景" en="Match key words to each story scene" /></p>
                </div>
              </div>
              <div className="overview-step">
                <span className="overview-step-num">3</span>
                <div>
                  <strong><BiLabel zh="口說練習" en="Speaking Practice" /></strong>
                  <p><BiText zh="把你的普通話故事大聲說出來並錄音" en="Record your Mandarin story out loud" /></p>
                </div>
              </div>
            </div>
          </div>

          <div className="overview-cta">
            <button
              className="btn-start-challenge"
              onClick={() => setPhase("sorting")}
            >
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
              <p className="eyebrow"><BiLabel zh="步驟 1 · 排列場景" en="Step 1 · Arrange Scenes" /></p>
              <h1><BiLabel zh="把故事排好順序" en="Put the Story in Order" /></h1>
              <p className="subtitle">
                <BiText zh="把每張圖片拖到正確的場景位置，然後驗證順序以解鎖口說練習。" en="Drag each picture into the correct scene slot, then verify the sequence to unlock speaking practice." />
              </p>
            </div>
            <div className="sorting-progress">
              <div className="sorting-progress-label">
                {placedImages.filter(Boolean).length} / {placedImages.length}{" "}
                placed
              </div>
              <div className="sorting-progress-bar">
                <div
                  className="sorting-progress-fill"
                  style={{
                    width: `${(placedImages.filter(Boolean).length / placedImages.length) * 100}%`,
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
                      Scene {index + 1}
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
                          {selectedPoolImage ? "Click to place" : "Drag here"}
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
              <h2>📷 Picture Bank</h2>
              <p className="pool-helper-text">
                {selectedPoolImage
                  ? "Click a scene slot above to place this picture."
                  : shuffledPool.length === 0
                    ? "All pictures placed — verify below!"
                    : "Drag a picture to a slot, or click to select then click a slot."}
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
                  <p>All pictures placed!</p>
                </div>
              ) : (
                shuffledPool.map((image) => (
                  <div
                    key={image}
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
                      {selectedPoolImage === image
                        ? "✓ Selected"
                        : "Drag · Click"}
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
              ↺ Reset
            </button>

            {validationStates.some((s) => s === "correct") &&
            !validationStates.includes("incorrect") &&
            placedImages.every(Boolean) ? (
              <button
                type="button"
                className="btn-start-speaking"
                onClick={() => setPhase("conceptmap")}
              >
                <BiLabel zh="繼續到詞彙地圖 →" en="Continue to Vocabulary Map" />
              </button>
            ) : (
              <button
                type="button"
                className="btn-verify-sorting"
                onClick={checkSequence}
                disabled={placedImages.some((img) => img === null)}
              >
                <BiLabel zh="驗證順序" en="Verify Sequence" />
              </button>
            )}

            <button
              type="button"
              className="btn-skip-sorting"
              onClick={() => setPhase("conceptmap")}
            >
              <BiLabel zh="跳過" en="Skip" />
            </button>
          </div>
        </section>
      )}

      {phase === "conceptmap" && (
        <section className="conceptmap-phase">
          <div className="conceptmap-phase-header">
            <p className="eyebrow"><BiLabel zh="步驟 2 · 詞彙地圖" en="Step 2 · Vocabulary Map" /></p>
            <h1><BiLabel zh="台灣社區故事畫布" en="Taiwan Community Story Canvas" /></h1>
            <p className="conceptmap-phase-sub">
              <BiText zh="把每個詞彙拖到對應的故事角色 — 人物、動作、場景、物品與工具、文法連接詞，或結果" en="Drag each word into its story role — Characters, Actions, Settings, Objects & Tools, Grammar Glue, or Outcomes" />
            </p>
          </div>
          <StoryConceptMap topic={topic} defaultOpen />
          <div className="conceptmap-phase-actions">
            <button
              className="btn-back-phase"
              onClick={() => setPhase("sorting")}
            >
              <BiLabel zh="← 返回場景" en="Back to Scenes" />
            </button>
            <button
              className="btn-next-phase"
              onClick={() => setPhase("practice")}
            >
              <BiLabel zh="繼續到口說練習 →" en="Continue to Speaking" />
            </button>
          </div>
        </section>
      )}

      {phase === "practice" && (
        <>
          {/* ── Scene selector strip ── */}
          <div className="practice-scene-strip">
            {topic.images.map((img, idx) => {
              const prog = sceneProgress[idx];
              const ready = prog ? sceneReady(prog) : false;
              const started = prog && prog.attempts > 0;
              return (
                <button
                  type="button"
                  key={img}
                  className={`practice-scene-thumb${idx === selectedImageIndex ? " active" : ""}${ready ? " scene-ready" : ""}`}
                  onClick={() => {
                    onImageChange(img);
                    onImageSelect(idx);
                    setPraatMetrics(null);
                    setAnalysisAudioBlob(null);
                    setAttemptHistory([]);
                    currentTranscriptRef.current = "";
                  }}
                  disabled={isBusy}
                >
                  <img src={img} alt={`Scene ${idx + 1}`} />
                  <span>Scene {idx + 1}</span>
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
                      setPraatMetrics(null);
                      setAnalysisAudioBlob(null);
                      setAttemptHistory([]);
                      currentTranscriptRef.current = "";
                    }}
                  >
                    <BiLabel zh="下一個場景 →" en="Next scene" />
                  </button>
                </div>
              );
            }
            if (ready && !hasNext) {
              return (
                <div className="scene-ready-banner scene-story-done">
                  <strong><BiLabel zh="所有場景都已練習完成！" en="All scenes practiced!" /></strong>
                  <p>
                    <BiText zh="你已完成整個故事。可以檢視你的錄音，或重新錄製任何場景。" en="You've completed the full story. Review your recordings or record any scene again." />
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
                  {gap > 0
                    ? `${gap} more points needed to unlock the next scene — keep going.`
                    : "Keep practicing — try to make the tone shapes clearer."}
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
                <div className="practice-scene-badge">
                  Scene {selectedImageIndex + 1} / {topic.images.length}
                  {topic.prompts?.[selectedImageIndex] && (
                    <span> · {topic.prompts[selectedImageIndex]}</span>
                  )}
                </div>
              </div>

              {(() => {
                const groups = topic.vocabularyGroups?.[selectedImageIndex];
                if (
                  groups &&
                  groups.length > 0 &&
                  selectedVocabulary.length > 0
                ) {
                  return (
                    <VocabCategorizer
                      key={selectedImageIndex}
                      words={selectedVocabulary}
                      groups={groups}
                    />
                  );
                }
                return null;
              })()}

              {selectedVocabulary.length > 0 && (
                <div className="practice-vocab-ref">
                  <p className="practice-vocab-heading">
                    Scene vocabulary
                    {praatMetrics && (
                      <span className="vocab-check-hint">
                        {" "}
                        — check which words you used
                      </span>
                    )}
                  </p>
                  <div className="practice-vocab-chips">
                    {selectedVocabulary.map((w) => {
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
                              ? "You used this word ✓"
                              : used === false
                                ? "Try to include this word"
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
                          {toPinyin(w) && (
                            <span className="vocab-chip-pinyin">
                              {toPinyin(w)}
                            </span>
                          )}
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
                          return "All vocabulary words used — excellent!";
                        if (usedList.length === 0)
                          return `Try to include: ${missedList.slice(0, 3).join("、")}`;
                        return `Used ${usedList.length}/${selectedVocabulary.length}. Try adding: ${missedList.slice(0, 2).join("、")}`;
                      })()}
                    </p>
                  )}
                </div>
              )}

              <div className="practice-record-area">
                {aiProviders.length > 0 && (
                  <div
                    className="record-engine-switch"
                    role="group"
                    aria-label="AI feedback engine"
                  >
                    <span className="record-engine-switch-label">
                      AI engine
                    </span>
                    <div className="record-engine-switch-options">
                      {aiProviders.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          className={`record-engine-chip${aiProvider === p.id ? " is-active" : ""}`}
                          onClick={() => setAiProvider(p.id)}
                          disabled={isBusy || !p.available || p.id === "local"}
                          title={
                            p.id === "local"
                              ? "Local engine disabled"
                              : p.available
                                ? `Use ${p.label} for feedback`
                                : `${p.label} needs an API key`
                          }
                        >
                          {p.label}
                          {p.available && p.id !== "local" ? "" : " 🔒"}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <button
                  type="button"
                  onClick={handlePrimaryRecordingAction}
                  disabled={recordingButtonDisabled}
                  className={`btn-practice-record${isRecording ? " is-recording" : ""}`}
                >
                  {isRecording ? <BiLabel zh="⏹ 停止錄音" en="Stop Recording" /> : <BiLabel zh="🎙 錄音" en="Record" />}
                </button>
                {isRecording && (
                  <div className="practice-timer">
                    <span>{recordingDuration}s</span>
                    {selectedModel === "webspeech" && (
                      <span className="practice-silence">
                        silence {silenceDuration}s / 7s
                      </span>
                    )}
                  </div>
                )}
                <label
                  className={`btn-practice-upload${isBusy ? " disabled" : ""}`}
                  role="button"
                  tabIndex={isBusy ? -1 : 0}
                >
                  Upload audio
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
            </div>

            {/* Right: story guide */}
            <div className="practice-guide-panel">
              <div className="practice-guide-header">
                <span>🗺️</span>
                <div>
                  <h3>Story Guide</h3>
                  <p>
                    Use your vocabulary map to build one or two sentences, then
                    record.
                  </p>
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
                  {sentenceStarters.map((s) => (
                    <span key={s} className="practice-chip">
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              <div className="practice-chips-group">
                <p>Connectors</p>
                <div>
                  {storyConnectors.map((c) => (
                    <span key={c} className="practice-chip">
                      {c}
                    </span>
                  ))}
                </div>
              </div>

              <details className="practice-model-picker">
                <summary>Recording options</summary>
                <label className="practice-model-label" htmlFor="speech-source">
                  Speech source
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
                    Browser (Traditional Chinese)
                  </option>
                  <option value="groq">Groq Whisper (free, cloud)</option>
                  <option value="ctwhisper">
                    Whisper (Chinese / Taiwanese, local)
                  </option>
                  <option value="vibevoice">VibeVoice-ASR (local file)</option>
                </select>
              </details>
            </div>
          </div>

          {(isTranscribing || isAnalyzing) && (
            <div className="analysis-loading-card">
              <div className="analysis-loading-spinner" />
              <div className="analysis-loading-text">
                <p className="analysis-loading-title">
                  {isTranscribing
                    ? "Listening to your voice…"
                    : "Analyzing pronunciation…"}
                </p>
                <p className="analysis-loading-sub">
                  {isTranscribing
                    ? "Converting speech to text"
                    : "Checking tones, rhythm, and vocabulary"}
                </p>
              </div>
              <div className="analysis-loading-steps">
                <span
                  className={`loading-step ${isTranscribing ? "active" : "done"}`}
                >
                  Transcribe
                </span>
                <span className="loading-step-arrow">→</span>
                <span
                  className={`loading-step ${isAnalyzing && !isTranscribing ? "active" : ""}`}
                >
                  Praat
                </span>
                <span className="loading-step-arrow">→</span>
                <span className="loading-step">Feedback</span>
              </div>
            </div>
          )}
          {error && <p className="error">{error}</p>}

          {praatMetrics && (
            <section className="analysis-panel">
              {/* ── Zone 1: Summary ─────────────────────────────────────── */}
              <FeedbackSummary
                praatMetrics={praatMetrics}
                attemptHistory={attemptHistory}
                transcription={praatMetrics.transcription || ""}
              />

              {(() => {
                const missing =
                  praatMetrics.ai_feedback?.vocabulary_coverage?.missing ?? [];
                if (missing.length > 0) {
                  return (
                    <div className="try-again-vocab-gate">
                      <p className="try-again-gate-title">
                        <BiText zh="再練習一次 — 你還沒使用所有場景詞彙" en="Practice again — you haven't used all the scene words yet" />
                      </p>
                      <div className="try-again-missing-chips">
                        {missing.map((w) => (
                          <span key={w} className="try-again-missing-chip">
                            {w}
                          </span>
                        ))}
                      </div>
                      <p className="try-again-gate-hint">
                        <BiText zh="試著在下一次錄音中使用上方每個詞彙。↑ 再錄一次" en="Try to use every word above in your next recording. ↑ Record again" />
                      </p>
                    </div>
                  );
                }
                return (
                  <div className="try-again-complete">
                    <span className="try-again-complete-icon">✓</span>
                    <div>
                      <p className="try-again-complete-title">
                        <BiLabel zh="所有詞彙都使用了！" en="All vocabulary words used!" />
                      </p>
                      <p className="try-again-complete-hint">
                        <BiText zh="現在練習發音 — 再錄一次，專注在聲調上。↑" en="Now work on pronunciation — record again and focus on the tones. ↑" />
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* ── Zone 3: Listen back ──────────────────────────────────── */}
              {/* Tone drill — only shown once student is using scene vocabulary */}
              {(praatMetrics.word_prosody?.length ?? 0) > 0 &&
                (praatMetrics.ai_feedback?.vocabulary_coverage?.used?.length ??
                  0) > 0 && (
                  <ToneDrillPanel
                    wordProsody={praatMetrics.word_prosody || []}
                  />
                )}

              <div className="listen-try-zone">
                {analysisAudioBlob && (
                  <RecordingPlayback blob={analysisAudioBlob} />
                )}
              </div>

              {/* ── Zone 4: Advanced details (collapsed) ────────────────── */}
              <details className="advanced-praat-details">
                <summary>Advanced analysis details</summary>

                <div className="pitch-overview">
                  <p className="pitch-overview-label">
                    Your pitch contour vs. target tone shape
                  </p>
                  <PitchChart
                    pitchContour={praatMetrics.pitch_contour}
                    detectedTone={praatMetrics.detected_tone}
                  />
                </div>

                <div className="metrics-section">
                  <div className="metric-card tone-card">
                    <div className="metric-label">Dominant pitch shape</div>
                    <div className="metric-value compact">
                      {getToneName(praatMetrics.detected_tone)}
                    </div>
                    <div className="metric-subtext">
                      Tone accuracy score shown in the summary above
                    </div>
                  </div>
                  <div className="metric-card rate-card">
                    <div className="metric-label">Speech rate</div>
                    <div className="metric-value">
                      {praatMetrics.speech_rate.toFixed(1)}
                    </div>
                    <div className="metric-subtext">
                      {praatMetrics.speech_rate < 2.5
                        ? "Too slow — add more flow"
                        : praatMetrics.speech_rate > 6.5
                          ? "Too fast — slow each tone"
                          : "syllables/sec — good pace"}
                    </div>
                  </div>
                  {praatMetrics.pause_analysis &&
                  praatMetrics.pause_analysis.duration > 0 ? (
                    <div className="metric-card pause-card">
                      <div className="metric-label">Pauses</div>
                      <div className="metric-value">
                        {praatMetrics.pause_analysis.pause_count}
                      </div>
                      <div className="metric-subtext">
                        {praatMetrics.pause_analysis.pause_count === 0
                          ? "No long pauses — smooth delivery"
                          : praatMetrics.pause_analysis.longest_pause >= 0.8
                            ? `Longest gap: ${praatMetrics.pause_analysis.longest_pause.toFixed(1)}s`
                            : `${praatMetrics.pause_analysis.pause_count} short pause${praatMetrics.pause_analysis.pause_count > 1 ? "s" : ""} — nearly fluent`}
                      </div>
                    </div>
                  ) : (
                    <div className="metric-card fluency-card">
                      <div className="metric-label">Fluency</div>
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
                      <div className="metric-label">Vowel quality</div>
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

                <div className="word-prosody-section">
                  <div className="word-prosody-header">
                    <h3>Character-by-character prosody</h3>
                    <p>Pitch movement estimated for each Mandarin character.</p>
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
                      <strong>No character feedback yet</strong>
                      <p>
                        Needs a clear pitch contour and transcript. Try one
                        complete sentence, or use Chinese/Taiwanese Whisper.
                      </p>
                    </div>
                  )}
                </div>

                <div className="formants-detail">
                  <h3>Formant measurements</h3>
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

          <div className="transcriptions">
            <h2>Speech transcript</h2>
            {praatMetrics?.transcription && (
              <div className="transcription-item transcription-asr-primary">
                <div className="item-header">
                  <span className="time">ASR result</span>
                  <span className="model-badge">
                    {(praatMetrics.transcription_model || "ASR").toUpperCase()}
                  </span>
                </div>
                <p lang="zh-TW">{praatMetrics.transcription}</p>
              </div>
            )}
            {transcriptions.length === 0 && !praatMetrics?.transcription ? (
              <p className="empty">
                Your transcript will appear after recording.
              </p>
            ) : (
              transcriptions.map((item) => (
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
              ))
            )}
          </div>

          {/* ── Submit Story ────────────────────────────────────────── */}
          {storySubmitted ? (
            <div className="story-submit-panel story-submit-success">
              <span className="story-submit-icon">✓</span>
              <div>
                <p className="story-submit-title">Story submitted!</p>
                <p className="story-submit-hint">
                  Your teacher can now review all {totalScenes} scenes.
                </p>
              </div>
            </div>
          ) : (
            <div className="story-submit-panel">
              <div className="story-submit-progress">
                {topic.images.map((_, si) => (
                  <div
                    key={si}
                    className={`story-submit-dot ${sceneRecordings[si] ? "done" : "pending"}`}
                    title={`Scene ${si + 1}${sceneRecordings[si] ? " ✓" : " — not yet recorded"}`}
                  />
                ))}
              </div>
              <p className="story-submit-label">
                {allScenesRecorded
                  ? "All scenes recorded — ready to submit"
                  : `${completedSceneCount} of ${totalScenes} scenes recorded`}
              </p>
              {submitError && (
                <p className="story-submit-error">{submitError}</p>
              )}
              <button
                className="btn-submit-story"
                disabled={!allScenesRecorded}
                onClick={handleSubmitStory}
              >
                <BiLabel zh="提交故事給老師" en="Submit Story to Teacher" />
              </button>
            </div>
          )}
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
        <span>Good</span>
        <strong>{studentStrength(toneAccuracy, fluencyScore)}</strong>
      </div>
      <div className="student-feedback-card fix">
        <span>Fix</span>
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
        <span>Next try</span>
        <strong>{studentNextStep(speechRate, focus, pauseAnalysis)}</strong>
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
  pauseAnalysis?: PauseAnalysis,
): string {
  if (speechRate > 6.5) {
    return "Slow down — each Mandarin tone needs time to complete its shape.";
  }
  if (pauseAnalysis && pauseAnalysis.longest_pause >= 0.8) {
    return `You paused ${pauseAnalysis.longest_pause.toFixed(1)}s — try linking those words without stopping.`;
  }
  if (toneAccuracy < 65 && focus) {
    return `Make the tone movement clearer on "${focus.token}" — exaggerate it first, then smooth it out.`;
  }
  if (fluencyScore < 60) {
    return "Connect the characters into one breath — don't stop between every word.";
  }
  if (focus) {
    return `"${focus.token}" has uneven pitch — isolate it, say it twice, then say the full sentence.`;
  }
  return "Keep the sentence short and make every tone shape distinct.";
}

function studentNextStep(
  speechRate: number,
  focus?: WordProsody,
  pauseAnalysis?: PauseAnalysis,
): string {
  if (focus) {
    return `Drill "${focus.token}": say it alone 3×, then put it back in the sentence.`;
  }
  if (pauseAnalysis && pauseAnalysis.pause_count > 2) {
    return "Record again but try to say the whole sentence in one breath.";
  }
  if (speechRate < 2.5) {
    return "Try the sentence again — a little faster, keeping the tones clear.";
  }
  return "Record again and push the tone shapes a bit further (exaggerate).";
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
  const pronScore = ai?.pronunciation_note?.score ?? null;
  const toneScore = Math.round(praatMetrics.tone_accuracy);

  const missingVocab = (ai?.vocabulary_coverage?.missing?.length ?? 0) > 0;
  const vocabListExists = ai?.vocabulary_coverage !== undefined;

  const overallScore =
    vocabScore !== null && pronScore !== null
      ? Math.round((vocabScore + pronScore + toneScore) / 3)
      : toneScore;

  const overallLabel =
    vocabListExists && missingVocab
      ? "Use all vocab first"
      : overallScore >= 85
        ? "Excellent!"
        : overallScore >= 70
          ? "Good progress"
          : "Keep going";

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
            Attempt {attemptHistory.length || 1}
          </p>
          {trendDiff !== null && (
            <p
              className={`feedback-summary-trend ${trendDiff > 0 ? "up" : trendDiff < 0 ? "down" : ""}`}
            >
              {trendDiff > 0
                ? `↑ +${trendDiff}% from last try`
                : trendDiff < 0
                  ? `↓ ${trendDiff}% — keep going`
                  : "→ Same as last try"}
            </p>
          )}
        </div>
      </div>

      {(() => {
        const bars = [
          ...(vocabScore !== null
            ? [
                { label: "詞彙 Vocabulary", score: vocabScore, color: "#7c3aed" },
                { label: "發音 Pronunciation", score: pronScore!, color: "#059669" },
              ]
            : []),
          { label: "聲調 Tone accuracy", score: toneScore, color: "#d97706" },
        ];
        return bars.length > 0 ? (
          <div className="feedback-summary-bars">
            {bars.map(({ label, score, color }) => (
              <div key={label} className="feedback-summary-bar-row">
                <span className="feedback-summary-bar-label">{label}</span>
                <div className="feedback-summary-bar-track">
                  <div
                    className="feedback-summary-bar-fill"
                    style={{ width: `${score}%`, background: color }}
                  />
                </div>
                <span className="feedback-summary-bar-pct">{score}%</span>
              </div>
            ))}
          </div>
        ) : null;
      })()}

      {(pronScore !== null || toneScore > 0) && (
        <div className="score-guide">
          <p className="score-guide-heading"><BiLabel zh="如何達到 100%" en="How to reach 100%" /></p>
          <div className="score-guide-rows">
            {pronScore !== null && pronScore < 100 && (
              <div className="score-guide-row">
                <span className="score-guide-label">Pronunciation</span>
                <ul className="score-guide-tips">
                  <li>
                    Hold each syllable long enough — short clipped sounds
                    confuse the detector.
                  </li>
                  <li>
                    Speak at a steady pace (4–5 syllables/sec). Too fast
                    collapses the pitch contour.
                  </li>
                  <li>
                    Exaggerate each tone: make rising higher, falling sharper,
                    dipping deeper.
                  </li>
                  <li>
                    Record in a quiet place — background noise flattens the
                    detected contour.
                  </li>
                </ul>
              </div>
            )}
            {toneScore < 100 && (
              <div className="score-guide-row">
                <span className="score-guide-label">Tone accuracy</span>
                <ul className="score-guide-tips">
                  <li>
                    <strong>Tone 1 (ā) →</strong> Keep pitch high and completely
                    flat throughout.
                  </li>
                  <li>
                    <strong>Tone 2 (á) ↗</strong> Start mid, push pitch up to
                    the top — like asking a question.
                  </li>
                  <li>
                    <strong>Tone 3 (ǎ) ↘↗</strong> Dip down first, then rise
                    back — the lowest point matters most.
                  </li>
                  <li>
                    <strong>Tone 4 (à) ↘</strong> Start as high as you can and
                    drop sharply to the bottom.
                  </li>
                  <li>
                    Isolate problem characters from the Tone Drill panel and
                    repeat them 5× before recording the full sentence.
                  </li>
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {transcription && (
        <p className="feedback-summary-transcript">
          You said: <em lang="zh-TW">"{transcription}"</em>
        </p>
      )}
    </div>
  );
}

const TONE_SHAPES: Record<
  string,
  { label: string; arrow: string; tip: string; drill: string }
> = {
  level: {
    label: "Level →",
    arrow: "→",
    tip: "Stays flat throughout.",
    drill: "Say it again and try to add more movement — either rise or fall.",
  },
  rising: {
    label: "Rising ↗",
    arrow: "↗",
    tip: "Pitch rises start to end.",
    drill: "Good upward shape. Make the start lower and push the end higher.",
  },
  falling: {
    label: "Falling ↘",
    arrow: "↘",
    tip: "Pitch falls start to end.",
    drill: "Good downward shape. Start high and let it drop sharply.",
  },
  dip: {
    label: "Dip ↘↗",
    arrow: "↘↗",
    tip: "Dips down, then rises.",
    drill: "Good dip shape. Make the lowest point deeper before rising back.",
  },
  variable: {
    label: "Unclear ??",
    arrow: "??",
    tip: "No clear shape was detected.",
    drill: "Isolate this character, say it 3 times slowly, then put it back.",
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
      <p className="recording-playback-label">Your recording</p>
      <audio controls src={url} className="recording-playback-audio" />
    </div>
  );
}

function ToneDrillPanel({ wordProsody }: { wordProsody: WordProsody[] }) {
  const problems = wordProsody
    .map((item) => {
      let priority = 0;
      if (item.contour_shape === "variable") priority += 4;
      if (item.pitch_range < 12) priority += 3; // too flat to read
      if (item.pitch_range > 110) priority += 2; // excessive movement
      return { item, priority };
    })
    .filter((e) => e.priority > 0)
    .sort((a, b) => b.priority - a.priority)
    .slice(0, 3)
    .map((e) => e.item);

  if (problems.length === 0) {
    return (
      <div className="tone-drill-panel tone-drill-clean">
        <span className="tone-drill-ok">
          All tones have clear shape — good work.
        </span>
      </div>
    );
  }

  return (
    <div className="tone-drill-panel">
      <p className="tone-drill-heading">Tone drill — focus characters</p>
      <div className="tone-drill-cards">
        {problems.map((item, i) => {
          const shape = TONE_SHAPES[item.contour_shape] ?? TONE_SHAPES.variable;
          return (
            <div key={`${item.token}-${i}`} className="tone-drill-card">
              <div className="tone-drill-char" lang="zh-TW">
                {item.token}
              </div>

              {/* Detected */}
              <div className="tone-drill-section">
                <span className="tone-drill-label">Detected</span>
                <div className="tone-drill-shape">
                  <span className="tone-arrow">{shape.arrow}</span>
                  <span className="tone-shape-label">{shape.label}</span>
                </div>
              </div>

              {/* Recommendation */}
              {/* <div className="tone-drill-section">
                <span className="tone-drill-label">Recommendation</span>
                <p className="tone-drill-tip">{shape.drill}</p>
              </div> */}

              {/* Detail */}
              <div className="tone-drill-section">
                <span className="tone-drill-label">
                  Detail
                  <a
                    className="tone-drill-detail-link"
                    href="#tone-shapes-reference"
                    title="See tone shapes reference"
                  >
                    ?
                  </a>
                </span>
                <p className="tone-drill-tip">{shape.tip}</p>
                <ol className="tone-drill-steps">
                  <li>
                    Say <strong lang="zh-TW">{item.token}</strong> alone —
                    exaggerate the movement.
                  </li>
                  <li>
                    Repeat 3×:{" "}
                    <strong lang="zh-TW">
                      {item.token} {item.token} {item.token}
                    </strong>
                  </li>
                  <li>Put it back into the full sentence and record again.</li>
                </ol>
              </div>
            </div>
          );
        })}
      </div>

      {/* Tone shapes reference table */}
      <div id="tone-shapes-reference" className="tone-shapes-reference">
        <p className="tone-drill-heading" style={{ marginBottom: 10 }}>
          Tone shapes reference
        </p>
        <table className="tone-ref-table">
          <thead>
            <tr>
              <th>Shape</th>
              <th>Arrow</th>
              <th>What it means</th>
              <th>How to fix</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(TONE_SHAPES).map(([key, s]) => (
              <tr key={key}>
                <td>
                  <strong>{s.label}</strong>
                </td>
                <td className="tone-ref-arrow">{s.arrow}</td>
                <td>{s.tip}</td>
                <td>{s.drill}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
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
        <span className="vocab-categorizer-title">Sort words into groups</span>
        {checked && (
          <span
            className={`vocab-categorizer-score ${correctCount === words.length ? "vc-score-perfect" : ""}`}
          >
            {correctCount}/{words.length} correct
          </span>
        )}
      </div>

      {unplaced.length > 0 && (
        <div className="vocab-categorizer-bank">
          <span className="vc-bank-label">
            Drag or click a word, then drop it into a group below
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
                        title={!checked ? "Click to move back" : undefined}
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
                  <span className="vc-group-empty">Drop here</span>
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
            {allPlaced
              ? "Check answers"
              : `${unplaced.length} word${unplaced.length > 1 ? "s" : ""} left to place`}
          </button>
        ) : (
          <div className="vc-result-row">
            {correctCount === words.length ? (
              <span className="vc-all-correct">
                All correct! Now record your sentence using these words.
              </span>
            ) : (
              <>
                <span className="vc-wrong-hint">
                  Words marked ✗ show the correct group — fix them and try
                  again.
                </span>
                <button
                  type="button"
                  className="vc-btn-retry"
                  onClick={handleReset}
                >
                  Try again
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
