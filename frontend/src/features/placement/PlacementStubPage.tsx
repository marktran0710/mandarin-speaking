import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill, { type StudentStatusTone } from "@shared/ui/student/StudentStatusPill";
import "@shared/ui/student/layout.css";
import {
  unavailablePlacementSession,
  usePlacementSession,
  type PlacementSessionAdapter,
  type PlacementSessionStatus,
} from "./placementSession";
import "./PlacementStubPage.css";

export interface PlacementStubPageProps {
  adapter?: PlacementSessionAdapter;
}

interface PlacementStatusPresentation {
  label: string;
  tone: StudentStatusTone;
  heading: string;
  body: string;
}

const STATUS_PRESENTATION: Record<PlacementSessionStatus, PlacementStatusPresentation> = {
  unavailable: {
    label: "Not available",
    tone: "neutral",
    heading: "Placement test not available",
    body: "The placement assessment is not available in this learning workspace yet.",
  },
  loading: {
    label: "Loading",
    tone: "info",
    heading: "Placement test is loading",
    body: "The placement assessment is being prepared. No assessment data is shown until the session is ready.",
  },
  ready: {
    label: "Ready",
    tone: "info",
    heading: "Placement test is ready",
    body: "The placement assessment can be connected here when its learner-facing session contract is available.",
  },
  complete: {
    label: "Complete",
    tone: "success",
    heading: "Placement test complete",
    body: "Placement results will appear here when the assessment result contract is available.",
  },
  error: {
    label: "Unavailable",
    tone: "danger",
    heading: "Placement test unavailable",
    body: "The placement assessment could not be loaded. No assessment data is shown.",
  },
};

export default function PlacementStubPage({ adapter = unavailablePlacementSession }: PlacementStubPageProps) {
  const session = usePlacementSession(adapter);
  const presentation = STATUS_PRESENTATION[session.status];

  return (
    <div className="sa-page-container sa-placement">
      <StudentPageHeader
        eyebrowEn="Placement"
        eyebrowZh="入門測驗"
        titleZh="入門測驗"
        titleEn="Placement Test"
        aside={<StudentStatusPill tone={presentation.tone}>{presentation.label}</StudentStatusPill>}
      />

      <StudentSection
        variant="panel"
        className="sa-placement__card"
        aria-labelledby="placement-test-heading"
      >
        <div className="sa-placement__accent" aria-hidden="true" />
        <div className="sa-placement__body">
          <div className="sa-placement__intro">
            <div className="sa-placement__icon" aria-hidden="true">
              <StudentIcon name="flag" size={20} role="decorative" />
            </div>
            <div className="sa-placement__intro-copy">
              <p className="sa-placement__kicker">Assessment availability</p>
              <h2 id="placement-test-heading">{presentation.heading}</h2>
              <p className="sa-placement__description">{presentation.body}</p>
            </div>
          </div>

          <div className="sa-placement__notice" role="status" aria-live="polite">
            <StudentIcon name="info" size={18} role="decorative" />
            <p>
              <span lang="zh-Hant">入門測驗目前未開放。</span>
              <span>Placement testing will appear here when it is enabled for learners.</span>
            </p>
          </div>
        </div>
      </StudentSection>
    </div>
  );
}
