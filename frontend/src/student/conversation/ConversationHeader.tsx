import StudentIcon from "../primitives/StudentIcon";

interface ConversationHeaderProps {
  title: string;
  currentExchange: number;
  totalExchanges: number;
  onBack: () => void;
}
export default function ConversationHeader({ title, currentExchange, totalExchanges, onBack }: ConversationHeaderProps) {
  return (
    <header className="sa-conversation__header">
      <button type="button" className="sa-conversation__back" onClick={onBack}>
        <StudentIcon name="arrow_back" size={18} role="decorative" />
        <span>Back to Study</span>
      </button>
      <div className="sa-conversation__title">
        <span lang="zh-Hant">{title}</span>
      </div>
      <div className="sa-conversation__progress" aria-label={`Exchange ${currentExchange} of ${totalExchanges}`}>
        <span>Exchange {currentExchange} / {totalExchanges}</span>
        <span className="sa-conversation__progress-track" aria-hidden="true">
          <span style={{ width: `${totalExchanges > 0 ? (currentExchange / totalExchanges) * 100 : 0}%` }} />
        </span>
      </div>
    </header>
  );
}
