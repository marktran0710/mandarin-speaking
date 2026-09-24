import { useEffect, useMemo, useState } from "react";
import { getContentInventory, type ContentDoctorFinding, type ContentDoctorReport } from "../services/api/content-doctor";
import "./AdminContentDoctorPage.css";

type SeverityFilter = "all" | "error" | "warning";

function detailText(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

function storyTitle(report: ContentDoctorReport, storyId: string | null): string {
  if (!storyId) return "";
  return report.lessons.find((lesson) => lesson.storyId === storyId)?.title || storyId;
}

/** Admin-only, read-only diagnostic over the existing content-inventory
 * report (backend/services/content_inventory.py) - never writes curriculum
 * rows or media files. This page is purely a viewer; every check it
 * surfaces already runs server-side (and via the `content_doctor.py` CLI),
 * this just gives Admin somewhere to actually see the findings instead of
 * only reaching them through a raw JSON file or the CLI. */
export default function AdminContentDoctorPage() {
  const [report, setReport] = useState<ContentDoctorReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [severity, setSeverity] = useState<SeverityFilter>("error");

  const load = () => {
    setLoading(true);
    setError("");
    getContentInventory()
      .then(setReport)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load the content inventory report."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const findings = useMemo<ContentDoctorFinding[]>(() => {
    if (!report) return [];
    return severity === "all" ? report.findings : report.findings.filter((finding) => finding.severity === severity);
  }, [report, severity]);

  return (
    <section className="admin-content-doctor" aria-label="Content Doctor">
      <p className="admin-content-doctor-note">
        Read-only consistency report over the current curriculum content and uploaded media.
        Nothing on this page changes any data - fix issues from Vocabulary, Materials, or the
        story editor, then refresh here to confirm.
      </p>

      <div className="admin-content-doctor-toolbar">
        <button type="button" onClick={load} disabled={loading}>
          {loading ? "Checking…" : "Refresh"}
        </button>
        {report && <span className="admin-content-doctor-generated">Generated {new Date(report.generatedAt).toLocaleString()}</span>}
      </div>

      {error && <p className="admin-content-doctor-error" role="alert">{error}</p>}

      {report && (
        <>
          <div className="admin-content-doctor-summary">
            <div><span>Stories</span><strong>{report.summary.stories}</strong><small>{report.summary.publishedStories} published</small></div>
            <div><span>Canonical words</span><strong>{report.summary.canonicalWords}</strong></div>
            <div><span>Quiz questions</span><strong>{report.summary.quizQuestions}</strong></div>
            <div><span>Media references</span><strong>{report.summary.mediaReferences}</strong></div>
            <div><span>Orphan files</span><strong>{report.summary.orphanFiles}</strong></div>
            <div className={report.summary.findingsBySeverity.error ? "is-error" : undefined}>
              <span>Errors</span><strong>{report.summary.findingsBySeverity.error ?? 0}</strong>
            </div>
            <div className={report.summary.findingsBySeverity.warning ? "is-warning" : undefined}>
              <span>Warnings</span><strong>{report.summary.findingsBySeverity.warning ?? 0}</strong>
            </div>
          </div>

          <div className="admin-content-doctor-filter" role="radiogroup" aria-label="Filter findings by severity">
            {(["error", "warning", "all"] as const).map((option) => (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={severity === option}
                className={severity === option ? "is-active" : undefined}
                onClick={() => setSeverity(option)}
              >
                {option === "all" ? "All" : option === "error" ? "Errors" : "Warnings"}
              </button>
            ))}
          </div>

          {findings.length === 0 ? (
            <p className="admin-content-doctor-empty">No {severity === "all" ? "" : severity} findings.</p>
          ) : (
            <ul className="admin-content-doctor-findings">
              {findings.map((finding, index) => (
                <li key={`${finding.code}-${index}`} className={finding.severity === "error" ? "is-error" : "is-warning"}>
                  <div className="admin-content-doctor-finding-head">
                    <span className="admin-content-doctor-finding-code">{finding.code.replace(/_/g, " ")}</span>
                    {finding.storyId && <span className="admin-content-doctor-finding-story">{storyTitle(report, finding.storyId)}</span>}
                  </div>
                  <p className="admin-content-doctor-finding-location">{finding.location}</p>
                  {finding.detail != null && <p className="admin-content-doctor-finding-detail">{detailText(finding.detail)}</p>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
