import { VocabGroup } from "../utils/teacherStories";

const GRAMMAR_CANVAS_CATEGORIES = [
  { name: "Subject", hanzi: "主語", sub: "Who is doing it (S)",        color: "var(--jade)" },
  { name: "Verb",     hanzi: "動詞", sub: "Aux + main verb (Vaux + V)", color: "var(--seal)" },
  { name: "Object",   hanzi: "受語", sub: "What the verb acts on (O)",  color: "var(--gold-deep)" },
];

const GRAMMAR_GROUP_NAMES = GRAMMAR_CANVAS_CATEGORIES.map(c => c.name);

export default function VocabGroupEditor({
  vocabulary,
  groups,
  onChange,
}: {
  vocabulary: string;
  groups: VocabGroup[] | null;
  onChange: (groups: VocabGroup[] | null) => void;
}) {
  const words = vocabulary.split(",").map((w) => w.trim()).filter(Boolean);

  if (words.length === 0) return null;

  const active = groups !== null;
  const categoryMeta = GRAMMAR_CANVAS_CATEGORIES;
  const editorTitle = "Grammar Pattern Canvas (Subject · Verb · Object)";

  const handleToggle = (groupNames: string[] | null) => {
    onChange(groupNames ? groupNames.map((name) => ({ name, words: [] })) : null);
  };

  if (!active) {
    return (
      <div className="vocab-group-toggle-row">
        <button type="button" className="vocab-group-toggle-btn" onClick={() => handleToggle(GRAMMAR_GROUP_NAMES)}>
          + Add Grammar categories (Subject · Verb · Object)
        </button>
      </div>
    );
  }

  const currentGroups = groups!;
  const assignedWords = currentGroups.flatMap((g) => g.words);
  const unassigned = words.filter((w) => !assignedWords.includes(w));

  const assignWord = (word: string, groupIndex: number) => {
    const next = currentGroups.map((g, i) => ({
      ...g,
      words: i === groupIndex ? [...g.words, word] : g.words.filter((w) => w !== word),
    }));
    onChange(next);
  };

  const removeWord = (word: string, groupIndex: number) => {
    const next = currentGroups.map((g, i) => ({
      ...g,
      words: i === groupIndex ? g.words.filter((w) => w !== word) : g.words,
    }));
    onChange(next);
  };

  return (
    <div className="vocab-group-editor">
      <div className="vocab-group-editor-header">
        <span>{editorTitle}</span>
        <button type="button" className="vocab-group-remove-btn" onClick={() => handleToggle(null)}>Remove categories</button>
      </div>

      {unassigned.length > 0 && (
        <div className="vocab-group-unassigned">
          <span className="vocab-group-label">Unassigned words — click a word then pick a group:</span>
          <div className="vocab-group-chips">
            {unassigned.map((word) => (
              <span key={word} className="vocab-group-chip unassigned">{word}</span>
            ))}
          </div>
        </div>
      )}

      <div className="vocab-group-grid">
        {currentGroups.map((group, gi) => {
          const cat = categoryMeta[gi];
          return (
          <div key={gi} className="vocab-group-slot">
            <div className="vocab-group-slot-header" style={{ background: cat?.color ?? "var(--clay-muted)" }}>
              <span className="vgs-hanzi">{cat?.hanzi}</span>
              <div className="vgs-title-block">
                <span className="vgs-name">{group.name}</span>
                <span className="vgs-sub">{cat?.sub}</span>
              </div>
            </div>
            <div className="vocab-group-slot-words">
              {group.words.map((word) => (
                <span
                  key={word}
                  className="vocab-group-chip assigned"
                  onClick={() => removeWord(word, gi)}
                  title="Click to remove"
                >
                  {word} ×
                </span>
              ))}
              {unassigned.map((word) => (
                <button
                  key={word}
                  type="button"
                  className="vocab-group-add-word-btn"
                  onClick={() => assignWord(word, gi)}
                >
                  + {word}
                </button>
              ))}
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}
