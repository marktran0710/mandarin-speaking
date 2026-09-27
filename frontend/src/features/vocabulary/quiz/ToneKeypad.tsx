import type { RefObject } from "react";
import StudentIcon from "@shared/ui/student/StudentIcon";
import { applyToneMark } from "./questionModel";
import StudentSystemText from "@shared/ui/student/StudentSystemText";

interface ToneKeypadProps {
  inputRef: RefObject<HTMLInputElement | null>;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

const TONE_GROUPS = [
  { base: "a", marks: ["ā", "á", "ǎ", "à"] },
  { base: "e", marks: ["ē", "é", "ě", "è"] },
  { base: "i", marks: ["ī", "í", "ǐ", "ì"] },
  { base: "o", marks: ["ō", "ó", "ǒ", "ò"] },
  { base: "u", marks: ["ū", "ú", "ǔ", "ù"] },
  { base: "ü", marks: ["ǖ", "ǘ", "ǚ", "ǜ"] },
] as const;

export default function ToneKeypad({ inputRef, value, onChange, disabled = false }: ToneKeypadProps) {
  const insertTone = (tone: 1 | 2 | 3 | 4) => {
    const input = inputRef.current;
    const selectionStart = input?.selectionStart ?? value.length;
    const selectionEnd = input?.selectionEnd ?? selectionStart;
    const edit = applyToneMark(value, tone, selectionStart, selectionEnd);
    onChange(edit.value);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(edit.cursor, edit.cursor);
    });
  };

  return (
    <div className="sa-quiz__tone-keypad" aria-label="聲調符號鍵盤">
      <div className="sa-quiz__tone-keypad-heading">
        <span><StudentIcon name="edit_note" size={16} role="decorative" /> <StudentSystemText k="toneMarks" /></span>
        <span>1 平 · 2 升 · 3 降升 · 4 降</span>
      </div>
      <div className="sa-quiz__tone-grid">
        {TONE_GROUPS.map((group) => (
          <div className="sa-quiz__tone-row" key={group.base}>
            <span className="sa-quiz__tone-base" aria-hidden="true">{group.base}</span>
            {group.marks.map((mark, index) => (
              <button
                key={mark}
                type="button"
                className="sa-quiz__tone-key"
                disabled={disabled}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => insertTone((index + 1) as 1 | 2 | 3 | 4)}
                aria-label={`${group.base} tone ${index + 1}: ${mark}`}
              >
                {mark}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
