import type { ConversationSession } from "./useConversationSession";
import ConversationFooter from "./ConversationFooter";
import { SpeechResultReview } from "@entities/speech";
import StudentSystemText from "@shared/ui/student/StudentSystemText";

interface TurnFeedbackProps {
  session: ConversationSession;
  continueLabel: "next" | "finish";
}
export default function TurnFeedback({ session, continueLabel }: TurnFeedbackProps) {
  const { lastAnalysis, lastResult, lastRecognizedText } = session;
  if (!lastAnalysis || !lastResult) return null;

  return (
    <section className="sa-bubble sa-bubble--feedback" aria-label="錄音回饋">
      <SpeechResultReview
        targetScript={session.currentTurn?.targetText || session.currentTurn?.text || ""}
        transcript={lastRecognizedText}
        metrics={lastResult.metrics}
        audioBlob={lastResult.audioBlob}
        audioUrl={lastResult.audioUrl}
        meaningPassed={lastAnalysis.accepted}
      />
      {lastResult.verified && <p className="sa-conversation__verified"><StudentSystemText k="verifiedRecording" /></p>}
      <ConversationFooter
        continueLabel={continueLabel}
        onRecordAgain={session.recordAgain}
        onContinue={session.nextTurn}
      />
    </section>
  );
}
