import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import type { ConversationSession } from "./useConversationSession";
import StudentButton from "../primitives/StudentButton";
import BilingualWord from "../primitives/BilingualWord";

interface StudentTurnProps {
  turn: ConversationTurn;
  session: ConversationSession;
}

export default function StudentTurn({ turn, session }: StudentTurnProps) {
  const { recorder } = session;
  return (
    <section className="sa-bubble-row is-student is-current" aria-label="Your response">
      <span className="sa-bubble-row__who">Your response</span>
      <div className="sa-bubble sa-bubble--target">
        <BilingualWord
          hanzi={turn.targetText || turn.text}
          pinyin={turn.pinyin}
          gloss={turn.translation}
          size="inline"
        />
        {recorder.error && <p className="sa-conversation__error" role="alert">{recorder.error}</p>}
        <StudentButton
          variant={recorder.isRecording ? "danger" : "primary"}
          icon={recorder.isRecording ? "stop" : "mic"}
          disabled={recorder.isAnalyzing}
          onClick={recorder.isRecording ? recorder.stopRecording : session.handleRecord}
        >
          {recorder.isRecording ? `Stop (${recorder.recordingDuration}s)` : recorder.isAnalyzing ? "Analyzing…" : "Record"}
        </StudentButton>
      </div>
    </section>
  );
}

