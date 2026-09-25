import StudentButton from "@shared/ui/student/StudentButton";

interface ConversationFooterProps {
  continueLabel: string;
  onRecordAgain: () => void;
  onContinue: () => void;
}
export default function ConversationFooter({ continueLabel, onRecordAgain, onContinue }: ConversationFooterProps) {
  return (
    <div className="sa-inline-feedback__actions sa-conversation__footer">
      <StudentButton variant="secondary" icon="replay" onClick={onRecordAgain}>Record again</StudentButton>
      <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onContinue}>{continueLabel}</StudentButton>
    </div>
  );
}
