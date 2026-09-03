/** Overlays the student's measured pitch curve against the idealized target
 * shape for the expected tone(s).
 *
 * Preferred mode: `userCurve`/`targetCurve` — the exact normalized [0,1]
 * arrays the backend's shape score compared. Both are drawn mean-centered
 * on a FIXED vertical scale, mirroring the score's own math (correlation is
 * offset-invariant; its distance term compares mean-centered curves), so
 * "the two lines look alike" and "the score is high" agree by construction.
 * The old raw-Hz mode auto-scaled both lines into the union of their own
 * ranges, which lied in both directions: a flat attempt squashed the target
 * flat too (looked fine, scored low), while one octave-error frame
 * stretched the range so a good attempt looked wrong (but scored high,
 * since scoring clips outliers).
 *
 * Legacy mode (`actual`/`reference`, raw Hz over time) remains as the
 * fallback for segments too short to score, which have no normalized pair. */
export default function MiniContourChart({
  actual,
  reference,
  userCurve,
  targetCurve,
}: {
  actual: Array<[number, number]>;
  reference?: Array<[number, number]>;
  userCurve?: number[];
  targetCurve?: number[];
}) {
  const width = 160;
  const height = 66;
  const padY = 8;

  const hasNormalized =
    (userCurve?.length ?? 0) > 1 && (targetCurve?.length ?? 0) > 1;

  if (hasNormalized) {
    // Fixed domain: a mean-centered [0,1] curve deviates at most ±0.5 from
    // its own mean. Never rescale per-card — a fixed frame is what makes
    // "flatter than the target" visible instead of normalized away.
    const DOMAIN = 0.55;
    const toPath = (series: number[]) => {
      const mean = series.reduce((s, v) => s + v, 0) / series.length;
      return series
        .map((v, index) => {
          const x = (index / (series.length - 1)) * width;
          const centered = Math.max(-DOMAIN, Math.min(DOMAIN, v - mean));
          const y =
            height / 2 - (centered / DOMAIN) * (height / 2 - padY);
          return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
        })
        .join(" ");
    };

    return (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mini-contour-svg"
        aria-hidden="true"
        preserveAspectRatio="none"
      >
        <path
          d={toPath(targetCurve!)}
          className="mini-contour-reference"
          fill="none"
        />
        <path
          d={toPath(userCurve!)}
          className="mini-contour-actual"
          fill="none"
        />
      </svg>
    );
  }

  const points =
    reference && reference.length > 1 ? [...actual, ...reference] : actual;
  if (points.length < 2) {
    return (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mini-contour-svg"
        aria-hidden="true"
      />
    );
  }

  const times = points.map((p) => p[0]);
  const freqs = points.map((p) => p[1]);
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  const minF = Math.min(...freqs);
  const maxF = Math.max(...freqs);
  const timeSpan = Math.max(maxT - minT, 0.001);
  const freqSpan = Math.max(maxF - minF, 1);

  const toPath = (series: Array<[number, number]>) =>
    series
      .map(([t, f], index) => {
        const x = ((t - minT) / timeSpan) * width;
        const y = height - padY - ((f - minF) / freqSpan) * (height - padY * 2);
        return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="mini-contour-svg"
      role="img"
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      {reference && reference.length > 1 && (
        <path
          d={toPath(reference)}
          className="mini-contour-reference"
          fill="none"
        />
      )}
      {actual.length > 1 && (
        <path d={toPath(actual)} className="mini-contour-actual" fill="none" />
      )}
    </svg>
  );
}
