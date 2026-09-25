import StudentIcon from "@shared/ui/student/StudentIcon";

interface ConversationHeaderProps {
  title: string;
  description?: string;
  currentExchange: number;
  totalExchanges: number;
  onBack: () => void;
}
export default function ConversationHeader({ title, description, currentExchange, totalExchanges, onBack }: ConversationHeaderProps) {
  const progress = totalExchanges > 0 ? Math.min(100, (currentExchange / totalExchanges) * 100) : 0;

  return (
    <header className="sa-conversation__header">
      <div className="sa-conversation__header-main">
        <button type="button" className="sa-conversation__back" onClick={onBack}>
          <StudentIcon name="arrow_back" size={18} role="decorative" />
          <span>Back to Study</span>
        </button>
        <span className="sa-conversation__divider" aria-hidden="true">/</span>
        <div className="sa-conversation__context">
          <h1 className="sa-conversation__title" lang="zh-Hant">{title}</h1>
          {description && <span className="sa-conversation__description">{description}</span>}
        </div>
      </div>
      <div
        className="sa-conversation__progress"
        aria-label={`Exchange ${currentExchange} of ${totalExchanges}`}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={totalExchanges}
        aria-valuenow={currentExchange}
      >
        <span className="sa-conversation__progress-copy">
          <span>Exchange</span>
          <strong>{currentExchange}</strong>
          <span>/ {totalExchanges}</span>
        </span>
        <span className="sa-conversation__progress-track" aria-hidden="true">
          <span style={{ width: `${progress}%` }} />
        </span>
      </div>
    </header>
  );
}
