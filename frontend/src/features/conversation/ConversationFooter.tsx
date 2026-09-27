import StudentButton from "@shared/ui/student/StudentButton";
import StudentSystemText from "@shared/ui/student/StudentSystemText";

interface ConversationFooterProps {
  continueLabel: "next" | "finish";
  onRecordAgain: () => void;
  onContinue: () => void;
}
export default function ConversationFooter({ continueLabel, onRecordAgain, onContinue }: ConversationFooterProps) {
  return (
    <div className="sa-inline-feedback__actions sa-conversation__footer">
      <StudentButton variant="secondary" icon="replay" onClick={onRecordAgain}><StudentSystemText k="recordAgain" withinControl /></StudentButton>
      <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onContinue}><StudentSystemText k={continueLabel === "finish" ? "finish" : "next"} withinControl /></StudentButton>
    </div>
  );
}
