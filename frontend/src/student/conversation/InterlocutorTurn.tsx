import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import StudentAudioControl from "../primitives/StudentAudioControl";
import StudentButton from "../primitives/StudentButton";
import BilingualWord from "../primitives/BilingualWord";

interface InterlocutorTurnProps {
  turn: ConversationTurn;
  onContinue: () => void;
}
export default function InterlocutorTurn({ turn, onContinue }: InterlocutorTurnProps) {
  return (
    <section className="sa-bubble-row is-character sa-conversation__current-turn" aria-label="Conversation partner turn">
      <span className="sa-bubble-row__who">Conversation partner</span>
      <div className="sa-bubble">
        <BilingualWord hanzi={turn.text} pinyin={turn.pinyin} gloss={turn.translation} size="inline" />
        <div className="sa-conversation__turn-actions">
          <StudentAudioControl audioUrl={turn.audioUrl} label="Listen" showDuration />
          <StudentButton variant="subtle" size="sm" onClick={onContinue}>Continue</StudentButton>
        </div>
      </div>
    </section>
  );
}
