import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentIcon from "../primitives/StudentIcon";
import "../primitives/layout.css";
import "./PlacementStubPage.css";

export default function PlacementStubPage() {
  return (
    <div className="sa-page-container">
      <StudentPageHeader
        eyebrowEn="Placement"
        titleZh="分級測驗"
        titleEn="Placement Test"
      />

      <StudentSection variant="panel">
        <div className="sa-placement__empty">
          <StudentIcon name="flag" size={22} role="decorative" />
          <p>Placement testing is coming soon.</p>
        </div>
      </StudentSection>
    </div>
  );
}
