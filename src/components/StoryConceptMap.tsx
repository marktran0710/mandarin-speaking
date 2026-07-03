import { useState, useCallback, useMemo } from "react";
import { toPinyin } from "../utils/pinyin";
import { BiLabel } from "./BiLabel";
import "./BiLabel.css";
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

// Grammar pattern canvas — Subject + (Aux) Verb + Object, e.g. S + Vaux + V(O)
const GRAMMAR_CATEGORIES = [
  { id: "subject", hanzi: "主語", english: "Subject", sub: "Who is doing it (S)",        color: "var(--seal)", border: "var(--seal)" },
  { id: "verb",     hanzi: "動詞", english: "Verb",    sub: "Aux + main verb (Vaux + V)", color: "var(--gold)", border: "var(--gold)" },
  { id: "object",   hanzi: "受語", english: "Object",  sub: "What the verb acts on (O)",  color: "var(--jade)", border: "var(--jade)" },
];

function groupNameToGrammarCategoryId(name: string): string | null {
  const n = name.toLowerCase();
  if (n.includes("subject") || n.includes("主語") || n.includes("主词") || n === "s") return "subject";
  if (n.includes("verb") || n.includes("動詞") || n.includes("助動詞") || n === "v" || n === "vaux") return "verb";
  if (n.includes("object") || n.includes("受語") || n.includes("受词") || n === "o") return "object";
  return null;
}

/** Every topic uses the grammar (Subject · Verb · Object) canvas. */
function pickCategorySet(_vocabularyGroups: Record<number, VocabGroup[]> | undefined) {
  return { categories: GRAMMAR_CATEGORIES, groupNameToCategoryId: groupNameToGrammarCategoryId };
}

// Layout: up to 3 columns, as many rows as needed for the active category set
const CANVAS_W   = 860;
const CENTRAL_W  = 180;
const CENTRAL_H  = 56;
const CENTRAL_X  = CANVAS_W / 2 - CENTRAL_W / 2;
const CENTRAL_Y  = 16;
const CAT_W      = 256;
const CAT_GAP    = 16;

function shuffleArr<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function StoryConceptMap({ topic, defaultOpen = false }: Props) {
  const { categories: CATEGORIES, groupNameToCategoryId } = useMemo(
    () => pickCategorySet(topic.vocabularyGroups),
    [topic.id, topic.vocabularyGroups],
  );
  const COLS = Math.min(3, CATEGORIES.length);
  const TOTAL_W = COLS * CAT_W + (COLS - 1) * CAT_GAP;
  const ROW_START_X = (CANVAS_W - TOTAL_W) / 2;
  const ROW_1_Y = CENTRAL_Y + CENTRAL_H + 56;
  const catCol     = (i: number) => i % COLS;
  const catRow     = (i: number) => Math.floor(i / COLS);
  const catLeft    = (i: number) => ROW_START_X + catCol(i) * (CAT_W + CAT_GAP);
  const catCenterX = (i: number) => catLeft(i) + CAT_W / 2;
  const rowCount   = Math.ceil(CATEGORIES.length / COLS);

  const [placed, setPlaced] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(CATEGORIES.map(c => [c.id, []]))
  );
  const [dragOver, setDragOver]   = useState<string | null>(null);
  const [draggingWord, setDraggingWord] = useState<string | null>(null);
  const [selectedWord, setSelectedWord] = useState<string | null>(null);
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
  }, [topic.id, topic.vocabularyGroups, groupNameToCategoryId]);

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
  }, [topic.id, CATEGORIES]);

  const usedWords   = new Set(Object.values(placed).flat());
  const totalPlaced = usedWords.size;
  const totalWords  = allWords.length;

  function dropWordOnCategory(catId: string, word: string) {
    setChecked(false);
    setSelectedWord(null);
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

  const maxWordsInRow = (row: number) =>
    Math.max(1, ...CATEGORIES.filter((_, i) => catRow(i) === row).map(c => placed[c.id].length));
  const ROW_H = (row: number) => 54 + maxWordsInRow(row) * 40;
  const catTop = (i: number) => {
    let top = ROW_1_Y;
    for (let r = 0; r < catRow(i); r++) top += ROW_H(r) + 32;
    return top;
  };
  const CANVAS_H = catTop(COLS * (rowCount - 1)) + ROW_H(rowCount - 1) + 40;

  if (!isOpen) {
    return (
      <button type="button" className="scmap-collapsed" onClick={() => setIsOpen(true)}>
        <span className="scmap-collapsed-icon">🗺️</span>
        <div className="scmap-collapsed-text">
          <strong><BiLabel zh="故事概念圖" en="Story Concept Map" /></strong>
          <span>
            <BiLabel
              zh={`整理故事詞彙 · 已放置 ${totalPlaced}/${totalWords}`}
              en={`Organize story vocabulary · ${totalPlaced}/${totalWords} placed`}
            />
          </span>
        </div>
        <span className="scmap-collapsed-caret">
          <BiLabel zh="▼ 展開" en="▼ Open" />
        </span>
      </button>
    );
  }

  return (
    <div className="scmap-root">

      <div className="scmap-toolbar">
        <div className="scmap-toolbar-left">
          <div className="scmap-score-badge">
            <BiLabel zh="已放置詞彙：" en="Words placed: " />
            <span>{totalPlaced}</span> / {totalWords}
          </div>
          <button className="scmap-tbtn" onClick={reset} disabled={submitted}>
            <BiLabel zh="↺ 重設" en="↺ Reset" />
          </button>
          <button
            className="scmap-tbtn scmap-tbtn-success"
            onClick={() => setChecked(true)}
            disabled={submitted || totalPlaced === 0}
          >
            <BiLabel zh="✓ 檢查" en="✓ Check" />
          </button>
          <button
            className={`scmap-tbtn scmap-tbtn-primary${submitted ? " is-submitted" : ""}`}
            onClick={() => { setSubmitted(true); setChecked(true); }}
            disabled={submitted}
          >
            {submitted ? <BiLabel zh="✓ 已提交" en="✓ Submitted" /> : <BiLabel zh="提交" en="Submit" />}
          </button>
        </div>
        <button className="scmap-tbtn" onClick={() => setIsOpen(false)}>
          <BiLabel zh="▲ 隱藏" en="▲ Hide" />
        </button>
      </div>

      {checked && hasAnswerKey && (
        <div className={`scmap-check-banner${allCorrect ? " scmap-check-banner-perfect" : ""}`}>
          {allCorrect ? (
            <BiLabel zh="🎉 所有詞彙都分類正確！太棒了！繼續進行口說練習。" en="🎉 All words in the right category! Now continue to speaking." />
          ) : (
            <BiLabel
              zh={`✓ ${checkedCorrect} 個正確 · ✗ ${checkedWrong} 個錯誤 — 標示 ✗ 的詞彙會顯示正確分類，移除後再試一次。`}
              en={`✓ ${checkedCorrect} correct · ✗ ${checkedWrong} wrong — words marked ✗ show the correct category. Remove them and try again.`}
            />
          )}
        </div>
      )}
      {checked && !hasAnswerKey && (
        <div className="scmap-check-banner">
          {totalPlaced === totalWords ? (
            <BiLabel zh="🎉 所有詞彙都已放置！請老師檢查你的概念圖。" en="🎉 All words placed! Ask your teacher to review your concept map." />
          ) : (
            <BiLabel
              zh={`已放置 ${totalPlaced}/${totalWords} 個詞彙，繼續加油！`}
              en={`${totalPlaced}/${totalWords} words placed. Keep going!`}
            />
          )}
        </div>
      )}

      <div className="scmap-main">

        <div className="scmap-word-bank">
          <h3><BiLabel zh="📚 詞彙庫" en="📚 Word Bank" /></h3>
          {allWords.length > 0 && (
            <div className="scmap-scene-legend">
              {Array.from(new Set(Object.keys(topic.vocabulary).map(Number))).sort((a, b) => a - b).map(si => (
                <span key={si} className={`chip-scene chip-scene-${si % 6}`}>S{si + 1}</span>
              ))}
              <span className="scmap-legend-hint">
                <BiLabel zh="= 場景" en="= scene" />
              </span>
            </div>
          )}
          {allWords.length === 0 ? (
            <div className="scmap-bank-empty">
              <span className="scmap-bank-empty-icon">📝</span>
              <p><BiLabel zh="尚無詞彙。" en="No vocabulary yet." /></p>
              <p><BiLabel zh="請老師為這個故事新增詞彙。" en="Ask your teacher to add words to this story." /></p>
            </div>
          ) : allWords.map((w, i) => {
            const used = usedWords.has(w);
            const isSelected = selectedWord === w;
            return (
              <button
                type="button"
                key={`${w}-${i}`}
                className={`scmap-word-chip${used ? " used" : ""}${submitted ? " used" : ""}${draggingWord === w ? " dragging" : ""}${isSelected ? " selected" : ""}`}
                draggable={!used && !submitted}
                disabled={used || submitted}
                aria-pressed={isSelected}
                title={
                  isSelected
                    ? "已選取 — 點擊一個分類來放置 Selected — click a category to place it"
                    : "點擊選取，或拖曳到分類 Click to select, or drag to a category"
                }
                onDragStart={e => {
                  if (!used && !submitted) {
                    e.dataTransfer.setData("text/plain", w);
                    e.dataTransfer.effectAllowed = "move";
                    setDraggingWord(w);
                  }
                }}
                onDragEnd={() => setDraggingWord(null)}
                onClick={() => setSelectedWord(prev => (prev === w ? null : w))}
              >
                <span className="chip-hanzi">
                  {w}
                  {toPinyin(w) && <span className="chip-pinyin">{toPinyin(w)}</span>}
                </span>
                <span className={`chip-scene chip-scene-${(wordScene[w] ?? 0) % 6}`}>
                  S{(wordScene[w] ?? 0) + 1}
                </span>
                {used && <span className="chip-check">✓</span>}
              </button>
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
                  x2={catCenterX(i)}             y2={catTop(i)}
                  stroke="var(--clay-muted-soft)" strokeWidth="2" strokeLinecap="round" strokeDasharray="6 4"
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
                  className={`scmap-cat-node${isOver ? " drag-over" : ""}${submitted ? " is-submitted" : ""}${selectedWord ? " selectable" : ""}`}
                  style={{ left: catLeft(i), top: catTop(i), width: CAT_W, borderColor: cat.border }}
                  role="button"
                  tabIndex={0}
                  aria-label={
                    selectedWord
                      ? `Place "${selectedWord}" in ${cat.english} category`
                      : `${cat.english} category, ${words.length} word${words.length === 1 ? "" : "s"} placed`
                  }
                  onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setDragOver(cat.id); }}
                  onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(null); }}
                  onDrop={e => {
                    e.preventDefault();
                    const word = e.dataTransfer.getData("text/plain");
                    if (word) dropWordOnCategory(cat.id, word);
                    setDragOver(null);
                  }}
                  onClick={() => { if (selectedWord && !submitted) dropWordOnCategory(cat.id, selectedWord); }}
                  onKeyDown={e => {
                    if ((e.key === "Enter" || e.key === " ") && selectedWord && !submitted) {
                      e.preventDefault();
                      dropWordOnCategory(cat.id, selectedWord);
                    }
                  }}
                >
                  <div className="scmap-cat-header" style={{ background: cat.color }}>
                    <div className="cat-header-top">
                      <span className="cat-hanzi">{cat.hanzi}</span>
                      <span className="cat-english">{cat.english}</span>
                    </div>
                    <span className="cat-sub">{cat.sub}</span>
                  </div>

                  <div className="scmap-cat-words">
                    {words.length === 0 ? (
                      <div className="scmap-cat-empty">
                        {isOver ? (
                          <BiLabel zh="放開以放置" en="Release to place" />
                        ) : selectedWord ? (
                          <BiLabel zh="點擊以放置選取的詞彙" en="Click to place the selected word" />
                        ) : (
                          <BiLabel zh="拖曳或選取詞彙後點擊這裡" en="Drag here, or select a word and click here" />
                        )}
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
                            <span className="cat-word-hint">→ {correctCat.hanzi} {correctCat.english}</span>
                          )}
                          {!submitted && (
                            <button
                              className={`cat-word-remove${result === "wrong" ? " cat-word-remove-wrong" : ""}`}
                              onClick={e => { e.stopPropagation(); removeFromCategory(cat.id, w, result === "wrong"); }}
                              title={result === "wrong" ? "錯誤 — 點擊移回 Wrong — click to move back" : "移除 Remove"}
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
