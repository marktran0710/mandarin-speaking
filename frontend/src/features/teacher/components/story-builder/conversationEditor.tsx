// @ts-nocheck
import { getAudioUploadError } from "../../../../utils/myStoriesUtils";
import { blankConversationExchange } from "./modelHelpers";

function readAudioAsDataUrl(file, onLoaded) {
  const reader = new FileReader();
  reader.onload = () => {
    if (typeof reader.result === "string") onLoaded(reader.result);
  };
  reader.readAsDataURL(file);
}

/** Dual Speaking Modes plan, Epic 3: lets a teacher author Conversation
 * Practice as exchange pairs (Character -> Student) without touching the
 * low-level system/student turn split - StoryBuilderSection.model.tsx's
 * exchangesToConversationTurns() does that conversion on save. */
export default function StoryBuilderConversationEditor({ draft, onSetDraft, setValidationErrors }) {
  const exchanges = draft.conversationExchanges;
  const enabled = draft.conversationEnabled;

  const updateExchange = (index, field, value) => {
    onSetDraft((current) => ({
      ...current,
      conversationExchanges: current.conversationExchanges.map((exchange, exchangeIndex) =>
        exchangeIndex === index ? { ...exchange, [field]: value } : exchange,
      ),
    }));
  };

  const addExchange = () => {
    onSetDraft((current) => ({
      ...current,
      conversationExchanges: [
        ...current.conversationExchanges,
        blankConversationExchange(`exchange-${Date.now()}-${current.conversationExchanges.length}`),
      ],
    }));
  };

  const removeExchange = (index) => {
    onSetDraft((current) => ({
      ...current,
      conversationExchanges: current.conversationExchanges.filter((_, exchangeIndex) => exchangeIndex !== index),
    }));
  };

  const moveExchange = (index, direction) => {
    onSetDraft((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.conversationExchanges.length) return current;
      const next = [...current.conversationExchanges];
      [next[index], next[target]] = [next[target], next[index]];
      return { ...current, conversationExchanges: next };
    });
  };

  const toggleEnabled = () => {
    onSetDraft((current) => {
      const next = !current.conversationEnabled;
      return {
        ...current,
        conversationEnabled: next,
        conversationExchanges:
          next && current.conversationExchanges.length === 0
            ? [blankConversationExchange(`exchange-${Date.now()}`)]
            : current.conversationExchanges,
      };
    });
  };

  const handleAudioUpload = (index, field, file) => {
    if (!file) return;
    const error = getAudioUploadError(file);
    if (error) {
      setValidationErrors((errors) => ({ ...errors, form: error }));
      return;
    }
    readAudioAsDataUrl(file, (dataUrl) => updateExchange(index, field, dataUrl));
  };

  return (
    <section className="teacher-conversation-editor" aria-labelledby="teacher-conversation-title">
      <div className="teacher-conversation-heading">
        <div>
          <h3 id="teacher-conversation-title">Speaking activities</h3>
          <p>Story Practice is always available to students. Conversation Practice is optional.</p>
        </div>
      </div>
      <label className="teacher-checkbox-field">
        <input type="checkbox" checked={enabled} onChange={toggleEnabled} />
        Enable Conversation Practice
      </label>
      {enabled && (
        <div className="teacher-conversation-exchanges">
          {exchanges.map((exchange, index) => (
            <div className="teacher-conversation-exchange" key={exchange.id}>
              <div className="teacher-conversation-exchange-header">
                <strong>Exchange {index + 1}</strong>
                <div className="teacher-conversation-exchange-actions">
                  <button
                    type="button"
                    onClick={() => moveExchange(index, -1)}
                    disabled={index === 0}
                    aria-label={`Move exchange ${index + 1} up`}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => moveExchange(index, 1)}
                    disabled={index === exchanges.length - 1}
                    aria-label={`Move exchange ${index + 1} down`}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="teacher-conversation-exchange-delete"
                    onClick={() => removeExchange(index)}
                    aria-label={`Delete exchange ${index + 1}`}
                  >
                    Delete
                  </button>
                </div>
              </div>
              <fieldset className="teacher-conversation-side">
                <legend>Character</legend>
                <label>
                  Script
                  <textarea
                    value={exchange.characterText}
                    onChange={(event) => updateExchange(index, "characterText", event.target.value)}
                    rows={2}
                  />
                </label>
                <label>
                  Pinyin
                  <input
                    value={exchange.characterPinyin}
                    onChange={(event) => updateExchange(index, "characterPinyin", event.target.value)}
                  />
                </label>
                <label>
                  Translation
                  <input
                    value={exchange.characterTranslation}
                    onChange={(event) => updateExchange(index, "characterTranslation", event.target.value)}
                  />
                </label>
                <label>
                  Voice
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={(event) => handleAudioUpload(index, "characterAudioUrl", event.target.files?.[0])}
                  />
                </label>
                {exchange.characterAudioUrl && (
                  <audio controls src={exchange.characterAudioUrl} aria-label={`Exchange ${index + 1} character audio`} />
                )}
              </fieldset>
              <fieldset className="teacher-conversation-side">
                <legend>Student's response</legend>
                <label>
                  Target script
                  <textarea
                    value={exchange.studentText}
                    onChange={(event) => updateExchange(index, "studentText", event.target.value)}
                    rows={2}
                  />
                </label>
                <label>
                  Pinyin
                  <input
                    value={exchange.studentPinyin}
                    onChange={(event) => updateExchange(index, "studentPinyin", event.target.value)}
                  />
                </label>
                <label>
                  Translation
                  <input
                    value={exchange.studentTranslation}
                    onChange={(event) => updateExchange(index, "studentTranslation", event.target.value)}
                  />
                </label>
                <label>
                  Optional model audio
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={(event) => handleAudioUpload(index, "studentModelAudioUrl", event.target.files?.[0])}
                  />
                </label>
                {exchange.studentModelAudioUrl && (
                  <audio controls src={exchange.studentModelAudioUrl} aria-label={`Exchange ${index + 1} student model audio`} />
                )}
              </fieldset>
            </div>
          ))}
          <button type="button" className="teacher-conversation-add" onClick={addExchange}>
            + Add exchange
          </button>
        </div>
      )}
    </section>
  );
}
