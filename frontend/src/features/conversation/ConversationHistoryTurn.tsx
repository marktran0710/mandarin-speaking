import type { ConversationTurn } from "@entities/conversation";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import BilingualWord from "@shared/ui/student/BilingualWord";
import ConversationRoleHeader from "./ConversationRoleHeader";

interface ConversationHistoryTurnProps {
  turn: ConversationTurn;
  showRoleHeader: boolean;
  studentAudioUrl?: string;
}

export default function ConversationHistoryTurn({ turn, showRoleHeader, studentAudioUrl }: ConversationHistoryTurnProps) {
  const isStudent = turn.speaker === "student";
  const audioUrl = isStudent ? studentAudioUrl?.trim() : turn.audioUrl || turn.targetAudioUrl;

  return (
    <article className={`sa-bubble-row sa-bubble-row--compact ${!showRoleHeader ? "is-grouped" : ""} ${isStudent ? "is-student" : "is-character"}`}>
      {showRoleHeader && <ConversationRoleHeader role={isStudent ? "student" : "character"} history />}
      <div className="sa-bubble sa-bubble--history">
        <BilingualWord
          hanzi={turn.targetText || turn.text}
          gloss={turn.translation}
          size="inline"
        />
        {audioUrl && (
          <StudentAudioControl
            audioUrl={audioUrl}
            labelKey={isStudent ? "replayAnswer" : "listen"}
            compact
            showDuration
          />
        )}
      </div>
    </article>
  );
}
