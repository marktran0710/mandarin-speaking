// One-off data repair (2026-07-23): the quiz audit found four scenes whose
// vocabulary/translation comma-lists were misaligned (a word glossed with
// two comma-separated translations shifts every later word onto its
// neighbour's gloss — 他們 ended up "afterwards", 去 ended up "to want"),
// plus a few authored-pinyin typos. Posts corrected stories back through
// the same upsert endpoint the teacher UI uses.
// Run: node scripts/fix-quiz-data.mjs
const BACKEND = "http://127.0.0.1:8000";

const stories = await fetch(`${BACKEND}/api/custom-stories`).then((r) => r.json());
const byTitle = (part) => stories.find((s) => s.title.includes(part));

const changes = [];

// ── 我們去喝下午茶 (easy) scene 4: "good, okay" double-gloss for 好啊 ──
{
  const story = byTitle("下午茶");
  const frame = story.frames[3];
  frame.vocabularyTranslation = "okay, you, to want, to go, where";
  changes.push([story, "下午茶 scene4 translations realigned (5 words = 5 glosses)"]);
}

// ── 我們去士林夜市 (medium) scene 5: "good, okay" + "but, however" doubles ──
{
  const story = byTitle("士林");
  const frame = story.frames[4];
  frame.vocabularyTranslationMedium = "okay, but, even more, bubble milk tea, there";
  // The milk-tea distractor list was authored for 珍珠奶茶 but sat on 可's
  // index after the same shift — move it home, leave 可 with none.
  try {
    const dis = JSON.parse(frame.vocabularyDistractorsMedium || "[]");
    if (dis.length === 2) {
      frame.vocabularyDistractorsMedium = JSON.stringify([dis[0], [], [], dis[1], []]);
    }
  } catch {}
  changes.push([story, "士林夜市 medium scene5 translations realigned + distractors rehomed"]);
}

// ── 他們學校在山上 (easy): double glosses in scenes 2-4 ──
{
  const story = byTitle("山上");
  const f2 = story.frames[1];
  f2.vocabularyTranslation =
    "noon, time, to go together, lunch, classmate, noodle shop, younger brother, to eat";
  f2.vocabularyPinyin =
    "zhōngwǔ, shíhòu, yìqǐ qù, wǔcān, tóngxué, miàndiàn, dìdì, chī";
  const f3 = story.frames[2];
  f3.vocabularyTranslation =
    "to eat, full, afterwards, they, to return, building, Chinese, to study, to eat one's fill, class";
  const f4 = story.frames[3];
  f4.vocabularyTranslation =
    "afterwards, scenery, campus, happy, to take photos, after class";
  changes.push([story, "山上 scenes2-4 translations realigned; 一起去 pinyin completed"]);
}

// ── 捷運站在哪裡 pinyin typos (medium/hard) ──
{
  const story = byTitle("捷運站");
  for (const frame of story.frames) {
    for (const field of ["vocabularyPinyinMedium", "vocabularyPinyinHard"]) {
      if (!frame[field]) continue;
      frame[field] = frame[field]
        .replace("shíguò", "shíjiān")
        .replace("Chēnghàn", "Chénghàn")
        .replace("xiàng zǐ", "xiàngzi");
    }
  }
  changes.push([story, "捷運站 pinyin typos: shíguò→shíjiān, Chēnghàn→Chénghàn, xiàng zǐ→xiàngzi"]);
}

for (const [story, note] of changes) {
  const res = await fetch(`${BACKEND}/api/custom-stories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(story),
  });
  if (!res.ok) {
    console.error(`FAILED (${res.status}): ${note}`);
    process.exitCode = 1;
  } else {
    console.log(`ok: ${note}`);
  }
}
