import StudentSystemText from "@shared/ui/student/StudentSystemText";

interface ConversationRoleHeaderProps {
  role: "character" | "student";
  history?: boolean;
}

/** Shared speaker marker used by history and the active conversation turn. */
export default function ConversationRoleHeader({ role, history = false }: ConversationRoleHeaderProps) {
  const isStudent = role === "student";

  return (
    <div
      className={`sa-bubble-row__who${history ? " sa-bubble-row__who--history" : ""}`}
      data-role-header={role}
    >
      <span className="sa-bubble-row__dot" aria-hidden="true" />
      {history && isStudent ? <span lang="zh-Hant">你</span> : <StudentSystemText k={isStudent ? "yourResponse" : "speakingCharacter"} />}
    </div>
  );
}
