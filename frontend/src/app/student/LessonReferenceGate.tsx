import StudentButton from "@shared/ui/student/StudentButton";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import type { StoryReferenceDataStatus } from "./useStoryReferenceData";

interface LessonReferenceGateProps {
  status: Exclude<StoryReferenceDataStatus, "ready">;
  onRetry: () => void;
}

/** Shown in place of Story Speaking / Conversation while the lesson's pitch
 * data loads. Recording before it arrives would score against no reference. */
export default function LessonReferenceGate({ status, onRetry }: LessonReferenceGateProps) {
  return (
    <StudentPage
      layout="task"
      header={<StudentPageHeader titleKey={status === "loading" ? "loading" : "unavailable"} />}
      state={status}
      errorText={(
        <>
          <StudentSystemText k="retryNetwork" />{" "}
          <StudentButton variant="primary" onClick={onRetry}>
            <StudentSystemText k="retry" withinControl />
          </StudentButton>
        </>
      )}
    />
  );
}
