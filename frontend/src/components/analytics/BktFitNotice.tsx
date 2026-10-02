import type { BktFitProvenance } from "../../services/api/bkt-fit-provenance";

export default function BktFitNotice({ provenance, title = "Active BKT fit" }: { provenance?: BktFitProvenance; title?: string }) {
  const origin = provenance?.evidenceOrigin ?? "UNKNOWN";
  return (
    <aside aria-label={title}>
      <p><strong>{origin === "SYNTHETIC" ? "SYNTHETIC FIT" : origin === "REAL" ? "REAL-EVIDENCE FIT" : origin === "ENGINEERING_DEFAULT" ? "ENGINEERING DEFAULTS" : "FIT PROVENANCE UNKNOWN"}</strong>{" · "}{title}{provenance?.modelVersion && <> · <code>{provenance.modelVersion}</code></>}</p>
      <p>{provenance?.label ?? "Fit provenance unavailable; do not treat as human pilot calibration."}</p>
    </aside>
  );
}
