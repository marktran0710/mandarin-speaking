// Semantic-review cleanup (2026-07-23, part 2): the AI-generated English
// distractors frequently include words that are themselves valid
// translations of the prompt (好吃 "delicious" offering "tasty",
// 兩點半 "two thirty" offering "half past two") — a second correct answer
// at tier 2+, where AI distractors lead. Removal-only: each listed string
// is deleted from that word's distractor pool wherever it appears; the
// quiz builders pad shortfalls from story words / generic filler.
// Also removes the nonsense synonym candidate 他們們.
// Run: node scripts/fix-quiz-distractors.mjs
const BACKEND = "http://127.0.0.1:8000";

// word → distractor strings that read as correct answers for that word's
// gloss (case-insensitive match).
const REMOVE = {
  好吃: ["tasty", "appetizing", "savory", "yummy", "flavorful", "scrumptious", "delectable"],
  好: ["well", "fine", "excellent", "great", "nice", "lovely", "pleasant"],
  太好了: ["excellent", "wonderful", "fantastic", "marvelous", "superb", "splendid"],
  找: ["search", "discover", "locate", "detect", "track down"],
  出去: ["leave", "depart", "escape", "head out", "venture out"],
  沒事: ["no problem", "nothing", "alright", "all right", "no issue"],
  一起: ["as one", "united", "as a team", "in unison", "hand in hand"],
  雞排: ["chicken steak", "fried chicken"],
  捷運站: ["train station", "subway stop", "metro station", "subway", "subway terminal"],
  六點: ["six pm"],
  兩點半: ["half past two"],
  咖啡廳: ["coffee shop"],
  知道: ["to realize", "to recognize"],
  有空: ["to be free", "to be available"],
  下午茶: ["high tea"],
  要: ["to need", "to require"],
  想: ["to wish", "to hope"],
  很多: ["numerous", "a large number", "countless", "plenty", "several"],
  種: ["type", "style", "category", "classification", "genre", "class"],
  有: ["some", "any", "available", "present", "existent", "own", "available now"],
  我: ["me", "myself", "myself alone", "one's own"],
  我們: ["us", "our", "ourselves", "our group"],
  你: ["thee", "thy"],
  見: ["meet", "greet", "encounter", "meet up", "run into", "salute"],
  晚上: ["nighttime", "evening time", "nightfall"],
  做: ["to make", "make", "undertake"],
  家: ["household", "residence", "hometown", "abode"],
  冰淇淋: ["gelato", "frozen dessert", "cold dessert", "frozen treat", "sweet ice"],
  聽音樂: ["to enjoy music"],
  珍珠奶茶: ["milk tea", "bubble drink", "pearl tea", "milk tea drink", "pearl tea beverage", "bubble milk tea"],
  好啊: ["not bad", "fair enough"],
  喝: ["to sip", "to gulp", "to taste", "to guzzle", "to swallow"],
  不遠: ["somewhat near", "extremely close"],
  很近: ["moderately close", "extremely close"],
};

const stories = await fetch(`${BACKEND}/api/custom-stories`).then((r) => r.json());
let removedCount = 0;

for (const story of stories) {
  let changed = false;
  for (const frame of story.frames) {
    const words = (frame.vocabulary || "").split(",").map((w) => w.trim()).filter(Boolean);
    if (frame.vocabularyDistractors) {
      try {
        const dis = JSON.parse(frame.vocabularyDistractors);
        words.forEach((word, i) => {
          const remove = REMOVE[word];
          if (!remove || !Array.isArray(dis[i])) return;
          const before = dis[i].length;
          dis[i] = dis[i].filter((d) => !remove.includes(d.trim().toLowerCase()));
          if (dis[i].length !== before) {
            removedCount += before - dis[i].length;
            changed = true;
          }
        });
        frame.vocabularyDistractors = JSON.stringify(dis);
      } catch {}
    }
    if (frame.vocabularySynonym) {
      try {
        const syn = JSON.parse(frame.vocabularySynonym);
        words.forEach((word, i) => {
          if (!Array.isArray(syn[i])) return;
          const before = syn[i].length;
          // 他們們 is not a word — AI garbage that would be shown as the
          // CORRECT answer of a synonym question.
          syn[i] = syn[i].filter((c) => c.synonym !== "他們們");
          if (syn[i].length !== before) changed = true;
        });
        frame.vocabularySynonym = JSON.stringify(syn);
      } catch {}
    }
  }
  if (changed) {
    const res = await fetch(`${BACKEND}/api/custom-stories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(story),
    });
    console.log(`${res.ok ? "ok" : `FAILED ${res.status}`}: ${story.title}`);
    if (!res.ok) process.exitCode = 1;
  }
}
console.log(`removed ${removedCount} second-correct distractors`);
