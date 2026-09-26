import type { ConversationSession } from "./useConversationSession";
import ConversationFooter from "./ConversationFooter";
import { SpeechResultReview } from "@entities/speech";

interface TurnFeedbackProps {
  session: ConversationSession;
  continueLabel: string;
}
export default function TurnFeedback({ session, continueLabel }: TurnFeedbackProps) {
  const { lastAnalysis, lastResult, lastRecognizedText } = session;
  if (!lastAnalysis || !lastResult) return null;

  return (
    <section className="sa-bubble sa-bubble--feedback" aria-label="Recording feedback">
      <SpeechResultReview
        targetScript={session.currentTurn?.targetText || session.currentTurn?.text || ""}
        transcript={lastRecognizedText}
        metrics={lastResult.metrics}
        audioBlob={lastResult.audioBlob}
        audioUrl={lastResult.audioUrl}
        meaningPassed={lastAnalysis.accepted}
        pronunciationPassed={lastResult.masteryPassed}
      />
      {lastResult.verified && <p className="sa-conversation__verified">Verified recording</p>}
      <ConversationFooter
        continueLabel={continueLabel}
        onRecordAgain={session.recordAgain}
        onContinue={session.nextTurn}
      />
    </section>
  );
}
