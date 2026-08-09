import type { AnalysisVersion } from "../utils/analysisVersion";

interface AnalysisVersionSelectorProps {
  value: AnalysisVersion;
  onChange: (version: AnalysisVersion) => void;
  experimentalAvailable?: boolean;
  experimentalStatus?: string;
  disabled?: boolean;
}

export default function AnalysisVersionSelector({
  value,
  onChange,
  experimentalAvailable = true,
  experimentalStatus,
  disabled = false,
}: AnalysisVersionSelectorProps) {
  const v2Disabled = disabled || !experimentalAvailable;
  return (
    <fieldset className="analysis-version-selector" aria-label="Analysis version">
      <legend>Analysis version</legend>
      <div className="analysis-version-options">
        <button
          type="button"
          className={`analysis-version-button ${value === "stable_v1" ? "selected" : ""}`}
          aria-pressed={value === "stable_v1"}
          disabled={disabled}
          onClick={() => onChange("stable_v1")}
        >
          Stable V1 — Current
        </button>
        <button
          type="button"
          className={`analysis-version-button ${value === "phoneme_tone_v2" ? "selected experimental" : "experimental"}`}
          aria-pressed={value === "phoneme_tone_v2"}
          aria-label="Experimental V2 — Character, phoneme and tone detection"
          title="Character, phoneme and tone detection. Not teacher validated."
          disabled={v2Disabled}
          onClick={() => onChange("phoneme_tone_v2")}
        >
          Experimental V2 <span className="analysis-version-badge">Experimental</span>
        </button>
      </div>
      {value === "phoneme_tone_v2" && (
        <p className="analysis-version-note">
          Character, phoneme and T1–T5 detection. This attempt does not change progression.
          {experimentalStatus ? ` Status: ${experimentalStatus}.` : ""}
        </p>
      )}
      {!experimentalAvailable && <p className="analysis-version-note">Experimental V2 is temporarily unavailable; Stable V1 is still ready.</p>}
    </fieldset>
  );
}
