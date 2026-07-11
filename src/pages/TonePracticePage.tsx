import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { BiLabel } from "../components/BiLabel";
import PitchOverlay from "../components/PitchOverlay";
import ToneShapeIcon, { type ToneGroup } from "../components/ToneShapeIcon";
import { scoreTier, scoreTierLabel } from "../utils/scoreLabels";
import {
  useWordPronunciationPractice,
  type WordAnalyzeResult,
} from "../hooks/useWordPronunciationPractice";
import "./TonePracticePage.css";

interface PracticeWord {
  id: string;
  text: string;
  pinyin: string;
  gloss: string;
  tone: ToneGroup;
}

// A small, hand-picked bank: four single-character syllables per canonical
// tone (so a beginner can isolate one tone shape at a time), plus a few
// everyday two-character words so practice isn't limited to isolated
// syllables. Tone grouping here is only for the picker UI — the backend
// independently derives the real expected tone(s) for scoring from the
// character itself via pypinyin, so a wrong label here couldn't skew scoring.
const PRACTICE_WORDS: PracticeWord[] = [
  { id: "ma1", text: "媽", pinyin: "mā", gloss: "mom", tone: 1 },
  { id: "tian1", text: "天", pinyin: "tiān", gloss: "sky / day", tone: 1 },
  { id: "san1", text: "三", pinyin: "sān", gloss: "three", tone: 1 },
  { id: "he1", text: "喝", pinyin: "hē", gloss: "drink", tone: 1 },

  { id: "ma2", text: "麻", pinyin: "má", gloss: "hemp / numb", tone: 2 },
  { id: "xue2", text: "學", pinyin: "xué", gloss: "study", tone: 2 },
  { id: "lai2", text: "來", pinyin: "lái", gloss: "come", tone: 2 },
  { id: "ren2", text: "人", pinyin: "rén", gloss: "person", tone: 2 },

  { id: "ma3", text: "馬", pinyin: "mǎ", gloss: "horse", tone: 3 },
  { id: "hao3", text: "好", pinyin: "hǎo", gloss: "good", tone: 3 },
  { id: "wo3", text: "我", pinyin: "wǒ", gloss: "I / me", tone: 3 },
  { id: "jiu3", text: "九", pinyin: "jiǔ", gloss: "nine", tone: 3 },

  { id: "ma4", text: "罵", pinyin: "mà", gloss: "scold", tone: 4 },
  { id: "shi4", text: "是", pinyin: "shì", gloss: "is / am", tone: 4 },
  { id: "da4", text: "大", pinyin: "dà", gloss: "big", tone: 4 },
  { id: "xie4", text: "謝", pinyin: "xiè", gloss: "thank", tone: 4 },

  { id: "nihao", text: "你好", pinyin: "nǐ hǎo", gloss: "hello", tone: "mixed" },
  { id: "xiexie", text: "謝謝", pinyin: "xiè xie", gloss: "thank you", tone: "mixed" },
  { id: "zaijian", text: "再見", pinyin: "zài jiàn", gloss: "goodbye", tone: "mixed" },
  { id: "zaoan", text: "早安", pinyin: "zǎo ān", gloss: "good morning", tone: "mixed" },
];

const FILTERS: Array<{ id: ToneGroup | "all"; label: string }> = [
  { id: "all", label: "All" },
  { id: 1, label: "Tone 1" },
  { id: 2, label: "Tone 2" },
  { id: 3, label: "Tone 3" },
  { id: 4, label: "Tone 4" },
  { id: "mixed", label: "Words" },
];

interface Attempt {
  score: number;
  at: number;
}

const BEST_SCORES_KEY = "tonePracticeBestScores";

function loadBestScores(): Record<string, number> {
  try {
    const raw = localStorage.getItem(BEST_SCORES_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveBestScores(scores: Record<string, number>) {
  try {
    localStorage.setItem(BEST_SCORES_KEY, JSON.stringify(scores));
  } catch {
    /* storage unavailable — best-score memory just won't persist */
  }
}

export default function TonePracticePage() {
  const [filter, setFilter] = useState<ToneGroup | "all">("all");
  const [selected, setSelected] = useState<PracticeWord>(PRACTICE_WORDS[0]);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [bestScores, setBestScores] = useState<Record<string, number>>(() => loadBestScores());

  const {
    isRecording,
    isAnalyzing,
    error,
    setError,
    result,
    startRecording,
    stopRecording,
    analyzeBlob,
    reset,
  } = useWordPronunciationPractice(selected.text, selected.pinyin);

  const visibleWords = useMemo(
    () => (filter === "all" ? PRACTICE_WORDS : PRACTICE_WORDS.filter((w) => w.tone === filter)),
    [filter],
  );

  // Track attempt history / best score whenever a new analysis result comes in.
  useEffect(() => {
    if (!result) return;
    const score = result.word_prosody?.[0]?.tone_accuracy ?? result.tone_accuracy ?? 0;
    setAttempts((prev) => [...prev, { score, at: Date.now() }]);
    setBestScores((prev) => {
      const next = { ...prev, [selected.id]: Math.max(prev[selected.id] || 0, score) };
      saveBestScores(next);
      return next;
    });
    // Only re-run when a fresh result arrives, not when `selected` changes on its own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const chooseWord = (word: PracticeWord) => {
    setSelected(word);
    reset();
    setAttempts([]);
  };

  const playExample = () => {
    if (!("speechSynthesis" in window)) {
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(selected.text);
    utterance.lang = "zh-TW";
    utterance.rate = 0.8;
    window.speechSynthesis.speak(utterance);
  };

  const handleImportFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!file.type.startsWith("audio/") && !/\.(wav|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name)) {
      setError(`"${file.name}" isn't an audio file.`);
      return;
    }

    await analyzeBlob(file);
  };

  const bestForSelected = bestScores[selected.id];
  const latestScore = attempts[attempts.length - 1]?.score;
  const previousScore = attempts[attempts.length - 2]?.score;

  return (
    <main className="tone-practice-page">
      <section className="tone-practice-hero">
        <p className="eyebrow">
          <BiLabel zh="聲調練習角" pinyin="Shēngdiào liànxí jiǎo" en="Tone practice corner" />
        </p>
        <h1>
          <BiLabel zh="試試你的聲調" pinyin="Shìshi nǐ de shēngdiào" en="Test your tone against the shape" />
        </h1>
        <p>
          <BiLabel
            zh="選一個字，聽範例，錄音，馬上看看你的音高曲線跟目標形狀有多接近。"
            pinyin="Xuǎn yí ge zì, tīng fànlì, lùyīn, mǎshàng kànkan nǐ de yīngāo qǔxiàn gēn mùbiāo xíngzhuàng yǒu duō jiējìn."
            en="Pick a character, listen to the example, record yourself, and see your pitch curve next to the target shape right away."
          />
        </p>
      </section>

      <section className="tone-practice-picker">
        <div className="tone-practice-filters" aria-label="Filter by tone">
          {FILTERS.map((f) => (
            <button
              key={String(f.id)}
              type="button"
              className={`tone-filter-chip ${filter === f.id ? "active" : ""}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="tone-practice-grid" aria-label="Practice words">
          {visibleWords.map((word) => {
            const best = bestScores[word.id];
            return (
              <button
                key={word.id}
                type="button"
                className={`tone-word-card ${selected.id === word.id ? "selected" : ""}`}
                onClick={() => chooseWord(word)}
              >
                <ToneShapeIcon tone={word.tone} />
                <strong>{word.text}</strong>
                <span>{word.pinyin}</span>
                <small>{word.gloss}</small>
                {typeof best === "number" && (
                  <em className={`tone-word-best ${scoreTier(best)}`}>
                    {scoreTierLabel(scoreTier(best)).zh}
                  </em>
                )}
              </button>
            );
          })}
        </div>
      </section>

      <section className="tone-practice-panel">
        <div className="tone-practice-target">
          <div className="tone-practice-target-main">
            <ToneShapeIcon tone={selected.tone} size={40} />
            <div>
              <strong className="tone-practice-char">{selected.text}</strong>
              <span className="tone-practice-pinyin">{selected.pinyin}</span>
              <span className="tone-practice-gloss">{selected.gloss}</span>
            </div>
          </div>
          <button type="button" className="btn btn-secondary" onClick={playExample}>
            <BiLabel zh="聽範例" pinyin="Tīng fànlì" en="Listen" />
          </button>
        </div>

        <div className="tone-practice-controls">
          <button
            type="button"
            className={`btn ${isRecording ? "btn-danger" : "btn-primary"}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing}
          >
            {isRecording ? (
              <BiLabel zh="停止，看結果" pinyin="Tíngzhǐ, kàn jiéguǒ" en="Stop and see result" />
            ) : result ? (
              <BiLabel zh="再試一次" pinyin="Zài shì yí cì" en="Try again" />
            ) : (
              <BiLabel zh="開始錄音" pinyin="Kāishǐ lùyīn" en="Record" />
            )}
          </button>
          <label
            className={`btn btn-secondary tone-practice-upload-label ${
              isRecording || isAnalyzing ? "disabled" : ""
            }`}
            role="button"
            tabIndex={isRecording || isAnalyzing ? -1 : 0}
          >
            <BiLabel zh="上傳音檔" pinyin="Shàngchuán yīndàng" en="Upload audio" />
            <input
              type="file"
              accept="audio/*,.wav,.webm,.mp3,.m4a,.ogg,.aac,.flac"
              className="tone-practice-upload-input"
              onChange={handleImportFile}
              disabled={isRecording || isAnalyzing}
            />
          </label>
          {attempts.length > 0 && (
            <span className="tone-practice-attempt-count">
              <BiLabel zh="第" pinyin="Dì" en="Attempt" /> {attempts.length}
              {typeof bestForSelected === "number" && (
                <>
                  {" · "}
                  <BiLabel zh="最佳" pinyin="Zuì jiā" en="Best" />{" "}
                  <span className={`score-tier-text ${scoreTier(bestForSelected)}`}>
                    {scoreTierLabel(scoreTier(bestForSelected)).zh}
                  </span>
                </>
              )}
            </span>
          )}
        </div>

        {isAnalyzing && (
          <p className="tone-practice-status">
            <BiLabel zh="正在分析你的聲音…" pinyin="Zhèngzài fēnxī nǐ de shēngyīn…" en="Analyzing your voice…" />
          </p>
        )}
        {error && <p className="tone-practice-error">{error}</p>}

        {result && !isAnalyzing && (
          <ToneMatchResult
            result={result}
            targetText={selected.text}
            latestScore={latestScore}
            previousScore={attempts.length > 1 ? previousScore : undefined}
          />
        )}

        {result && !isAnalyzing && (
          <div className="tone-practice-retry-row">
            <NextWordButton words={visibleWords} current={selected} onChoose={chooseWord} />
          </div>
        )}
      </section>
    </main>
  );
}

function NextWordButton({
  words,
  current,
  onChoose,
}: {
  words: PracticeWord[];
  current: PracticeWord;
  onChoose: (word: PracticeWord) => void;
}) {
  const currentIndex = words.findIndex((w) => w.id === current.id);
  const next = words[(currentIndex + 1) % words.length];

  if (words.length < 2) {
    return null;
  }

  return (
    <button type="button" className="btn btn-secondary" onClick={() => onChoose(next)}>
      <BiLabel zh="下一個字" pinyin="Xià yí ge zì" en="Next word" /> · {next.text}
    </button>
  );
}

function ToneMatchResult({
  result,
  targetText,
  latestScore,
  previousScore,
}: {
  result: WordAnalyzeResult;
  targetText: string;
  latestScore?: number;
  previousScore?: number;
}) {
  const segments = result.word_prosody || [];

  if (segments.length === 0) {
    return (
      <div className="tone-practice-result empty">
        <p>
          <BiLabel
            zh="沒聽清楚。再靠近麥克風一點，把字音拉長一點再試一次。"
            pinyin="Méi tīng qīngchu. Zài kàojìn màikèfēng yìdiǎn, bǎ zìyīn lā cháng yìdiǎn zài shì yí cì."
            en="Didn't catch enough of that. Move closer to the mic, hold the sound a little longer, and try again."
          />
        </p>
      </div>
    );
  }

  const trend =
    typeof latestScore === "number" && typeof previousScore === "number"
      ? Math.round(latestScore - previousScore)
      : undefined;

  return (
    <div className="tone-practice-result">
      {result.content_match === false && (
        <p className="tone-match-content-warning">
          <BiLabel
            zh={`聽起來不太像「${targetText}」，分數可能不準。再唸一次試試？`}
            pinyin={`Tīng qǐlái bú tài xiàng “${targetText}”, fēnshù kěnéng bù zhǔn. Zài niàn yí cì shìshi?`}
            en={`That didn't sound like "${targetText}" — the score above may not be reliable. Try recording it again?`}
          />
        </p>
      )}
      {segments.map((segment, index) => (
        <div className={`tone-match-card ${scoreTier(segment.tone_accuracy)}`} key={`${segment.token}-${index}`}>
          <div className="tone-match-header">
            <div className="tone-match-score-ring">
              <strong>{scoreTierLabel(scoreTier(segment.tone_accuracy)).zh}</strong>
            </div>
            <div className="tone-match-meta">
              <strong>{segment.token || targetText}</strong>
              {index === 0 && typeof trend === "number" && trend !== 0 && (
                <em className={trend > 0 ? "trend-up" : "trend-down"}>
                  {trend > 0 ? "↑" : "↓"} {Math.abs(trend)}% <BiLabel zh="比上次" pinyin="Bǐ shàngcì" en="vs last try" />
                </em>
              )}
            </div>
          </div>
          <PitchOverlay
            userContour={segment.pitch_contour}
            referenceContour={segment.reference_contour || []}
          />
          <p className="tone-match-feedback">{segment.feedback}</p>
        </div>
      ))}
    </div>
  );
}

