import type { ConversationSession } from "./useConversationSession";
import PitchChart from "../../components/pitch/PitchChart";
import StudentInlineFeedback from "@shared/ui/student/StudentInlineFeedback";
import ConversationFooter from "./ConversationFooter";
import { mapWordProsodyToAlignment } from "@entities/speech/wordAlignment";

interface TurnFeedbackProps {
  session: ConversationSession;
  continueLabel: string;
}
export default function TurnFeedback({ session, continueLabel }: TurnFeedbackProps) {
  const { lastAnalysis, lastResult, lastRecognizedText } = session;
  if (!lastAnalysis || !lastResult) return null;

  const weakestWord = lastAnalysis.legacyPracticeWords[0]?.token
    ?? lastAnalysis.weakItems[0]?.token
    ?? lastAnalysis.failedWords[0]?.token;

  return (
    <section className="sa-bubble sa-bubble--feedback" aria-label="Recording feedback">
      <p className="sa-conversation__you-said">
        You said <span lang="zh-Hant">{lastRecognizedText || "No transcript available"}</span>
      </p>
      <div className="sa-conversation__feedback-heading">
        <span>Acoustic alignment</span>
        <span>Tonal integrity</span>
      </div>
      <StudentInlineFeedback
        meaningOk={lastAnalysis.accepted}
        pronunciationOk={lastResult.masteryPassed}
        pronunciationNote={weakestWord}
        coachText={lastAnalysis.corrective?.hint || undefined}
        wordChips={mapWordProsodyToAlignment(lastResult.metrics.word_prosody)}
        detailsContent={lastResult.metrics.pitch_contour?.length > 0 ? (
          <PitchChart pitchContour={lastResult.metrics.pitch_contour} detectedTone={lastResult.metrics.detected_tone} />
        ) : (
          <p className="sa-conversation__no-pitch">No pitch data captured for this attempt.</p>
        )}
        footer={
          <>
            {lastResult.verified && <p className="sa-conversation__verified">Verified recording</p>}
            <ConversationFooter
              continueLabel={continueLabel}
              onRecordAgain={session.recordAgain}
              onContinue={session.nextTurn}
            />
          </>
        }
      />
    </section>
  );
}
