import type { NewAudioRecord, ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "../../components/content/topic-selector/types";
import type { SceneSubmission } from "../../services/database";
import ConversationHeader from "./ConversationHeader";
import InterlocutorTurn from "./InterlocutorTurn";
import StudentTurn from "./StudentTurn";
import TurnFeedback from "./TurnFeedback";
import { useConversationSession } from "./useConversationSession";
import "./ConversationPage.css";

interface ConversationPageProps {
  topic: Topic;
  turns: ConversationTurn[];
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  onSceneSubmission: (key: string, submission: SceneSubmission) => void;
  onDone: () => void;
  onBack: () => void;
}
export default function ConversationPage({ topic, turns, onAddRecord, onSceneSubmission, onDone, onBack }: ConversationPageProps) {
  const session = useConversationSession({ topic, turns, onAddRecord, onSceneSubmission, onDone });
  const { state, currentTurn, historyTurns, exchange } = session;

  return (
    <div className="sa-conversation">
      <ConversationHeader
        title={topic.name}
        currentExchange={exchange.current}
        totalExchanges={exchange.total}
        onBack={onBack}
      />

      <div className="sa-conversation__column">
        {historyTurns.map((turn) => (
          <div key={turn.id} className={`sa-bubble-row sa-bubble-row--compact ${turn.speaker === "student" ? "is-student" : "is-character"}`}>
            <span className="sa-bubble-row__who">{turn.speaker === "student" ? "You" : "Conversation partner"}</span>
            <div className="sa-bubble">
              <span lang="zh-Hant" className="sa-bubble__hanzi">{turn.targetText || turn.text}</span>
            </div>
          </div>
        ))}

        {currentTurn && state.step === "system" && (
          <InterlocutorTurn turn={currentTurn} onContinue={session.handleListen} />
        )}

        {currentTurn && state.step === "student" && (
          <StudentTurn turn={currentTurn} session={session} />
        )}

        {currentTurn && state.step === "feedback" && (
          <div className="sa-bubble-row is-student is-current">
            <span className="sa-bubble-row__who">Your response</span>
            <TurnFeedback
              session={session}
              continueLabel={state.turnIndex + 1 < turns.length ? "Next turn" : "Finish"}
            />
          </div>
        )}
      </div>
    </div>
  );
}
