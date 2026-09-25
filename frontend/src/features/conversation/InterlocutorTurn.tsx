import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentButton from "@shared/ui/student/StudentButton";
import BilingualWord from "@shared/ui/student/BilingualWord";

interface InterlocutorTurnProps {
  turn: ConversationTurn;
  onContinue: () => void;
}
export default function InterlocutorTurn({ turn, onContinue }: InterlocutorTurnProps) {
  return (
    <section className="sa-bubble-row is-character sa-conversation__current-turn" aria-label="Conversation partner turn">
      <div className="sa-bubble-row__who">
        <span className="sa-bubble-row__dot" aria-hidden="true" />
        <span>Conversation partner</span>
      </div>
      <div className="sa-bubble">
        <BilingualWord hanzi={turn.text} pinyin={turn.pinyin} gloss={turn.translation} size="display" />
        <div className="sa-conversation__turn-actions">
          <StudentAudioControl audioUrl={turn.audioUrl} label="Listen" showDuration />
          <StudentButton variant="subtle" onClick={onContinue}>Continue</StudentButton>
        </div>
      </div>
    </section>
  );
}
