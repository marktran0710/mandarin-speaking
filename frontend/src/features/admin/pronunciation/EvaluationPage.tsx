import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { convertBlobToWav } from "@entities/audio";
import { publishedTopicsFromStories } from "@entities/story";
import type { Topic } from "@entities/topic";
import {
  evaluatePronunciation,
  PronunciationRequestError,
  type PronunciationEvaluation,
} from "@shared/api/pronunciation";
import { canUseDatabase, listCustomStories } from "../../../services/database";
import PronunciationResult from "./Result";
import { evaluationScenes } from "./model";
import "./EvaluationPage.css";

const MAX_RECORDING_SECONDS = 30;

/** Try the pronunciation evaluator on a real scene: Praat measures the pitch,
 * fixed rules give the score, and the configured model only explains it. */
export default function PronunciationEvaluationPage() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState("");
  const [sceneIndex, setSceneIndex] = useState<number | null>(null);
  const [isLoadingTopics, setIsLoadingTopics] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PronunciationEvaluation | null>(null);
  const [audioUrl, setAudioUrl] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const audioUrlRef = useRef("");
  const uploadRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!canUseDatabase()) {
      setIsLoadingTopics(false);
      return;
    }
    let active = true;
    void listCustomStories({ includeReferenceData: false })
      .then((stories) => {
        if (!active) return;
        const published = publishedTopicsFromStories(stories).filter((topic) => evaluationScenes(topic).length > 0);
        setTopics(published);
        setTopicId((current) => current || published[0]?.id || "");
      })
      .catch(() => {
        if (active) setError("Could not load the published stories.");
      })
      .finally(() => {
        if (active) setIsLoadingTopics(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(
    () => () => {
      if (stopTimerRef.current) clearTimeout(stopTimerRef.current);
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        recorder.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    },
    [],
  );

  const topic = topics.find((candidate) => candidate.id === topicId) ?? topics[0];
  const scenes = useMemo(() => evaluationScenes(topic), [topic]);
  const scene = scenes.find((candidate) => candidate.index === sceneIndex) ?? scenes[0];
  const isBusy = isRecording || isEvaluating;

  const clearAudioPreview = () => {
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = "";
    setAudioUrl("");
  };

  const resetEvaluation = () => {
    clearAudioPreview();
    setResult(null);
    setError("");
  };

  const showAudio = (blob: Blob) => {
    clearAudioPreview();
    audioUrlRef.current = URL.createObjectURL(blob);
    setAudioUrl(audioUrlRef.current);
  };

  const evaluate = async (rawBlob: Blob) => {
    if (!topic || !scene) return;
    const request = {
      storyId: topic.sourceStory?.id ?? topic.id,
      sceneIndex: scene.index,
    };
    setIsEvaluating(true);
    setError("");
    setResult(null);
    clearAudioPreview();
    try {
      const wav = await convertBlobToWav(rawBlob);
      showAudio(wav);
      setResult(await evaluatePronunciation(wav, request));
    } catch (caught) {
      setError(
        caught instanceof PronunciationRequestError
          ? `${caught.message} (${caught.code})`
          : caught instanceof Error
            ? caught.message
            : "Could not evaluate this recording.",
      );
    } finally {
      setIsEvaluating(false);
    }
  };

  const stopRecording = () => {
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current);
    stopTimerRef.current = null;
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  };

  const startRecording = async () => {
    resetEvaluation();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => event.data.size > 0 && chunksRef.current.push(event.data);
      recorder.onstop = () => {
        if (stopTimerRef.current) clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        setIsRecording(false);
        const recording = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (recording.size === 0) {
          setError("The browser did not capture any audio. Please try again or upload a recording.");
          return;
        }
        void evaluate(recording);
      };
      recorder.start();
      setIsRecording(true);
      stopTimerRef.current = setTimeout(stopRecording, MAX_RECORDING_SECONDS * 1000);
    } catch {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      recorderRef.current = null;
      setIsRecording(false);
      setError("Could not use the microphone. Check the browser permission, or upload a recording instead.");
    }
  };

  const onUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void evaluate(file);
  };

  const onTopicChange = (event: ChangeEvent<HTMLSelectElement>) => {
    resetEvaluation();
    setTopicId(event.target.value);
    setSceneIndex(null);
  };

  const onSceneChange = (event: ChangeEvent<HTMLSelectElement>) => {
    resetEvaluation();
    setSceneIndex(Number(event.target.value));
  };

  return (
    <div className="pron-page" aria-busy={isEvaluating}>
      <p className="pron-intro">
        Record the scene's sentence. Pitch and timing are measured with Praat and compared with the teacher's recording;
        the score comes from fixed rules and the language model only explains it. Nothing here affects student progress.
      </p>

      <div className="pron-controls">
        <label>
          <span>Story</span>
          <select value={topic?.id ?? ""} onChange={onTopicChange} disabled={topics.length === 0 || isBusy}>
            {topics.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>{candidate.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Scene</span>
          <select value={scene?.index ?? ""} onChange={onSceneChange} disabled={scenes.length === 0 || isBusy}>
            {scenes.map((candidate) => (
              <option key={candidate.index} value={candidate.index}>{`${candidate.index + 1}. ${candidate.text}`}</option>
            ))}
          </select>
        </label>
      </div>

      {isLoadingTopics ? (
        <p className="pron-status" role="status">Loading published stories…</p>
      ) : topics.length === 0 ? (
        <p className="pron-note">No published story has both a target sentence and teacher recording yet.</p>
      ) : null}
      {scene?.text && <p className="pron-target" lang="zh-Hant">{scene.text}</p>}

      <div className="pron-actions">
        {isRecording ? (
          <button type="button" className="pron-record is-recording" onClick={stopRecording}>Stop and evaluate</button>
        ) : (
          <button type="button" className="pron-record" onClick={() => void startRecording()} disabled={!scene || isEvaluating}>
            Record
          </button>
        )}
        <button type="button" className="secondary" onClick={() => uploadRef.current?.click()} disabled={!scene || isBusy}>
          Upload a recording
        </button>
        <input ref={uploadRef} type="file" accept="audio/*" hidden onChange={onUpload} aria-label="Upload a recording" />
        {audioUrl && <audio controls src={audioUrl} aria-label="Your recording" />}
      </div>

      {isEvaluating && <p className="pron-status" role="status">Measuring pitch and writing feedback…</p>}
      {error && <p className="admin-error" role="alert">{error}</p>}
      {result && <PronunciationResult result={result} />}
    </div>
  );
}
