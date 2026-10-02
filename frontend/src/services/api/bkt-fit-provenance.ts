/** Fit evidence is independent of the provenance of the trace responses. */
export interface BktFitProvenance {
  modelVersion: string | null;
  fitRunId?: string | null;
  evidenceOrigin: "SYNTHETIC" | "REAL" | "ENGINEERING_DEFAULT" | "UNKNOWN";
  synthetic: boolean;
  label: string;
}
