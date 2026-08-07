"""Build a listening-review set and a local page for judging alignment by ear.

The acoustic check was a proxy and has a known blind spot: it called 是/四/字
misaligned because sibilant onsets with the apical vowel measure low voicing,
which may say more about pitch tracking than about the boundary. Only listening
settles that, so this prepares the set and the interface and stops.

The review deliberately hides `majority_tone_correct`. The question is whether
the clip contains the intended syllable, not whether the learner said it well;
seeing the tone verdict first would make it hard to unsee.

    python -m pronunciation.wav2vec_tone.prepare_human_review
    python -m pronunciation.wav2vec_tone.serve_review
"""

from __future__ import annotations

import argparse
import csv
import html
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"
ITEMS_CSV = DATA_DIR / "ompal_alignment_review_items.csv"
REVIEW_HTML = DATA_DIR / "review.html"

# The characters the acoustic proxy disagreed on, or failed most often.
MUST_INCLUDE = ("是", "四", "字", "一", "去", "花")
PER_MUST_INCLUDE = 3


def utterance_relative(utterance_id: str) -> str:
    """From data/ up to backend/, then into the read-only corpus."""
    return f"../../../private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav"


def select(rows, wanted: int, seed: int):
    """Stratify over tone x label x status, after forcing the flagged characters."""
    available = [r for r in rows if r["segment_path"] and r["start_seconds"]]
    rng = np.random.default_rng(seed)

    chosen, seen = [], set()

    def key(row):
        return (row["utterance_id"], row["token_index"])

    # 1. The characters under suspicion, spread across statuses.
    for character in MUST_INCLUDE:
        pool = [r for r in available if r["word"] == character]
        by_status = defaultdict(list)
        for row in pool:
            by_status[row["alignment_status"]].append(row)
        for items in by_status.values():
            rng.shuffle(items)
        # One from each status before taking a second of any, so a flagged
        # character is heard in both its good and its suspect form.
        taken, depth = 0, 0
        while taken < PER_MUST_INCLUDE and depth < 4:
            for status in ("failed", "questionable", "good"):
                pool_at_depth = by_status.get(status, [])
                if taken >= PER_MUST_INCLUDE or len(pool_at_depth) <= depth:
                    continue
                row = pool_at_depth[depth]
                if key(row) not in seen:
                    chosen.append(row)
                    seen.add(key(row))
                    taken += 1
            depth += 1

    # 2. Fill the rest across tone x human label x status, so the set spans
    #    both automatic verdicts and both outcomes without revealing either.
    buckets = defaultdict(list)
    for row in available:
        if key(row) in seen:
            continue
        buckets[(row["expected_tone"], row["majority_tone_correct"],
                 row["alignment_status"])].append(row)
    for items in buckets.values():
        rng.shuffle(items)
        items.sort(key=lambda r: r["speaker_id"])

    # Fill by whichever tone is furthest behind. The must-include characters
    # are almost all T1/T4 (一 花 是 四 字), so filling in bucket order would
    # leave T2 and T3 badly under-sampled.
    cursor = {bucket: 0 for bucket in buckets}
    while len(chosen) < wanted:
        tone_counts = Counter(r["expected_tone"] for r in chosen)
        candidates = [b for b in buckets if cursor[b] < len(buckets[b])]
        if not candidates:
            break
        label_counts = Counter(r["majority_tone_correct"] for r in chosen)
        status_counts = Counter(r["alignment_status"] for r in chosen)
        # Tone first, then the human label, then automatic status. The label is
        # balanced even though the reviewer never sees it, so the reviewed set
        # is not accidentally all well-pronounced tokens.
        candidates.sort(key=lambda b: (tone_counts.get(b[0], 0),
                                       label_counts.get(b[1], 0),
                                       status_counts.get(b[2], 0)))
        bucket = candidates[0]
        row = buckets[bucket][cursor[bucket]]
        cursor[bucket] += 1
        if key(row) not in seen:
            chosen.append(row)
            seen.add(key(row))

    # Shuffle presentation order so status is not guessable from position.
    rng.shuffle(chosen)
    return chosen[:wanted]


def build_items(chosen) -> list[dict]:
    items = []
    for number, row in enumerate(chosen, start=1):
        items.append({
            "review_id": f"R{number:03d}",
            "token_id": f"{row['utterance_id']}_{int(row['token_index']):02d}",
            "segment_path": row["segment_path"],
            "utterance_path": utterance_relative(row["utterance_id"]),
            "speaker_id": row["speaker_id"],
            "utterance_id": row["utterance_id"],
            "token_index": row["token_index"],
            "word": row["word"],
            "expected_pinyin": row["expected_pinyin"],
            "expected_tone": row["expected_tone"],
            "start_seconds": row["start_seconds"],
            "end_seconds": row["end_seconds"],
            "duration_seconds": row["duration_seconds"],
            "alignment_score": row["alignment_score"],
            "alignment_status": row["alignment_status"],
            "flag_reason": row["alignment_note"],
            # Carried in the item file for later joins, never rendered.
            "majority_tone_correct": row["majority_tone_correct"],
        })
    return items


def render(items) -> str:
    """A single self-contained page. No network, no build step."""
    payload = ",\n".join(
        "{" + ", ".join(
            f'{k}: "{html.escape(str(item[k]), quote=True)}"'
            for k in ("review_id", "token_id", "segment_path", "utterance_path",
                      "speaker_id", "utterance_id", "word", "expected_pinyin",
                      "expected_tone", "start_seconds", "end_seconds",
                      "duration_seconds", "alignment_score", "alignment_status",
                      "flag_reason")
        ) + "}"
        for item in items
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>OMPAL alignment — listening review</title>
<style>
 :root {{ --bg:#12100e; --card:#1c1917; --ink:#f5f0e8; --dim:#a8a29e;
          --gold:#c9a227; --good:#4ade80; --warn:#fbbf24; --bad:#f87171; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--ink);
        font:15px/1.5 system-ui,-apple-system,"Noto Sans TC",sans-serif; }}
 .wrap {{ max-width:760px; margin:0 auto; padding:24px 20px 80px; }}
 h1 {{ font-size:17px; font-weight:600; margin:0 0 4px; }}
 .sub {{ color:var(--dim); font-size:13px; margin-bottom:20px; }}
 .bar {{ position:sticky; top:0; background:var(--bg); padding:12px 0;
         border-bottom:1px solid #2c2825; z-index:10; }}
 .track {{ height:5px; background:#2c2825; border-radius:3px; overflow:hidden; }}
 .fill {{ height:100%; background:var(--gold); width:0%; transition:width .2s; }}
 .card {{ background:var(--card); border:1px solid #2c2825; border-radius:12px;
          padding:22px; margin:16px 0; }}
 .hz {{ font-size:64px; line-height:1; font-family:"Noto Sans TC",serif; }}
 .meta {{ color:var(--dim); font-size:13px; margin-top:6px; }}
 .row {{ display:flex; gap:20px; align-items:center; flex-wrap:wrap; }}
 button {{ font:inherit; padding:9px 16px; border-radius:8px; cursor:pointer;
           border:1px solid #3f3a35; background:#262220; color:var(--ink); }}
 button:hover {{ border-color:var(--gold); }}
 .judge button {{ flex:1; min-width:130px; font-weight:600; }}
 .judge {{ display:flex; gap:10px; margin-top:16px; }}
 .g.on {{ background:var(--good); color:#06240f; border-color:var(--good); }}
 .q.on {{ background:var(--warn); color:#2b1d00; border-color:var(--warn); }}
 .w.on {{ background:var(--bad);  color:#2b0606; border-color:var(--bad); }}
 input[type=text] {{ width:100%; margin-top:10px; padding:9px; border-radius:8px;
                     border:1px solid #3f3a35; background:#171412; color:var(--ink); }}
 .tag {{ font-size:11px; padding:2px 8px; border-radius:99px;
         border:1px solid #3f3a35; color:var(--dim); }}
 .done {{ border-color:var(--gold); }}
 .kbd {{ font-size:12px; color:var(--dim); margin-top:10px; }}
 .export {{ position:fixed; bottom:0; left:0; right:0; background:var(--card);
            border-top:1px solid #2c2825; padding:12px; text-align:center; }}
 .export button {{ background:var(--gold); color:#231a00; font-weight:700;
                   border-color:var(--gold); padding:11px 26px; }}
 @media (prefers-color-scheme: light) {{
   :root {{ --bg:#faf7f2; --card:#fff; --ink:#1c1917; --dim:#6b6560; }}
   .card, .bar, .export {{ border-color:#e7e0d6; }}
   button {{ background:#f2ede5; border-color:#ddd5c8; }}
   input[type=text] {{ background:#fff; border-color:#ddd5c8; }}
 }}
</style></head><body><div class="wrap">
<h1>OMPAL forced-alignment — listening review</h1>
<div class="sub">Judge <b>only</b> whether the clip contains the intended syllable.
Not whether the learner's tone was right — that label is deliberately hidden.</div>
<div class="bar"><div class="track"><div class="fill" id="fill"></div></div>
<div class="meta" id="prog">0 judged</div></div>
<div id="list"></div>
</div>
<div class="export"><button onclick="save()">Download judgments CSV</button>
<span class="meta" id="status" style="margin-left:12px"></span></div>
<script>
const ITEMS = [
{payload}
];
const KEY = "ompal_align_review";
let votes = JSON.parse(localStorage.getItem(KEY) || "{{}}");

function esc(s) {{ return String(s).replace(/"/g, '""'); }}

function progress() {{
  const n = Object.keys(votes).filter(k => votes[k] && votes[k].j).length;
  document.getElementById("prog").textContent = n + " of " + ITEMS.length + " judged";
  document.getElementById("fill").style.width = (100 * n / ITEMS.length) + "%";
}}

function vote(id, j) {{
  votes[id] = Object.assign({{}}, votes[id], {{ j: j }});
  localStorage.setItem(KEY, JSON.stringify(votes));
  const card = document.getElementById("c_" + id);
  card.classList.add("done");
  ["g","q","w"].forEach(c => card.querySelector("." + c).classList.remove("on"));
  card.querySelector("." + {{GOOD:"g", QUESTIONABLE:"q", WRONG:"w"}}[j]).classList.add("on");
  progress();
}}

function note(id, v) {{
  votes[id] = Object.assign({{}}, votes[id], {{ n: v }});
  localStorage.setItem(KEY, JSON.stringify(votes));
}}

function play(sel) {{ const a = document.querySelector(sel); a.currentTime = 0; a.play(); }}

function save() {{
  let out = "review_id,token_id,human_boundary_judgment,human_note\\n";
  ITEMS.forEach(it => {{
    const v = votes[it.review_id] || {{}};
    if (!v.j) return;
    out += `${{it.review_id}},${{it.token_id}},${{v.j}},"${{esc(v.n || "")}}"\\n`;
  }});
  const blob = new Blob([out], {{ type: "text/csv;charset=utf-8" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ompal_alignment_human_review.csv";
  a.click();
  document.getElementById("status").textContent =
    "saved — put it in data/ then run analyze_human_review.py";
}}

document.getElementById("list").innerHTML = ITEMS.map((it, i) => `
 <div class="card" id="c_${{it.review_id}}">
  <div class="row">
   <div><div class="hz">${{it.word}}</div>
    <div class="meta">${{it.expected_pinyin}} &nbsp;·&nbsp; tone ${{it.expected_tone}}</div></div>
   <div style="flex:1">
    <div class="row">
     <button onclick="play('#s_${{it.review_id}}')">▶ segment</button>
     <button onclick="play('#u_${{it.review_id}}')">▶ full utterance</button>
     <span class="tag">${{it.alignment_status}}${{it.flag_reason ? " · " + it.flag_reason : ""}}</span>
    </div>
    <div class="meta">${{it.review_id}} &nbsp;·&nbsp; spk ${{it.speaker_id}} &nbsp;·&nbsp;
     ${{it.duration_seconds}}s &nbsp;·&nbsp; ${{it.start_seconds}}–${{it.end_seconds}}s
     &nbsp;·&nbsp; score ${{it.alignment_score}}</div>
   </div>
  </div>
  <audio id="s_${{it.review_id}}" src="${{it.segment_path}}" preload="none"></audio>
  <audio id="u_${{it.review_id}}" src="${{it.utterance_path}}" preload="none"></audio>
  <div class="judge">
   <button class="g" onclick="vote('${{it.review_id}}','GOOD')">GOOD</button>
   <button class="q" onclick="vote('${{it.review_id}}','QUESTIONABLE')">QUESTIONABLE</button>
   <button class="w" onclick="vote('${{it.review_id}}','WRONG')">WRONG</button>
  </div>
  <input type="text" placeholder="optional note"
     oninput="note('${{it.review_id}}', this.value)">
  <div class="kbd">keys: <b>a</b> play segment · <b>s</b> play utterance ·
   <b>1</b> good · <b>2</b> questionable · <b>3</b> wrong</div>
 </div>`).join("");

// Restore any judgments from a previous sitting.
ITEMS.forEach(it => {{
  const v = votes[it.review_id];
  if (!v) return;
  if (v.j) vote(it.review_id, v.j);
  if (v.n) document.querySelector("#c_" + it.review_id + " input").value = v.n;
}});
progress();

// Keyboard driving: whichever card is nearest the middle of the screen.
function current() {{
  let best = null, dist = 1e9;
  ITEMS.forEach(it => {{
    const r = document.getElementById("c_" + it.review_id).getBoundingClientRect();
    const d = Math.abs(r.top + r.height / 2 - innerHeight / 2);
    if (d < dist) {{ dist = d; best = it; }}
  }});
  return best;
}}
addEventListener("keydown", e => {{
  if (e.target.tagName === "INPUT") return;
  const it = current(); if (!it) return;
  if (e.key === "a") play("#s_" + it.review_id);
  if (e.key === "s") play("#u_" + it.review_id);
  if (e.key === "1") vote(it.review_id, "GOOD");
  if (e.key === "2") vote(it.review_id, "QUESTIONABLE");
  if (e.key === "3") vote(it.review_id, "WRONG");
}});
</script></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=46)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rows = list(csv.DictReader(PILOT_CSV.open(encoding="utf-8")))
    chosen = select(rows, args.count, args.seed)
    items = build_items(chosen)

    with ITEMS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)
    REVIEW_HTML.write_text(render(items), encoding="utf-8")

    print(f"review items : {len(items)}")
    print(f"  statuses   : {dict(Counter(i['alignment_status'] for i in items))}")
    print(f"  tones      : {dict(sorted(Counter(i['expected_tone'] for i in items).items()))}")
    print(f"  speakers   : {len({i['speaker_id'] for i in items})}")
    print(f"  hidden human label balance (not shown in UI): "
          f"{dict(Counter(i['majority_tone_correct'] for i in items))}")
    flagged = Counter(i["word"] for i in items if i["word"] in MUST_INCLUDE)
    print(f"  flagged characters included: "
          + ", ".join(f"{c}={flagged.get(c, 0)}" for c in MUST_INCLUDE))
    print(f"\nitems csv : {ITEMS_CSV}")
    print(f"page      : {REVIEW_HTML}")
    print("\nStart the reviewer with:")
    print("  cd backend && python -m pronunciation.wav2vec_tone.serve_review")


if __name__ == "__main__":
    main()
