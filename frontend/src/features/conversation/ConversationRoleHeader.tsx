import StudentSystemText from "@shared/ui/student/StudentSystemText";
import RoleAvatar from "./RoleAvatar";

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
      <RoleAvatar role={role} compact={history} />
      <span className="sa-bubble-row__dot" aria-hidden="true" />
      {history && isStudent && <span lang="zh-Hant">{"\u4f60"}</span>}
      {(!history || !isStudent) && <StudentSystemText k={isStudent ? "yourResponse" : "speakingCharacter"} />}
    </div>
  );
}
