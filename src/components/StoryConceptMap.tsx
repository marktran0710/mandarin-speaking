import { useState, useCallback, useMemo } from "react";
import "./StoryConceptMap.css";

interface Topic {
  id: string;
  name: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
}

interface Props {
  topic: Topic;
  defaultOpen?: boolean;
}


// ── Fixed concept map categories ──────────────────────────────────────────────
const CATEGORIES = [
  { id: "characters", hanzi: "人物",   english: "Characters", color: "#4f46e5", border: "#818cf8" },
  { id: "places",     hanzi: "地點",   english: "Places",     color: "#0891b2", border: "#67e8f9" },
  { id: "events",     hanzi: "事件",   english: "Events",     color: "#d97706", border: "#fcd34d" },
  { id: "activities", hanzi: "活動",   english: "Activities", color: "#059669", border: "#6ee7b7" },
];

// ── Canvas geometry ───────────────────────────────────────────────────────────
const CANVAS_W    = 860;
const CENTRAL_W   = 160;
const CENTRAL_H   = 70;
const CENTRAL_X   = CANVAS_W / 2 - CENTRAL_W / 2;
const CENTRAL_Y   = 24;
const CAT_W       = 172;
const CAT_GAP     = 16;
const CAT_Y       = CENTRAL_Y + CENTRAL_H + 72;
const N           = CATEGORIES.length;
const TOTAL_CATS_W = N * CAT_W + (N - 1) * CAT_GAP;
const CAT_START_X  = (CANVAS_W - TOTAL_CATS_W) / 2;

const catLeft = (i: number) => CAT_START_X + i * (CAT_W + CAT_GAP);
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
  // placed: categoryId → list of hanzi strings placed there
  const [placed, setPlaced] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(CATEGORIES.map(c => [c.id, []]))
  );
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [modal, setModal] = useState<{ emoji: string; title: string; placed: number; total: number; msg: string } | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [isOpen, setIsOpen] = useState(defaultOpen);

  // All words from this story's vocabulary only (no generic extras)
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
    setModal(null);
    setSubmitted(false);
  }, [topic.id]);

  // Which words are already in a category
  const usedWords = new Set(Object.values(placed).flat());
  const totalPlaced = usedWords.size;
  const totalWords = allWords.length;

  function dropWordOnCategory(catId: string, word: string) {
    setPlaced(prev => {
      // Remove from any current category
      const next: Record<string, string[]> = {};
      for (const [k, v] of Object.entries(prev)) {
        next[k] = v.filter(w => w !== word);
      }
      if (!next[catId].includes(word)) {
        next[catId] = [...next[catId], word];
      }
      return next;
    });
  }

  function removeFromCategory(catId: string, word: string) {
    setPlaced(prev => ({
      ...prev,
      [catId]: prev[catId].filter(w => w !== word),
    }));
  }

  function checkAnswers() {
    const pct = totalWords > 0 ? Math.round((totalPlaced / totalWords) * 100) : 0;
    setModal({
      emoji: pct === 100 ? "🎉" : pct >= 60 ? "👍" : "📚",
      title: pct === 100 ? "Complete!" : pct >= 60 ? "Almost There!" : "Keep Going!",
      placed: totalPlaced,
      total: totalWords,
      msg:
        pct === 100
          ? "You've placed all words on the concept map! 太棒了！"
          : `${totalWords - totalPlaced} word(s) still in the bank. Try to place them all!`,
    });
  }

  function handleSubmit() {
    setSubmitted(true);
    const pct = totalWords > 0 ? Math.round((totalPlaced / totalWords) * 100) : 0;
    setModal({
      emoji: pct === 100 ? "🎉" : "✅",
      title: "Submitted!",
      placed: totalPlaced,
      total: totalWords,
      msg: "Your concept map has been recorded. Great thinking!",
    });
  }

  // Canvas height: enough for the category nodes + any number of words
  const maxWordsInCat = Math.max(1, ...CATEGORIES.map(c => placed[c.id].length));
  const CANVAS_H = CAT_Y + 54 + maxWordsInCat * 36 + 60;

  // ── Collapsed bar ──────────────────────────────────────────────────────────
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

      {/* ── Toolbar ── */}
      <div className="scmap-toolbar">
        <div className="scmap-toolbar-left">
          <div className="scmap-score-badge">
            Words placed: <span>{totalPlaced}</span> / {totalWords}
          </div>
          <button className="scmap-tbtn" onClick={reset} disabled={submitted}>↺ Reset</button>
          <button className="scmap-tbtn scmap-tbtn-success" onClick={checkAnswers} disabled={submitted}>
            ✓ Check
          </button>
          <button className="scmap-tbtn scmap-tbtn-primary" onClick={handleSubmit} disabled={submitted}>
            {submitted ? "✓ Submitted" : "Submit"}
          </button>
        </div>
        <button className="scmap-tbtn" onClick={() => setIsOpen(false)}>▲ Hide</button>
      </div>

      {/* ── Main: word bank + canvas ── */}
      <div className="scmap-main">

        {/* Word Bank */}
        <div className="scmap-word-bank">
          <h3>📚 Word Bank</h3>
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
                <span className="chip-hanzi">{w}</span>
                {used && <span className="chip-check">✓</span>}
              </div>
            );
          })}
        </div>

        {/* Canvas (scrollable, dot-grid) */}
        <div className="scmap-canvas-wrapper">
          <div className="scmap-canvas" style={{ width: CANVAS_W, height: CANVAS_H }}>

            {/* SVG connector lines */}
            <svg
              className="scmap-svg"
              viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
              style={{ width: CANVAS_W, height: CANVAS_H }}
            >
              {CATEGORIES.map((cat, i) => (
                <line
                  key={cat.id}
                  x1={CENTRAL_X + CENTRAL_W / 2}
                  y1={CENTRAL_Y + CENTRAL_H}
                  x2={catCenterX(i)}
                  y2={CAT_Y}
                  stroke="#a5b4fc"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeDasharray="6 4"
                />
              ))}
            </svg>

            {/* Central topic node */}
            <div
              className="scmap-central"
              style={{ left: CENTRAL_X, top: CENTRAL_Y, width: CENTRAL_W, height: CENTRAL_H }}
            >
              <span className="central-topic-label">{topic.name}</span>
            </div>

            {/* Category nodes (drop targets) */}
            {CATEGORIES.map((cat, i) => {
              const words = placed[cat.id] ?? [];
              const isOver = dragOver === cat.id;

              return (
                <div
                  key={cat.id}
                  className={`scmap-cat-node${isOver ? " drag-over" : ""}${submitted ? " is-submitted" : ""}`}
                  style={{ left: catLeft(i), top: CAT_Y, width: CAT_W, borderColor: cat.border }}
                  onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setDragOver(cat.id); }}
                  onDragLeave={e => {
                    if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(null);
                  }}
                  onDrop={e => {
                    e.preventDefault();
                    const word = e.dataTransfer.getData("text/plain");
                    if (word) dropWordOnCategory(cat.id, word);
                    setDragOver(null);
                  }}
                >
                  {/* Node header */}
                  <div className="scmap-cat-header" style={{ background: cat.color }}>
                    <span className="cat-hanzi">{cat.hanzi}</span>
                    <span className="cat-english">{cat.english}</span>
                  </div>

                  {/* Dropped words */}
                  <div className="scmap-cat-words">
                    {words.length === 0 ? (
                      <div className="scmap-cat-empty">
                        {isOver ? "Release to place" : "Drop words here"}
                      </div>
                    ) : (
                      words.map(w => (
                        <div key={w} className="scmap-cat-word">
                          <span>{w}</span>
                          {!submitted && (
                            <button
                              className="cat-word-remove"
                              onClick={() => removeFromCategory(cat.id, w)}
                            >×</button>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })}

          </div>
        </div>
      </div>

      {/* ── Result modal ── */}
      {modal && (
        <div className="scmap-modal-overlay" onClick={() => setModal(null)}>
          <div className="scmap-modal" onClick={e => e.stopPropagation()}>
            <div className="scmap-modal-emoji">{modal.emoji}</div>
            <h3 className="scmap-modal-title">{modal.title}</h3>
            <div className="scmap-modal-score">{modal.placed} / {modal.total}</div>
            <p className="scmap-modal-msg">{modal.msg}</p>
            <button className="scmap-tbtn scmap-tbtn-primary" onClick={() => setModal(null)}>Close</button>
            {!submitted && (
              <>
                &nbsp;
                <button className="scmap-tbtn" onClick={() => { setModal(null); reset(); }}>Try Again</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
