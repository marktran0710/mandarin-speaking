import type { NewAudioRecord, ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "@entities/topic";
import type { SceneSubmission } from "../../services/database";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import ConversationHistoryTurn from "./ConversationHistoryTurn";
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
  const progress = exchange.total > 0 ? Math.min(100, (exchange.current / exchange.total) * 100) : 0;

  const header = (
    <StudentPageHeader
      eyebrowZh="對話練習"
      eyebrowEn="Conversation Practice"
      titleZh={topic.name}
      titleEn={topic.description || "Practice the dialogue"}
      onBack={onBack}
      aside={
        <div
          className="sa-conversation__progress"
          aria-label={`Exchange ${exchange.current} of ${exchange.total}`}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={exchange.total}
          aria-valuenow={exchange.current}
        >
          <span className="sa-conversation__progress-copy">
            <span lang="zh-Hant">第{exchange.current}輪</span> · Exchange <strong>{exchange.current}</strong> / {exchange.total}
          </span>
          <span className="sa-conversation__progress-track" aria-hidden="true">
            <span style={{ width: `${progress}%` }} />
          </span>
        </div>
      }
    />
  );

  return (
    <StudentPage layout="stage" header={header}>
      <section className="sa-conversation__surface" aria-label="Conversation practice">
        <div className="sa-conversation__workspace">
          <div className="sa-conversation__column">
            {historyTurns.map((turn) => <ConversationHistoryTurn key={turn.id} turn={turn} />)}

            {currentTurn && state.step === "system" && (
              <InterlocutorTurn turn={currentTurn} onContinue={session.handleListen} />
            )}

            {currentTurn && state.step === "student" && (
              <StudentTurn turn={currentTurn} session={session} />
            )}

            {currentTurn && state.step === "feedback" && (
              <div className="sa-bubble-row is-student is-current">
                <span className="sa-bubble-row__who"><span lang="zh-Hant">你的回答</span> · Your response</span>
                <TurnFeedback
                  session={session}
                  continueLabel={state.turnIndex + 1 < turns.length ? "Next turn" : "Finish"}
                />
              </div>
            )}
          </div>
        </div>
      </section>
    </StudentPage>
  );
}
