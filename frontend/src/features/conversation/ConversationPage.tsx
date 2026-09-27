import type { NewAudioRecord, ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "@entities/topic";
import type { SceneSubmission } from "../../services/database";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentButton from "@shared/ui/student/StudentButton";
import ConversationHistoryTurn from "./ConversationHistoryTurn";
import ConversationRoleHeader from "./ConversationRoleHeader";
import InterlocutorTurn from "./InterlocutorTurn";
import StudentTurn from "./StudentTurn";
import TurnFeedback from "./TurnFeedback";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import { useConversationSession } from "./useConversationSession";
import { SpeechSelfEvaluation } from "@entities/speech";
import "./ConversationPage.css";

interface ConversationPageProps {
  topic: Topic;
  turns: ConversationTurn[];
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  onSceneSubmission: (key: string, submission: SceneSubmission) => void;
  onDone: () => void;
  onBack: () => void;
}

export function groupConversationTurns(turns: ConversationTurn[]) {
  return turns.reduce<ConversationTurn[][]>((groups, turn) => {
    const currentGroup = groups[groups.length - 1];
    if (currentGroup && currentGroup[0].speaker === turn.speaker) {
      currentGroup.push(turn);
    } else {
      groups.push([turn]);
    }
    return groups;
  }, []);
}

export default function ConversationPage({ topic, turns, onAddRecord, onSceneSubmission, onDone, onBack }: ConversationPageProps) {
  if (turns.length === 0) {
    return <ConversationEmptyPage topic={topic} onBack={onBack} />;
  }

  return (
    <ConversationSessionPage
      topic={topic}
      turns={turns}
      onAddRecord={onAddRecord}
      onSceneSubmission={onSceneSubmission}
      onDone={onDone}
      onBack={onBack}
    />
  );
}

function ConversationEmptyPage({ topic, onBack }: Pick<ConversationPageProps, "topic" | "onBack">) {
  const header = (
    <StudentPageHeader
      eyebrowKey="conversation"
      titleKey="conversationPractice"
      context={<span lang="zh-Hant">{topic.name}</span>}
      subtitle={topic.description}
      onBack={onBack}
    />
  );

  return (
    <StudentPage
      layout="task"
      header={header}
      state="empty"
      emptyTitle={<StudentSystemText k="conversationNotReady" />}
      emptyText={<StudentSystemText k="conversationBackHint" />}
      emptyAction={<StudentButton variant="secondary" onClick={onBack}><StudentSystemText k="backToStudy" withinControl /></StudentButton>}
    />
  );
}

function ConversationSessionPage({ topic, turns, onAddRecord, onSceneSubmission, onDone, onBack }: ConversationPageProps) {
  const session = useConversationSession({ topic, turns, onAddRecord, onSceneSubmission, onDone });
  const { state, currentTurn, historyTurns, exchange } = session;
  const historyGroups = groupConversationTurns(historyTurns);
  const progress = exchange.total > 0 ? Math.min(100, (exchange.current / exchange.total) * 100) : 0;

  const header = (
    <StudentPageHeader
      eyebrowKey="conversation"
      titleKey="conversationPractice"
      context={<span lang="zh-Hant">{topic.name}</span>}
      subtitle={topic.description}
      onBack={onBack}
      aside={
        <div
          className="sa-conversation__progress"
          aria-label={`第 ${exchange.current} / ${exchange.total} 輪`}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={exchange.total}
          aria-valuenow={exchange.current}
        >
          <span className="sa-conversation__progress-copy">
            第 {exchange.current} / {exchange.total} 輪
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
      <section className="sa-conversation__surface" aria-label="對話練習">
        <div className="sa-conversation__workspace">
          <div className="sa-conversation__column">
            {historyGroups.map((group) => (
              <div className="sa-conversation__history-group" key={group[0].id}>
                {group.map((turn, index) => (
                  <ConversationHistoryTurn
                    key={turn.id}
                    turn={turn}
                    showRoleHeader={index === group.length - 1}
                  />
                ))}
              </div>
            ))}

            {currentTurn && state.step === "system" && (
              <InterlocutorTurn turn={currentTurn} onContinue={session.handleListen} />
            )}

            {currentTurn && state.step === "student" && (
              <StudentTurn turn={currentTurn} session={session} />
            )}

            {currentTurn && state.step === "selfEval" && session.lastResult && (
              <div className="sa-bubble-row is-student is-current">
                <ConversationRoleHeader role="student" />
                <SpeechSelfEvaluation
                  targetText={currentTurn.targetText || currentTurn.text}
                  translation={currentTurn.translation}
                  modelAudioUrl={currentTurn.targetAudioUrl || currentTurn.audioUrl}
                  audioBlob={session.lastResult.audioBlob}
                  meaning={session.selfEvalMeaning}
                  pronunciation={session.selfEvalPronunciation}
                  onMeaningChange={session.setSelfEvalMeaning}
                  onPronunciationChange={session.setSelfEvalPronunciation}
                  onContinue={() => session.submitSelfEvaluation(false)}
                  onSkip={() => session.submitSelfEvaluation(true)}
                  onRecordAgain={session.recordAgain}
                />
              </div>
            )}

            {currentTurn && state.step === "feedback" && (
              <div className="sa-bubble-row is-student is-current">
                <ConversationRoleHeader role="student" />
                <TurnFeedback
                  session={session}
                  continueLabel={state.turnIndex + 1 < turns.length ? "next" : "finish"}
                />
              </div>
            )}
          </div>
        </div>
      </section>
    </StudentPage>
  );
}
