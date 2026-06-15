import { useState, useCallback, useMemo } from "react";
import { toPinyin } from "../utils/pinyin";
import "./StoryConceptMap.css";

interface VocabGroup {
  name: string;
  words: string[];
}

interface Topic {
  id: string;
  name: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
}

interface Props {
  topic: Topic;
  defaultOpen?: boolean;
}

const CATEGORIES = [
  { id: "characters", hanzi: "人物", english: "Characters", color: "#4f46e5", border: "#818cf8" },
  { id: "setting",    hanzi: "場景", english: "Setting",    color: "#0891b2", border: "#67e8f9" },
  { id: "actions",    hanzi: "動作", english: "Actions",    color: "#d97706", border: "#fcd34d" },
  { id: "outcome",    hanzi: "結果", english: "Outcome",    color: "#059669", border: "#6ee7b7" },
];

function groupNameToCategoryId(name: string): string | null {
  const n = name.toLowerCase();
  if (n.includes("character") || n.includes("人物")) return "characters";
  if (n.includes("setting") || n.includes("place") || n.includes("場景") || n.includes("地點")) return "setting";
  if (n.includes("action") || n.includes("動作") || n.includes("活動")) return "actions";
  if (n.includes("outcome") || n.includes("result") || n.includes("event") || n.includes("結果") || n.includes("事件")) return "outcome";
  return null;
}

const CANVAS_W     = 860;
const CENTRAL_W    = 160;
const CENTRAL_H    = 70;
const CENTRAL_X    = CANVAS_W / 2 - CENTRAL_W / 2;
const CENTRAL_Y    = 24;
const CAT_W        = 172;
const CAT_GAP      = 16;
const CAT_Y        = CENTRAL_Y + CENTRAL_H + 72;
const N            = CATEGORIES.length;
const TOTAL_CATS_W = N * CAT_W + (N - 1) * CAT_GAP;
const CAT_START_X  = (CANVAS_W - TOTAL_CATS_W) / 2;

const catLeft    = (i: number) => CAT_START_X + i * (CAT_W + CAT_GAP);
const catCenterX = (i: number) => catLeft(i) + CAT_W / 2;

function shuffleArr<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function StoryConceptMap({ topic, defaultOpen = false }: Props) {
  const [placed, setPlaced] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(CATEGORIES.map(c => [c.id, []]))
  );
  const [dragOver, setDragOver]   = useState<string | null>(null);
  const [checked, setChecked]     = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [isOpen, setIsOpen]       = useState(defaultOpen);

  const answerKey = useMemo<Record<string, string>>(() => {
    const key: Record<string, string> = {};
    if (!topic.vocabularyGroups) return key;
    for (const groups of Object.values(topic.vocabularyGroups)) {
      for (const group of groups) {
        const catId = groupNameToCategoryId(group.name);
        if (catId) {
          for (const word of group.words) key[word] = catId;
        }
      }
    }
    return key;
  }, [topic.id, topic.vocabularyGroups]);

  const hasAnswerKey = Object.keys(answerKey).length > 0;

  const wordScene = useMemo<Record<string, number>>(() => {
    const map: Record<string, number> = {};
    for (const [sceneIdx, vocab] of Object.entries(topic.vocabulary)) {
      for (const w of vocab as string[]) {
        if (!(w in map)) map[w] = Number(sceneIdx);
      }
    }
    return map;
  }, [topic.id]);

  const allWords = useMemo<string[]>(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const vocab of Object.values(topic.vocabulary)) {
      for (const w of vocab as string[]) {
        if (!seen.has(w)) { seen.add(w); out.push(w); }
      }
    }
    return shuffleArr(out);
  }, [topic.id]);

  const reset = useCallback(() => {
    setPlaced(Object.fromEntries(CATEGORIES.map(c => [c.id, []])));
    setChecked(false);
    setSubmitted(false);
  }, [topic.id]);

  const usedWords   = new Set(Object.values(placed).flat());
  const totalPlaced = usedWords.size;
  const totalWords  = allWords.length;

  function dropWordOnCategory(catId: string, word: string) {
    setChecked(false);
    setPlaced(prev => {
      const next: Record<string, string[]> = {};
      for (const [k, v] of Object.entries(prev)) next[k] = v.filter(w => w !== word);
      if (!next[catId].includes(word)) next[catId] = [...next[catId], word];
      return next;
    });
  }

  function removeFromCategory(catId: string, word: string, keepChecked = false) {
    if (!keepChecked) setChecked(false);
    setPlaced(prev => ({ ...prev, [catId]: prev[catId].filter(w => w !== word) }));
  }

  const wordResult = useMemo<Record<string, "correct" | "wrong">>(() => {
    if (!checked || !hasAnswerKey) return {};
    const result: Record<string, "correct" | "wrong"> = {};
    for (const [catId, words] of Object.entries(placed)) {
      for (const word of words) {
        result[word] = answerKey[word] === catId ? "correct" : "wrong";
      }
    }
    return result;
  }, [checked, placed, answerKey]);

  const checkedCorrect = Object.values(wordResult).filter(v => v === "correct").length;
  const checkedWrong   = Object.values(wordResult).filter(v => v === "wrong").length;
  const allCorrect     = checked && hasAnswerKey && checkedWrong === 0 && totalPlaced === totalWords;

  const maxWordsInCat = Math.max(1, ...CATEGORIES.map(c => placed[c.id].length));
  const CANVAS_H = CAT_Y + 54 + maxWordsInCat * 40 + 60;

  if (!isOpen) {
    return (
      <div className="scmap-collapsed" onClick={() => setIsOpen(true)}>
        <span className="scmap-collapsed-icon">🗺️</span>
        <div className="scmap-collapsed-text">
          <strong>Story Concept Map</strong>
          <span>Organize story vocabulary · {totalPlaced}/{totalWords} placed</span>
        </div>
        <span className="scmap-collapsed-caret">▼ Open</span>
      </div>
    );
  }

  return (
    <div className="scmap-root">

      <div className="scmap-toolbar">
        <div className="scmap-toolbar-left">
          <div className="scmap-score-badge">
            Words placed: <span>{totalPlaced}</span> / {totalWords}
          </div>
          <button className="scmap-tbtn" onClick={reset} disabled={submitted}>↺ Reset</button>
          <button
            className="scmap-tbtn scmap-tbtn-success"
            onClick={() => setChecked(true)}
            disabled={submitted || totalPlaced === 0}
          >
            ✓ Check
          </button>
          <button
            className={`scmap-tbtn scmap-tbtn-primary${submitted ? " is-submitted" : ""}`}
            onClick={() => { setSubmitted(true); setChecked(true); }}
            disabled={submitted}
          >
            {submitted ? "✓ Submitted" : "Submit"}
          </button>
        </div>
        <button className="scmap-tbtn" onClick={() => setIsOpen(false)}>▲ Hide</button>
      </div>

      {checked && hasAnswerKey && (
        <div className={`scmap-check-banner${allCorrect ? " scmap-check-banner-perfect" : ""}`}>
          {allCorrect
            ? "🎉 All words in the right category! 太棒了！ Now continue to speaking."
            : `✓ ${checkedCorrect} correct · ✗ ${checkedWrong} wrong — words marked ✗ show the correct category. Remove them and try again.`}
        </div>
      )}
      {checked && !hasAnswerKey && (
        <div className="scmap-check-banner">
          {totalPlaced === totalWords
            ? "🎉 All words placed! Ask your teacher to review your concept map."
            : `${totalPlaced}/${totalWords} words placed. Keep going!`}
        </div>
      )}

      <div className="scmap-main">

        <div className="scmap-word-bank">
          <h3>📚 Word Bank</h3>
          {allWords.length > 0 && (
            <div className="scmap-scene-legend">
              {Array.from(new Set(Object.keys(topic.vocabulary).map(Number))).sort((a, b) => a - b).map(si => (
                <span key={si} className={`chip-scene chip-scene-${si % 6}`}>S{si + 1}</span>
              ))}
              <span className="scmap-legend-hint">= scene</span>
            </div>
          )}
          {allWords.length === 0 ? (
            <div className="scmap-bank-empty">
              <span className="scmap-bank-empty-icon">📝</span>
              <p>No vocabulary yet.</p>
              <p>Ask your teacher to add words to this story.</p>
            </div>
          ) : allWords.map((w, i) => {
            const used = usedWords.has(w);
            return (
              <div
                key={`${w}-${i}`}
                className={`scmap-word-chip${used ? " used" : ""}${submitted ? " used" : ""}`}
                draggable={!used && !submitted}
                onDragStart={e => {
                  if (!used && !submitted) {
                    e.dataTransfer.setData("text/plain", w);
                    e.dataTransfer.effectAllowed = "move";
                  }
                }}
              >
                <span className="chip-hanzi">
                  {w}
                  {toPinyin(w) && <span className="chip-pinyin">{toPinyin(w)}</span>}
                </span>
                <span className={`chip-scene chip-scene-${(wordScene[w] ?? 0) % 6}`}>
                  S{(wordScene[w] ?? 0) + 1}
                </span>
                {used && <span className="chip-check">✓</span>}
              </div>
            );
          })}
        </div>

        <div className="scmap-canvas-wrapper">
          <div className="scmap-canvas" style={{ width: CANVAS_W, height: CANVAS_H }}>

            <svg
              className="scmap-svg"
              viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
              style={{ width: CANVAS_W, height: CANVAS_H }}
            >
              {CATEGORIES.map((cat, i) => (
                <line
                  key={cat.id}
                  x1={CENTRAL_X + CENTRAL_W / 2} y1={CENTRAL_Y + CENTRAL_H}
                  x2={catCenterX(i)}             y2={CAT_Y}
                  stroke="#a5b4fc" strokeWidth="2" strokeLinecap="round" strokeDasharray="6 4"
                />
              ))}
            </svg>

            <div
              className="scmap-central"
              style={{ left: CENTRAL_X, top: CENTRAL_Y, width: CENTRAL_W, height: CENTRAL_H }}
            >
              <span className="central-topic-label">{topic.name}</span>
            </div>

            {CATEGORIES.map((cat, i) => {
              const words = placed[cat.id] ?? [];
              const isOver = dragOver === cat.id;

              return (
                <div
                  key={cat.id}
                  className={`scmap-cat-node${isOver ? " drag-over" : ""}${submitted ? " is-submitted" : ""}`}
                  style={{ left: catLeft(i), top: CAT_Y, width: CAT_W, borderColor: cat.border }}
                  onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setDragOver(cat.id); }}
                  onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(null); }}
                  onDrop={e => {
                    e.preventDefault();
                    const word = e.dataTransfer.getData("text/plain");
                    if (word) dropWordOnCategory(cat.id, word);
                    setDragOver(null);
                  }}
                >
                  <div className="scmap-cat-header" style={{ background: cat.color }}>
                    <span className="cat-hanzi">{cat.hanzi}</span>
                    <span className="cat-english">{cat.english}</span>
                  </div>

                  <div className="scmap-cat-words">
                    {words.length === 0 ? (
                      <div className="scmap-cat-empty">
                        {isOver ? "Release to place" : "Drop words here"}
                      </div>
                    ) : words.map(w => {
                      const result = wordResult[w];
                      const correctCatId = result === "wrong" ? answerKey[w] : null;
                      const correctCat = correctCatId ? CATEGORIES.find(c => c.id === correctCatId) : null;
                      return (
                        <div
                          key={w}
                          className={`scmap-cat-word${result === "correct" ? " word-correct" : result === "wrong" ? " word-wrong" : ""}`}
                        >
                          <span className="cat-word-text">
                            {w}
                            {toPinyin(w) && <span className="chip-pinyin">{toPinyin(w)}</span>}
                          </span>
                          {result === "correct" && <span className="cat-word-icon">✓</span>}
                          {result === "wrong" && correctCat && (
                            <span className="cat-word-hint">→ {correctCat.english}</span>
                          )}
                          {!submitted && (
                            <button
                              className={`cat-word-remove${result === "wrong" ? " cat-word-remove-wrong" : ""}`}
                              onClick={() => removeFromCategory(cat.id, w, result === "wrong")}
                              title={result === "wrong" ? "Wrong — click to move back" : "Remove"}
                            >×</button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

          </div>
        </div>
      </div>
    </div>
  );
}
