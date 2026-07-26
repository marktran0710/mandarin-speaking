// One-off semantic-review dump: every quiz entry's word / translation /
// pinyin / AI data per story+difficulty, compact enough for a human (or
// Claude) to read end-to-end. Reads the audit fixture, mirrors the
// vocabulary/translation comma-split alignment the app performs.
// Run: node scripts/dump-quiz-entries.mjs > quiz-entries.txt
import { readFileSync } from "node:fs";

const stories = JSON.parse(
  readFileSync(new URL("../src/components/__fixtures__/custom-stories.json", import.meta.url), "utf8"),
);

const SUFFIX = { easy: "", medium: "Medium", hard: "Hard" };
const splitList = (s) => (s || "").split(",").map((w) => w.trim()).filter(Boolean);
const tier = (frame, base, level) => frame[`${base}${SUFFIX[level]}`] || (level === "easy" ? frame[base] : null);

for (const story of stories) {
  for (const level of ["easy", "medium", "hard"]) {
    const hasTier =
      level === "easy" ||
      story.frames.some((f) => (f[`vocabulary${SUFFIX[level]}`] || "").trim());
    if (!hasTier) continue;
    console.log(`\n████ ${story.title} (${level}) — published: ${story.published}`);
    story.frames.forEach((frame, fi) => {
      const words = splitList(tier(frame, "vocabulary", level));
      const trans = splitList(tier(frame, "vocabularyTranslation", level));
      const pinyin = splitList(tier(frame, "vocabularyPinyin", level));
      const pos = splitList(tier(frame, "vocabularyPos", level));
      if (words.length === 0) return;
      const mismatch =
        words.length !== trans.length || (pinyin.length > 0 && pinyin.length !== words.length)
          ? `  ⚠️ COUNT MISMATCH words=${words.length} trans=${trans.length} pinyin=${pinyin.length}`
          : "";
      console.log(` scene ${fi + 1}${mismatch}`);
      let distractors = [];
      let synonyms = [];
      try { distractors = JSON.parse(frame[`vocabularyDistractors${SUFFIX[level]}`] || frame.vocabularyDistractors || "[]"); } catch {}
      try { synonyms = JSON.parse(frame[`vocabularySynonym${SUFFIX[level]}`] || frame.vocabularySynonym || "[]"); } catch {}
      words.forEach((w, i) => {
        const syn = (synonyms[i] || []).map((s) => `${s.synonym}(vs ${s.distractors.join("/")})`).join("; ");
        console.log(
          `   ${w} [${pinyin[i] ?? "-"}] (${pos[i] ?? "-"}) = ${trans[i] ?? "??MISSING??"}` +
            ` | dis: ${(distractors[i] || []).join(", ") || "-"}` +
            (syn ? ` | syn: ${syn}` : ""),
        );
      });
    });
  }
}
