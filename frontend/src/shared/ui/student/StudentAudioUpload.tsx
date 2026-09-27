import { useRef, type ChangeEvent } from "react";
import StudentButton from "./StudentButton";
import StudentSystemText from "./StudentSystemText";
import { studentUiCopy, type StudentUiCopyKey } from "../../../i18n/student-ui-copy";

interface StudentAudioUploadProps {
  onSelect: (file: File) => void | Promise<void>;
  disabled?: boolean;
  label?: string;
  labelKey?: StudentUiCopyKey;
  className?: string;
}

/** A keyboard-accessible audio file picker styled like the student actions. */
export default function StudentAudioUpload({
  onSelect,
  disabled = false,
  label = "上傳錄音",
  labelKey,
  className,
}: StudentAudioUploadProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Clear the value so choosing the same file again still emits change.
    event.target.value = "";
    if (file) void onSelect(file);
  };

  return (
    <>
      <StudentButton
        variant="secondary"
        icon="upload"
        className={className}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        {labelKey ? <StudentSystemText k={labelKey} withinControl /> : label}
      </StudentButton>
      <input
        ref={inputRef}
        type="file"
        accept="audio/*"
        aria-label={labelKey ? studentUiCopy[labelKey].zh : label}
        hidden
        onChange={handleChange}
      />
    </>
  );
}

export type { StudentAudioUploadProps };
