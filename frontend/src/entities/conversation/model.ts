import type { ConversationSpeaker, ConversationTurn } from "./types";

const OPTIONAL_TEXT_FIELDS = ["audioUrl", "targetText", "targetAudioUrl", "pinyin", "translation"] as const;

export function normalizeConversationTurns(value: unknown): ConversationTurn[] | null {
  if (!Array.isArray(value) || value.length === 0 || value.length % 2 !== 0) return null;

  const ids = new Set<string>();
  const turns: ConversationTurn[] = [];

  for (let index = 0; index < value.length; index += 1) {
    const candidate = value[index];
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return null;

    const record = candidate as Record<string, unknown>;
    const expectedSpeaker: ConversationSpeaker = index % 2 === 0 ? "system" : "student";
    if (
      typeof record.id !== "string" ||
      record.id.trim() === "" ||
      ids.has(record.id) ||
      record.speaker !== expectedSpeaker ||
      typeof record.text !== "string" ||
      record.text.trim() === ""
    ) return null;

    const turn: ConversationTurn = { id: record.id, speaker: expectedSpeaker, text: record.text };
    for (const field of OPTIONAL_TEXT_FIELDS) {
      const fieldValue = record[field];
      if (fieldValue !== undefined) {
        if (typeof fieldValue !== "string") return null;
        turn[field] = fieldValue;
      }
    }
    ids.add(record.id);
    turns.push(turn);
  }
  return turns;
}
