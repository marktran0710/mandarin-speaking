/** Overlays the student's measured pitch curve against the idealized target
 * shape for the expected tone(s) — both scaled to a shared time/pitch range
 * so the two lines are directly comparable, making the exact mismatch
 * (wrong direction, not enough movement, dip too shallow, etc.) visible
 * rather than something the student has to infer from a text description. */
export default function MiniContourChart({
  actual,
  reference,
}: {
  actual: Array<[number, number]>;
  reference?: Array<[number, number]>;
}) {
  const width = 160;
  const height = 66;
  const padY = 8;

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
