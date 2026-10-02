import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import type { StudentUiCopyKey } from "../../i18n/student-ui-copy";

export type ConversationRoleChoice = "solo" | "male" | "female";
export type ConversationPartnerGender = Exclude<ConversationRoleChoice, "solo">;

interface ConversationRolePickerProps {
  partnerGender: ConversationPartnerGender;
  disabled: boolean;
  onSelect: (role: ConversationRoleChoice) => void;
}

const ROLE_OPTIONS: ReadonlyArray<{
  value: ConversationRoleChoice;
  labelKey: StudentUiCopyKey;
  descriptionKey: StudentUiCopyKey;
  icon: "microphone" | "users";
}> = [
  {
    value: "solo",
    labelKey: "soloConversationRole",
    descriptionKey: "soloConversationRoleHint",
    icon: "microphone",
  },
  {
    value: "male",
    labelKey: "maleConversationRole",
    descriptionKey: "maleConversationRoleHint",
    icon: "users",
  },
  {
    value: "female",
    labelKey: "femaleConversationRole",
    descriptionKey: "femaleConversationRoleHint",
    icon: "users",
  },
];

export default function ConversationRolePicker({
  partnerGender,
  disabled,
  onSelect,
}: ConversationRolePickerProps) {
  return (
    <fieldset className="sa-conversation-role" disabled={disabled}>
      <legend><StudentSystemText k="chooseConversationRole" /></legend>
      <p className="sa-conversation-role__hint">
        <StudentSystemText k="conversationRoleHint" english="supporting" />
      </p>
      <div className="sa-conversation-role__options">
        {ROLE_OPTIONS.map((option) => {
          const selected = option.value !== "solo" && option.value === partnerGender;
          return (
            <label
              className={`sa-conversation-role__option${selected ? " is-selected" : ""}`}
              key={option.value}
            >
              <input
                type="radio"
                name="conversation-role"
                value={option.value}
                checked={selected}
                onChange={() => onSelect(option.value)}
              />
              <StudentIcon name={option.icon} size={28} role="decorative" />
              <span className="sa-conversation-role__copy">
                <strong><StudentSystemText k={option.labelKey} withinControl /></strong>
                <small><StudentSystemText k={option.descriptionKey} withinControl /></small>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
