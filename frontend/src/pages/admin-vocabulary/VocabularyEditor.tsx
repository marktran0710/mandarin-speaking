import { useState, type FormEvent } from "react";
import Modal from "../../shared/ui/Modal";
import Icon from "../../shared/ui/Icon";
import type { VocabularyEntry } from "./model";
import { vocabularyBookSource } from "./book-sources";
import { updateVocabularyMetadata } from "../../services/api/vocabulary";
import type { StoredCustomStory } from "../../services/api/stories-submissions";

const POS = ["N", "V", "Vi", "Vt", "Vs", "Vst", "V-sep", "Vaux", "Adj", "Adv", "Prep", "Conj", "Pron", "M", "MW", "Ptc", "Particle", "Time", "TimeExpr", "Loc", "Phrase", "Other"];

export default function VocabularyEditor({ entry, onClose, onSaved }: {
  entry: VocabularyEntry; onClose: () => void; onSaved: (story: StoredCustomStory) => void;
}) {
  const [pinyin, setPinyin] = useState(entry.pinyin);
  const [translation, setTranslation] = useState(entry.translation);
  const [pos, setPos] = useState(entry.pos);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const source = vocabularyBookSource(entry);
  const dirty = pinyin !== entry.pinyin || translation !== entry.translation || pos !== entry.pos;
  const close = () => {
    if (!saving && (!dirty || window.confirm("Discard unsaved vocabulary changes?"))) onClose();
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!dirty || saving) return;
    if ([pinyin, translation, pos].some(value => !value.trim() || /[,\r\n]/.test(value))) {
      setError("Enter pinyin, meaning and part of speech without commas or line breaks.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const story = await updateVocabularyMetadata(entry.storyId, {
        frameIndex: entry.frameIndex, wordIndex: entry.wordIndex, word: entry.word, tier: entry.tier,
        storyWide: entry.storyWide,
        expected: entry.expected, pinyin: pinyin.trim(), translation: translation.trim(), pos: pos.trim(),
      });
      onSaved(story);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save vocabulary.");
      setSaving(false);
    }
  };
  return <Modal open title={`Edit vocabulary: ${entry.word}`} onClose={close}>
    <form className="av-editor" onSubmit={save} aria-busy={saving}>
      <dl className="av-context">
        <div><dt>Speaking</dt><dd>{entry.storyTitle}</dd></div>
        <div><dt>Scene / level</dt><dd>{entry.storyWide ? "Story-wide" : entry.frameIndex + 1} / {entry.tier}</dd></div>
        <div><dt>Book source</dt><dd>{source ? `${source.book}, p. ${source.page} (${source.kind})` : "Not verified"}</dd></div>
        <div><dt>Example</dt><dd lang="zh-Hant">{entry.context || "No example"}</dd></div>
      </dl>
      <fieldset disabled={saving}>
        <label>Pinyin<input value={pinyin} onChange={event => setPinyin(event.target.value)} required maxLength={300} /></label>
        <label>Meaning (English)<input value={translation} onChange={event => setTranslation(event.target.value)} required maxLength={500} /></label>
        <label>Part of speech<select value={pos} onChange={event => setPos(event.target.value)} required>
          <option value="">Select</option>
          {[...new Set([...POS, entry.pos].filter(Boolean))].map(value => <option key={value}>{value}</option>)}
        </select></label>
      </fieldset>
      <dl className="av-context av-save-scope">
        <div><dt>Update scope</dt><dd>{entry.storyWide ? "Story-wide vocabulary" : `Scene ${entry.frameIndex + 1}`}, {entry.tier}{entry.tier === "easy" ? " and inherited fields" : " only"}</dd></div>
        <div><dt>Quiz publication</dt><dd>Unchanged</dd></div>
      </dl>
      {error && <p className="av-error" role="alert">{error}</p>}
      <div className="av-editor-actions">
        <button type="button" className="av-button" disabled={saving} onClick={close}>Cancel</button>
        <button type="submit" className="av-button av-primary" disabled={!dirty || saving}><Icon name="check" size={18} />{saving ? "Saving..." : "Save changes"}</button>
      </div>
    </form>
  </Modal>;
}
