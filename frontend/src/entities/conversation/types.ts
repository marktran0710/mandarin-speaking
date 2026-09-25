export type ConversationSpeaker = "system" | "student";

export interface ConversationTurn {
  id: string;
  speaker: ConversationSpeaker;
  text: string;
  pinyin?: string;
  translation?: string;
  audioUrl?: string;
  targetText?: string;
  targetAudioUrl?: string;
}
