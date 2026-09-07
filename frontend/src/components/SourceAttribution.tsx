import "./SourceAttribution.css";

/**
 * Educational-use attribution for the source textbook. The practice stories,
 * dialogues and vocabulary in this app are adapted from NTNU's 時代華語一
 * (Modern Chinese 1); this app is a non-commercial teaching aid. The notice
 * sits at the foot of every page so the provenance
 * travels with the content wherever a learner or teacher lands.
 *
 * Rendered in normal document flow (not fixed) so it never overlaps content —
 * it appears at the bottom of each page's own scroll area.
 */
export default function SourceAttribution({
  className = "",
}: {
  className?: string;
}) {
  return (
    <div className={`source-attribution ${className}`.trim()}>
      <p className="source-attribution-zh" lang="zh-Hant">
        本教材改編自國立臺灣師範大學《時代華語一》，僅供教學使用，非商業用途。
      </p>
      <p className="source-attribution-en" lang="en">
        Materials adapted from NTNU&nbsp;“Modern Chinese&nbsp;1.” For educational, non-commercial use only.
      </p>
    </div>
  );
}
