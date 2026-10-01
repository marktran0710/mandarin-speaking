import { useState } from "react";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import type { StudentUiCopyKey } from "../../i18n/student-ui-copy";
import { markOnboardingSeen } from "./onboardingFlag";
import "./OnboardingIntro.css";

interface Step {
  icon: string;
  titleKey: StudentUiCopyKey;
  bodyKey: StudentUiCopyKey;
}

const STEPS: Step[] = [
  { icon: "person", titleKey: "onboardingWelcomeTitle", bodyKey: "onboardingWelcomeBody" },
  { icon: "menu_book", titleKey: "onboardingLessonsTitle", bodyKey: "onboardingLessonsBody" },
  { icon: "star", titleKey: "onboardingFeedbackTitle", bodyKey: "onboardingFeedbackBody" },
  { icon: "flag", titleKey: "onboardingPlacementTitle", bodyKey: "onboardingPlacementBody" },
];

/** A short first-run tour of the system for a brand-new account. The last step
 * hands over to the placement test, which the account must finish before the
 * rest of Student Mode opens. */
export default function OnboardingIntro({ onStartPlacement }: { onStartPlacement: () => void }) {
  const [index, setIndex] = useState(0);
  const step = STEPS[index];
  const isLast = index === STEPS.length - 1;

  const start = () => {
    markOnboardingSeen();
    onStartPlacement();
  };

  return (
    <StudentPage
      layout="task"
      header={
        <StudentPageHeader
          eyebrowKey="onboardingKicker"
          titleKey={step.titleKey}
          aside={<StudentStatusPill tone="info">{`${index + 1} / ${STEPS.length}`}</StudentStatusPill>}
        />
      }
    >
      <StudentSection variant="panel" className="sa-onboarding">
        <div className="sa-onboarding__icon" aria-hidden="true">
          <StudentIcon name={step.icon} size={40} role="decorative" />
        </div>
        <p className="sa-onboarding__body">
          <StudentSystemText k={step.bodyKey} />
        </p>
        <ol className="sa-onboarding__dots" aria-hidden="true">
          {STEPS.map((_, dot) => (
            <li key={dot} className={dot === index ? "is-active" : dot < index ? "is-done" : ""} />
          ))}
        </ol>
        <div className="sa-onboarding__actions">
          {index > 0 && (
            <StudentButton variant="secondary" icon="arrow_back" onClick={() => setIndex(index - 1)}>
              <StudentSystemText k="onboardingBack" withinControl />
            </StudentButton>
          )}
          {isLast ? (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={start}>
              <StudentSystemText k="onboardingStartPlacement" withinControl />
            </StudentButton>
          ) : (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => setIndex(index + 1)}>
              <StudentSystemText k="onboardingNext" withinControl />
            </StudentButton>
          )}
        </div>
      </StudentSection>
    </StudentPage>
  );
}
