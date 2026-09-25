import type { ConversationTurn } from "@entities/conversation";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import BilingualWord from "@shared/ui/student/BilingualWord";

interface ConversationHistoryTurnProps {
  turn: ConversationTurn;
}

export default function ConversationHistoryTurn({ turn }: ConversationHistoryTurnProps) {
  const isStudent = turn.speaker === "student";
  const audioUrl = turn.audioUrl || turn.targetAudioUrl;

  return (
    <article className={`sa-bubble-row sa-bubble-row--compact ${isStudent ? "is-student" : "is-character"}`}>
      <div className="sa-bubble-row__who">
        <span className="sa-bubble-row__dot" aria-hidden="true" />
        <span>{isStudent ? <><span lang="zh-Hant">你</span> · You</> : <><span lang="zh-Hant">對話角色</span> · Character</>}</span>
      </div>
      <div className="sa-bubble sa-bubble--history">
        <BilingualWord
          hanzi={turn.targetText || turn.text}
          pinyin={turn.pinyin}
          gloss={turn.translation}
          size="inline"
        />
        {audioUrl && (
          <StudentAudioControl
            audioUrl={audioUrl}
            label={isStudent ? "Replay response" : "Listen"}
            compact
            showDuration
          />
        )}
      </div>
    </article>
  );
}
