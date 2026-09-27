import type { ReactNode } from "react";
import StudentIcon from "./StudentIcon";
import StudentSystemText from "./StudentSystemText";
import type { StudentUiCopyKey } from "../../../i18n/student-ui-copy";
import "./StudentPageHeader.css";

interface StudentPageHeaderProps {
  eyebrowKey?: StudentUiCopyKey;
  titleKey: StudentUiCopyKey;
  /** Dynamic lesson/topic context is intentionally plain content, not UI copy. */
  context?: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
  /** Only the "stage" layout's Conversation screen uses this today — Story
   * Speaking has no back affordance and none is added here (no new
   * navigation is invented for it). */
  onBack?: () => void;
}

export default function StudentPageHeader({
  eyebrowKey,
  titleKey,
  context,
  subtitle,
  aside,
  onBack,
}: StudentPageHeaderProps) {
  return (
    <header className="sa-page-header">
      <div className="sa-page-header__copy">
        {onBack && (
          <button
            type="button"
            className="sa-page-header__back"
            onClick={onBack}
          >
            <StudentIcon name="arrow_back" size={18} role="decorative" />
            <span>
              <StudentSystemText k="backToStudy" withinControl />
            </span>
          </button>
        )}
        {eyebrowKey && <p className="sa-page-header__eyebrow"><StudentSystemText k={eyebrowKey} />{context && <> · <span className="sa-page-header__context">{context}</span></>}</p>}
        <h1 className="sa-page-header__title">
          <StudentSystemText k={titleKey} />
        </h1>
        {subtitle && <p className="sa-page-header__subtitle">{subtitle}</p>}
      </div>
      {aside && <div className="sa-page-header__aside">{aside}</div>}
    </header>
  );
}
