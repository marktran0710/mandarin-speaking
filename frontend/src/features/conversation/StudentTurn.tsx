import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import type { ConversationSession } from "./useConversationSession";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentAudioUpload from "@shared/ui/student/StudentAudioUpload";
import BilingualWord from "@shared/ui/student/BilingualWord";
import ConversationRoleHeader from "./ConversationRoleHeader";
import StudentSystemText from "@shared/ui/student/StudentSystemText";

interface StudentTurnProps {
  turn: ConversationTurn;
  session: ConversationSession;
}
export default function StudentTurn({ turn, session }: StudentTurnProps) {
  const { recorder } = session;
  return (
    <section className="sa-bubble-row is-student is-current" aria-label="你的回答">
      <ConversationRoleHeader role="student" />
      <div className="sa-bubble sa-bubble--target">
        <span className="sa-conversation__target-label"><StudentSystemText k="yourTurn" /></span>
        <BilingualWord
          hanzi={turn.targetText || turn.text}
          gloss={turn.translation}
          size="display"
        />
        {recorder.error && <p className="sa-conversation__error" role="alert">{recorder.error}</p>}
        <div className="sa-conversation__record-actions">
          <StudentButton
            variant={recorder.isRecording ? "danger" : "primary"}
            icon={recorder.isRecording ? "stop" : "mic"}
            disabled={recorder.isAnalyzing}
            onClick={recorder.isRecording ? recorder.stopRecording : session.handleRecord}
          >
            {recorder.isRecording ? <><StudentSystemText k="stop" withinControl />（{recorder.recordingDuration} 秒）</> : recorder.isAnalyzing ? <StudentSystemText k="analyzing" withinControl /> : <StudentSystemText k="record" withinControl />}
          </StudentButton>
          <StudentAudioUpload
            labelKey="upload"
            disabled={recorder.isRecording || recorder.isAnalyzing}
            onSelect={session.handleUpload}
          />
        </div>
      </div>
    </section>
  );
}
