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
        本教材改編自國立臺灣師範大學《時代華語（一）》，原著作之權利歸原權利人所有。僅供教學與學習使用，不作商業用途。
      </p>
      <p className="source-attribution-en" lang="en">
        Adapted from <em>Modern Chinese&nbsp;1</em> (時代華語一), National Taiwan Normal University. All rights in the original work remain with their respective owners. For non-commercial educational use only.
      </p>
    </div>
  );
}
