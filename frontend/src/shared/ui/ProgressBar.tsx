interface ProgressBarProps {
  value: number;
  label?: string;
  tone?: "jade" | "amber";
}

export default function ProgressBar({ value, label, tone = "jade" }: ProgressBarProps) {
  const safeValue = Math.max(0, Math.min(100, value));
  return (
    <div
      className={`workspace-progress-track${tone === "amber" ? " workspace-progress-track-amber" : ""}`}
      aria-label={label ?? `${Math.round(safeValue)}% progress`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(safeValue)}
    >
      <span style={{ width: `${safeValue}%` }} />
    </div>
  );
}
