import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentButton from "@shared/ui/student/StudentButton";
import BilingualWord from "@shared/ui/student/BilingualWord";
import ConversationRoleHeader from "./ConversationRoleHeader";
import StudentSystemText from "@shared/ui/student/StudentSystemText";

interface InterlocutorTurnProps {
  turn: ConversationTurn;
  partnerGender: "male" | "female";
  onContinue: () => void;
}
export default function InterlocutorTurn({ turn, partnerGender, onContinue }: InterlocutorTurnProps) {
  return (
    <section className="sa-bubble-row is-character sa-conversation__current-turn" aria-label="對話夥伴回合">
      <ConversationRoleHeader role="character" partnerGender={partnerGender} />
      <div className="sa-bubble">
        <BilingualWord hanzi={turn.text} gloss={turn.translation} size="display" />
        <div className="sa-conversation__turn-actions">
          <StudentAudioControl audioUrl={turn.audioUrl} labelKey="listen" showDuration />
          <StudentButton variant="subtle" onClick={onContinue}><StudentSystemText k="continue" withinControl /></StudentButton>
        </div>
      </div>
    </section>
  );
}
