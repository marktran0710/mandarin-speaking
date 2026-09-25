import type { ConversationSpeaker, ConversationTurn } from "./types";

const OPTIONAL_TEXT_FIELDS = ["audioUrl", "targetText", "targetAudioUrl", "pinyin", "translation"] as const;

export interface ConversationSceneSource {
  targetText?: string;
  prompt?: string;
  audioUrl?: string;
}

/**
 * Build the conversation view from the same scene targets used by Story
 * Speaking. Scene zero is always the system turn; speakers then alternate for
 * every following scene. A final system turn is valid and simply ends the
 * session after the learner listens to it.
 */
export function buildConversationTurnsFromScenes(
  scenes: readonly ConversationSceneSource[],
): ConversationTurn[] | null {
  const usableScenes = scenes
    .map((scene, sourceIndex) => ({
      sourceIndex,
      text: (scene.targetText || scene.prompt || "").trim(),
      audioUrl: scene.audioUrl,
    }))
    .filter((scene) => scene.text.length > 0);

  if (usableScenes.length < 2) return null;

  return usableScenes.map((scene, index) => {
    const speaker: ConversationSpeaker = index % 2 === 0 ? "system" : "student";
    return {
      id: `${speaker}-scene-${scene.sourceIndex}`,
      speaker,
      text: scene.text,
      sceneIndex: scene.sourceIndex,
      ...(speaker === "student" ? { targetText: scene.text } : {}),
      ...(scene.audioUrl
        ? speaker === "system"
          ? { audioUrl: scene.audioUrl }
          : { targetAudioUrl: scene.audioUrl }
        : {}),
    };
  });
}

export function normalizeConversationTurns(value: unknown): ConversationTurn[] | null {
  if (!Array.isArray(value) || value.length < 2) return null;

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

    if (record.sceneIndex !== undefined && (typeof record.sceneIndex !== "number" || !Number.isInteger(record.sceneIndex) || record.sceneIndex < 0)) {
      return null;
    }

    const turn: ConversationTurn = {
      id: record.id,
      speaker: expectedSpeaker,
      text: record.text,
      ...(record.sceneIndex !== undefined ? { sceneIndex: record.sceneIndex } : {}),
    };
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
