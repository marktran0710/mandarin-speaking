import { type ChangeEvent, useEffect, useRef, useState } from "react";
import StudentPageHeader from "../components/StudentPageHeader";
import StudentAudioActionPanel from "../components/StudentAudioActionPanel";
import { BiLabel } from "../components/BiLabel";
import { convertBlobToWav } from "../utils/audio";
import { ensureWavBlob, formatBackendError, normalizeWavFileName, readErrorResponse } from "./voice-test/helpers";
import VoiceTestResults from "./voice-test/VoiceTestResults";
import type { VoiceMetrics } from "./voice-test/types";
import { getBackendUrl as getRuntimeBackendUrl, getVoiceTestAsrModel } from "../config/runtimeEnv";
import "../components/BiLabel.css";
import "./VoiceTestPage.css";

const BACKEND_URL = getRuntimeBackendUrl();
const VOICE_TEST_ASR_MODEL = getVoiceTestAsrModel();

export default function VoiceTestPage() {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [metrics, setMetrics] = useState<VoiceMetrics | null>(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [pendingAudio, setPendingAudio] = useState<Blob | null>(null);
  const [pendingAudioName, setPendingAudioName] = useState("");
  const [pendingTranscription, setPendingTranscription] = useState("");
  const [selectedAudioName, setSelectedAudioName] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");
  const [analysisAttemptCount, setAnalysisAttemptCount] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const transcriptRef = useRef("");
  const startTimeRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const preparationIdRef = useRef(0);
  const audioUrlRef = useRef("");
  const analysisControllerRef = useRef<AbortController | null>(null);

  const clearAudioPreview = () => { if (audioUrlRef.current) { URL.revokeObjectURL?.(audioUrlRef.current); audioUrlRef.current = ""; } setAudioUrl(""); };
  const clearDurationTimer = () => { if (durationTimerRef.current) { clearInterval(durationTimerRef.current); durationTimerRef.current = null; } };
  const stopTracks = () => { recognitionRef.current = null; streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null; };
  useEffect(() => () => { mountedRef.current = false; preparationIdRef.current += 1; analysisControllerRef.current?.abort(); recognitionRef.current?.abort?.(); if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop(); streamRef.current?.getTracks().forEach((track) => track.stop()); if (durationTimerRef.current) clearInterval(durationTimerRef.current); if (audioUrlRef.current) URL.revokeObjectURL?.(audioUrlRef.current); }, []);

  const startSpeechRecognition = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) { setLiveTranscript("瀏覽器不支援即時語音轉錄。 Browser speech transcription is not available."); return; }
    const recognition = new SpeechRecognition(); recognition.continuous = true; recognition.interimResults = true; recognition.lang = "zh-TW";
    recognition.onresult = (event: any) => { let finalText = transcriptRef.current; let interimText = ""; for (let index = event.resultIndex; index < event.results.length; index += 1) { const text = event.results[index][0].transcript; if (event.results[index].isFinal) finalText = `${finalText} ${text}`.trim(); else interimText = `${interimText} ${text}`.trim(); } transcriptRef.current = finalText; setLiveTranscript([finalText, interimText].filter(Boolean).join(" ")); };
    recognition.onerror = () => setLiveTranscript(transcriptRef.current || "瀏覽器語音轉錄已停止，Praat 仍會分析這段音檔。 Browser speech transcription stopped. Praat will still analyze the audio.");
    recognitionRef.current = recognition; recognition.start();
  };
  const prepareAudio = async (rawBlob: Blob, fileName = "voice-test.wav", shouldConvertToWav = true, transcription = "") => {
    const preparationId = ++preparationIdRef.current;
    try { const wavBlob = shouldConvertToWav ? await convertBlobToWav(rawBlob) : rawBlob; const normalizedWavBlob = ensureWavBlob(wavBlob); if (!mountedRef.current || preparationId !== preparationIdRef.current) return; clearAudioPreview(); const nextAudioUrl = URL.createObjectURL(normalizedWavBlob); audioUrlRef.current = nextAudioUrl; setAudioBlob(normalizedWavBlob); setAudioUrl(nextAudioUrl); setPendingAudio(normalizedWavBlob); setPendingAudioName(fileName); setPendingTranscription(transcription); setMetrics(null); setError(""); } catch (err) { if (mountedRef.current && preparationId === preparationIdRef.current) setError(formatBackendError(err, BACKEND_URL || "the configured backend")); }
  };
  const startRecording = async () => {
    const recordingId = ++preparationIdRef.current; analysisControllerRef.current?.abort(); analysisControllerRef.current = null; setError(""); setMetrics(null); clearAudioPreview(); setAudioBlob(null); setPendingAudio(null); setPendingAudioName(""); setPendingTranscription(""); setSelectedAudioName(""); setLiveTranscript(""); transcriptRef.current = ""; setRecordingDuration(0);
    try { const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); streamRef.current = stream; chunksRef.current = []; const preferredType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : ""; const recorder = new MediaRecorder(stream, preferredType ? { mimeType: preferredType } : undefined); mediaRecorderRef.current = recorder; recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); }; recorder.onstop = async () => { const rawBlob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }); stopTracks(); if (recordingId !== preparationIdRef.current) return; await prepareAudio(rawBlob, "voice-test.wav", true, transcriptRef.current.trim()); }; startTimeRef.current = Date.now(); durationTimerRef.current = setInterval(() => setRecordingDuration(Math.floor((Date.now() - startTimeRef.current) / 1000)), 250); recorder.start(); startSpeechRecognition(); setIsRecording(true); } catch (err) { setError(err instanceof Error ? err.message : "無法存取麥克風。 Could not access microphone."); stopTracks(); clearDurationTimer(); }
  };
  const stopRecording = () => { recognitionRef.current?.stop(); if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop(); setIsRecording(false); clearDurationTimer(); };
  const handleImportWav = async (event: ChangeEvent<HTMLInputElement>) => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return; const isWav = file.type === "audio/wav" || file.type === "audio/wave" || file.type === "audio/x-wav" || file.type === "audio/vnd.wave" || file.name.toLowerCase().endsWith(".wav"); if (!isWav) { setError(`匯入的檔案格式不支援，請上傳 WAV 檔案。 Import a WAV file. "${file.name}" is not supported yet.`); return; } setError(""); setMetrics(null); setRecordingDuration(0); preparationIdRef.current += 1; analysisControllerRef.current?.abort(); analysisControllerRef.current = null; clearAudioPreview(); setPendingAudio(null); setPendingAudioName(""); setPendingTranscription(""); setSelectedAudioName(file.name); await prepareAudio(file, normalizeWavFileName(file.name), false); };
  const analyzeAudio = async () => { if (!pendingAudio) return; const controller = new AbortController(); const timeoutId = window.setTimeout(() => controller.abort(), 120_000); analysisControllerRef.current?.abort(); analysisControllerRef.current = controller; setIsAnalyzing(true); setMetrics(null); try { const formData = new FormData(); formData.append("file", pendingAudio, pendingAudioName || "voice-test.wav"); formData.append("transcription", pendingTranscription); if (!pendingTranscription.trim()) formData.append("asr_model", VOICE_TEST_ASR_MODEL); const response = await fetch(`${getBackendUrl()}/api/analyze`, { method: "POST", body: formData, signal: controller.signal }); if (!response.ok) { const errorData = await readErrorResponse(response); throw new Error(errorData.detail || "語音分析失敗。 Voice analysis failed."); } const nextMetrics = (await response.json()) as VoiceMetrics; if (mountedRef.current && analysisControllerRef.current === controller) { setMetrics(nextMetrics); setAnalysisAttemptCount((count) => count + 1); } } catch (err) { if (controller.signal.aborted && analysisControllerRef.current !== controller) return; if (controller.signal.aborted) { setError("Analysis took too long. Please try the recording again."); return; } setError(formatBackendError(err, BACKEND_URL || "the configured backend")); } finally { window.clearTimeout(timeoutId); if (analysisControllerRef.current === controller) { analysisControllerRef.current = null; if (mountedRef.current) setIsAnalyzing(false); } } };
  const primaryLabel = isRecording ? { zh: "停止，看回饋", pinyin: "Tíngzhǐ, kàn huíkuì", en: "Stop and get feedback" } : metrics ? { zh: "再錄一次", pinyin: "Zài lù yí cì", en: "Record again" } : { zh: "開始語音測試", pinyin: "Kāishǐ yǔyīn cèshì", en: "Start voice test" };
  return <main className="voice-test-page"><StudentPageHeader eyebrow={{ zh: "語音練習", pinyin: "Yǔyīn liànxí", en: "Voice practice" }} title={{ zh: "分析你的聲音", pinyin: "Fēnxī nǐ de shēngyīn", en: "Analyze Your Voice" }} lede={{ zh: "錄音或上傳 WAV 檔案，系統會轉錄音檔，然後檢查發音和語言表現，給你回饋。", pinyin: "Lùyīn huò shàngchuán WAV dǎng'àn, xìtǒng huì zhuǎnlù yīndǎng, ránhòu jiǎnchá fāyīn hé yǔyán biǎoxiàn, gěi nǐ huíkuì.", en: "Record or upload a WAV file. The system transcribes the audio, then checks pronunciation and language feedback from the recording." }} />
    <section className="voice-test-hero"><div className="voice-test-status"><span><BiLabel zh="狀態" pinyin="Zhuàngtài" en="Status" /></span><strong>{isRecording ? <BiLabel zh="錄音中" pinyin="Lùyīn zhōng" en="Recording" /> : isAnalyzing ? <BiLabel zh="分析中" pinyin="Fēnxī zhōng" en="Analyzing" /> : <BiLabel zh="準備好了" pinyin="Zhǔnbèi hǎo le" en="Ready" />}</strong><p>{isRecording ? <BiLabel zh={`已錄音 ${recordingDuration} 秒`} pinyin={`Yǐ lùyīn ${recordingDuration} miǎo`} en={`${recordingDuration}s recorded`} /> : <BiLabel zh="錄一次就夠了。" pinyin="Lù yí cì jiù gòu le." en="One recording is enough." />}</p></div></section>
    <section className="voice-test-workspace"><StudentAudioActionPanel className="voice-test-controls" primaryIcon={metrics ? "retry" : "record"} primaryLabel={primaryLabel.en} uploadLabel="Import WAV file" accept=".wav,audio/wav,audio/wave,audio/x-wav,audio/vnd.wave" onPrimaryAction={isRecording ? stopRecording : startRecording} onFileChange={handleImportWav} isRecording={isRecording} isAnalyzing={isAnalyzing} hasPendingAudio={Boolean(pendingAudio && !metrics)} onAnalyze={pendingAudio && !metrics ? () => void analyzeAudio() : undefined} status={isRecording ? `${recordingDuration}s recorded` : isAnalyzing ? "Running voice analysis..." : "One recording is enough."} readyMessage={null} />
      <div className="voice-step-row voice-step-row-legacy" aria-label="Voice test steps"><span><BiLabel zh="1. 說話或上傳" pinyin="1. Shuōhuà huò shàngchuán" en="1. Speak or upload" /></span><span><BiLabel zh="2. 轉錄音檔" pinyin="2. Zhuǎnlù yīndǎng" en="2. Transcribe audio" /></span><span><BiLabel zh="3. 查看結果" pinyin="3. Chákàn jiéguǒ" en="3. Review" /></span></div>
      {audioUrl && <div className="voice-audio-preview"><span id="voice-audio-preview-label"><BiLabel zh="錄音預覽" pinyin="Lùyīn yùlǎn" en="Recording preview" /></span>{selectedAudioName && <strong>{selectedAudioName}</strong>}<audio controls src={audioUrl} aria-labelledby="voice-audio-preview-label" /></div>}
      {pendingAudio && !metrics && !isAnalyzing && <p className="voice-audio-ready"><span>Audio ready — review it, then analyze</span></p>}
      {liveTranscript && <div className="voice-live-transcript"><span><BiLabel zh="即時轉錄" pinyin="Jíshí zhuǎnlù" en="Live transcript" /></span><p>{liveTranscript}</p></div>}
    </section>{isAnalyzing && <p className="voice-test-loading"><BiLabel zh="正在執行 Praat 分析和本地回饋…" pinyin="Zhèngzài zhíxíng Praat fēnxī hé běndì huíkuì…" en="Running Praat and local feedback..." /></p>}{error && <p className="voice-test-error">{error}</p>}{metrics && <VoiceTestResults metrics={metrics} audioBlob={audioBlob} attemptCount={analysisAttemptCount} />}</main>;
}

function getBackendUrl(): string {
  if (BACKEND_URL) return BACKEND_URL;
  throw new Error("語音測試需要正式部署的後端。請部署 FastAPI 後端並設定 VITE_BACKEND_URL。 Voice testing needs a deployed backend in production. Deploy the FastAPI backend and set VITE_BACKEND_URL.");
}
