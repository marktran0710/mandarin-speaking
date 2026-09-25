import type { ReactNode } from "react";
import StudentIcon from "./StudentIcon";
import "./StudentPageHeader.css";

interface StudentPageHeaderProps {
  /** Chinese primary + English secondary on every label (D2) — both required,
   * no English-only eyebrow. */
  eyebrowZh: string;
  eyebrowEn: string;
  titleZh: string;
  titleEn: string;
  aside?: ReactNode;
  /** Only the "stage" layout's Conversation screen uses this today — Story
   * Speaking has no back affordance and none is added here (no new
   * navigation is invented for it). */
  onBack?: () => void;
}

export default function StudentPageHeader({ eyebrowZh, eyebrowEn, titleZh, titleEn, aside, onBack }: StudentPageHeaderProps) {
  return (
    <header className="sa-page-header">
      <div className="sa-page-header__copy">
        {onBack && (
          <button type="button" className="sa-page-header__back" onClick={onBack}>
            <StudentIcon name="arrow_back" size={18} role="decorative" />
            <span><span lang="zh-Hant">返回</span> · Back to Study</span>
          </button>
        )}
        <p className="sa-page-header__eyebrow">
          <span lang="zh-Hant">{eyebrowZh}</span> · {eyebrowEn}
        </p>
        <h1 className="sa-page-header__title">
          <span lang="zh-Hant">{titleZh}</span>
        </h1>
        <p className="sa-page-header__subtitle">{titleEn}</p>
      </div>
      {aside && <div className="sa-page-header__aside">{aside}</div>}
    </header>
  );
}
