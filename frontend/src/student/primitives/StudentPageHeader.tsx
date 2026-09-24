import type { ReactNode } from "react";
import "./StudentPageHeader.css";

interface StudentPageHeaderProps {
  eyebrowZh?: string;
  eyebrowEn: string;
  titleZh: string;
  titleEn: string;
  aside?: ReactNode;
}

export default function StudentPageHeader({ eyebrowZh, eyebrowEn, titleZh, titleEn, aside }: StudentPageHeaderProps) {
  return (
    <header className="sa-page-header">
      <div className="sa-page-header__copy">
        <p className="sa-page-header__eyebrow">
          {eyebrowEn}
          {eyebrowZh && <span lang="zh-Hant"> · {eyebrowZh}</span>}
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
