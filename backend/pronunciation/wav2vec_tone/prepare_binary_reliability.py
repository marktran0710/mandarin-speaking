"""Binary usability review, with hidden duplicates to measure its reliability.

The three-level scale collapsed: identical 0 ms audio drew the same verdict as
round 2 only 16/44 times (36%). A criterion that unstable cannot choose an
aligner or a padding, and every earlier alignment number inherits that noise.

The likely cause is that GOOD / QUESTIONABLE / WRONG asks about boundary
aesthetics, which has no threshold a listener can hold steady across a session.
So the question changes to the one the pipeline actually needs: is this segment
usable for tone analysis? Tone lives in the voiced rhyme, so a clip with a
little extra silence is fine and a clip missing part of the rhyme is not --
that is a fact about the audio rather than a matter of taste.

This measures the new criterion before trusting it. Ten of the fifty trials are
the same audio presented twice under different ids, widely separated. If the
reviewer disagrees with themselves on those, no downstream comparison means
anything.

40 ms padding is used for presentation only, so that clipping does not
contaminate a test of the criterion. It is not adopted as a pipeline rule.

    python -m pronunciation.wav2vec_tone.prepare_binary_reliability
    python -m pronunciation.wav2vec_tone.serve_review --round binary
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
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"
ROUND2_ITEMS = DATA_DIR / "ompal_alignment_review_items_round2.csv"
ROUND2_REVIEW = DATA_DIR / "ompal_alignment_human_review_round2.csv"
TRIAL_DIR = DATA_DIR / "binary_trial_segments"
KEY_CSV = DATA_DIR / "binary_trial_key.csv"
PAGE = DATA_DIR / "review_binary.html"

SAMPLE_RATE = 16000
PRESENTATION_PADDING_MS = 40     # presentation only, not a pipeline decision
MIN_DUPLICATE_SEPARATION = 15


def load_audio(path: Path) -> np.ndarray:
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != SAMPLE_RATE:
        from math import gcd

        from scipy.signal import resample_poly

        divisor = gcd(int(rate), SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor,
                              int(rate) // divisor).astype(np.float32)
    return np.ascontiguousarray(audio, dtype=np.float32)


def prior_judgments() -> dict:
    """Round-2 verdicts, carried into the key for later comparison only."""
    if not (ROUND2_ITEMS.exists() and ROUND2_REVIEW.exists()):
        return {}
    items = {r["review_id"]: r
             for r in csv.DictReader(ROUND2_ITEMS.open(encoding="utf-8"))}
    prior = {}
    for row in csv.DictReader(ROUND2_REVIEW.open(encoding="utf-8")):
        item = items.get(row["review_id"])
        if item:
            prior[(item["utterance_id"], item["token_index"])] = \
                row["human_boundary_judgment"].strip().upper()
    return prior


def select(unique_count: int, seed: int, max_per_word: int):
    """Spread across automatic status, tone, duration, speaker and word.

    Deliberately includes automatic questionable and failed segments. This is a
    test of the criterion, not of the aligner, and a set of only clean cases
    would measure agreement on easy material and overstate the reliability.
    """
    rows = [r for r in csv.DictReader(PILOT_CSV.open(encoding="utf-8"))
            if r["segment_path"] and r["start_seconds"]]
    prior = prior_judgments()
    for row in rows:
        row["prior_judgment"] = prior.get(
            (row["utterance_id"], row["token_index"]), "")

    rng = np.random.default_rng(seed)
    rng.shuffle(rows)

    def bucket(row):
        value = float(row["duration_seconds"])
        return "short" if value < 0.14 else "mid" if value < 0.22 else "long"

    chosen = []
    statuses, tones, buckets, speakers, words = (
        Counter(), Counter(), Counter(), Counter(), Counter())
    while len(chosen) < unique_count:
        candidates = [r for r in rows
                      if r not in chosen and words[r["word"]] < max_per_word]
        if not candidates:
            break
        candidates.sort(key=lambda r: (
            statuses[r["alignment_status"]],
            tones[r["expected_tone"]],
            buckets[bucket(r)],
            speakers[r["speaker_id"]],
            words[r["word"]],
        ))
        pick = candidates[0]
        chosen.append(pick)
        statuses[pick["alignment_status"]] += 1
        tones[pick["expected_tone"]] += 1
        buckets[bucket(pick)] += 1
        speakers[pick["speaker_id"]] += 1
        words[pick["word"]] += 1
    return chosen


def pick_duplicates(chosen, count: int, seed: int):
    """Duplicate a spread of tokens, not the easy ones.

    Repeating only clean segments would measure agreement where agreement is
    cheap. The duplicates are spread over automatic status and tone so the
    reliability figure reflects the material the criterion will actually face.
    """
    rng = np.random.default_rng(seed + 1)
    by_status = defaultdict(list)
    for row in chosen:
        by_status[row["alignment_status"]].append(row)
    for items in by_status.values():
        rng.shuffle(items)

    picked, depth = [], 0
    order = sorted(by_status)
    while len(picked) < count and depth < 40:
        for status in order:
            if len(picked) >= count:
                break
            if len(by_status[status]) > depth:
                picked.append(by_status[status][depth])
        depth += 1
    return picked


def order_trials(unique_rows, duplicate_rows, seed: int):
    """Sequence 50 trials so each duplicate pair sits far apart."""
    rng = np.random.default_rng(seed + 2)
    entries = ([{"row": r, "repeat": 0} for r in unique_rows]
               + [{"row": r, "repeat": 1} for r in duplicate_rows])

    for _ in range(2000):
        rng.shuffle(entries)
        seen, ok = {}, True
        for position, entry in enumerate(entries):
            token = (entry["row"]["utterance_id"], entry["row"]["token_index"])
            if token in seen and position - seen[token] < MIN_DUPLICATE_SEPARATION:
                ok = False
                break
            seen[token] = position
        if ok:
            return entries
    raise RuntimeError("could not separate duplicates; lower the threshold")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unique", type=int, default=40)
    parser.add_argument("--duplicates", type=int, default=10)
    parser.add_argument("--max-per-word", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    import soundfile as sf

    chosen = select(args.unique, args.seed, args.max_per_word)
    duplicates = pick_duplicates(chosen, args.duplicates, args.seed)
    entries = order_trials(chosen, duplicates, args.seed)

    TRIAL_DIR.mkdir(parents=True, exist_ok=True)
    for old in TRIAL_DIR.glob("*.wav"):
        old.unlink()

    cache: dict[str, np.ndarray] = {}
    key_rows, page_items = [], []
    pad = PRESENTATION_PADDING_MS / 1000.0

    for number, entry in enumerate(entries, start=1):
        row = entry["row"]
        utterance_id = row["utterance_id"]
        if utterance_id not in cache:
            cache[utterance_id] = load_audio(
                OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav")
        audio = cache[utterance_id]

        begin = max(0, int(round((float(row["start_seconds"]) - pad) * SAMPLE_RATE)))
        finish = min(len(audio),
                     int(round((float(row["end_seconds"]) + pad) * SAMPLE_RATE)))
        segment = audio[begin:finish]

        trial_id = f"B{number:03d}"
        # A duplicate is written as its own file under its own trial id, so the
        # two presentations are indistinguishable from the page.
        sf.write(TRIAL_DIR / f"{trial_id}.wav", segment, SAMPLE_RATE)

        key_rows.append({
            "trial_id": trial_id,
            "token_id": f"{utterance_id}_{int(row['token_index']):02d}",
            "is_repeat": entry["repeat"],
            "alignment_status": row["alignment_status"],
            "flag_reason": row["alignment_note"],
            "prior_judgment": row["prior_judgment"],
            "majority_tone_correct": row["majority_tone_correct"],
            "word": row["word"],
            "expected_pinyin": row["expected_pinyin"],
            "expected_tone": row["expected_tone"],
            "speaker_id": row["speaker_id"],
            "utterance_id": utterance_id,
            "presentation_padding_ms": PRESENTATION_PADDING_MS,
            "duration_seconds": f"{len(segment) / SAMPLE_RATE:.4f}",
        })
        page_items.append({
            "trial_id": trial_id,
            "word": row["word"],
            "expected_pinyin": row["expected_pinyin"],
            "segment_path": f"binary_trial_segments/{trial_id}.wav",
            "utterance_path":
                f"../../../private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
        })

    with KEY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0].keys()))
        writer.writeheader()
        writer.writerows(key_rows)
    PAGE.write_text(render(page_items), encoding="utf-8")

    positions = defaultdict(list)
    for index, entry in enumerate(entries):
        positions[(entry["row"]["utterance_id"],
                   entry["row"]["token_index"])].append(index)
    gaps = [max(v) - min(v) for v in positions.values() if len(v) > 1]

    print(f"unique tokens    : {len(chosen)}")
    print(f"hidden duplicates: {len(duplicates)}  "
          f"(separation min {min(gaps)}, median {int(np.median(gaps))})")
    print(f"total trials     : {len(entries)}")
    print(f"automatic status : "
          + ", ".join(f"{k}={v}" for k, v in
                      sorted(Counter(r['alignment_status'] for r in chosen).items())))
    print(f"duplicated from  : "
          + ", ".join(f"{k}={v}" for k, v in
                      sorted(Counter(r['alignment_status'] for r in duplicates).items())))
    print(f"tones            : "
          + ", ".join(f"T{k}={v}" for k, v in
                      sorted(Counter(r['expected_tone'] for r in chosen).items())))
    print(f"speakers         : {len({r['speaker_id'] for r in chosen})}, "
          f"distinct words: {len({r['word'] for r in chosen})}")
    print(f"presentation     : {PRESENTATION_PADDING_MS} ms padding "
          f"(presentation only -- NOT adopted as pipeline rule)")
    print(f"\nkey (do NOT open before reviewing): {KEY_CSV}")
    print(f"page: {PAGE}")
    print("\n  python -m pronunciation.wav2vec_tone.serve_review --round binary")


def render(items) -> str:
    payload = ",\n".join(
        "{" + ", ".join(
            f'{k}: "{html.escape(str(item[k]), quote=True)}"'
            for k in ("trial_id", "word", "expected_pinyin",
                      "segment_path", "utterance_path")
        ) + "}"
        for item in items
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Segment usability — binary review</title>
<style>
 :root {{ --bg:#12100e; --card:#1c1917; --ink:#f5f0e8; --dim:#a8a29e;
          --gold:#c9a227; --ok:#4ade80; --no:#f87171; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--ink);
        font:15px/1.5 system-ui,-apple-system,"Noto Sans TC",sans-serif; }}
 .wrap {{ max-width:720px; margin:0 auto; padding:24px 20px 90px; }}
 h1 {{ font-size:17px; font-weight:600; margin:0 0 8px; }}
 .crit {{ background:#1c1917; border:1px solid #2c2825; border-radius:10px;
          padding:14px 16px; font-size:13px; color:var(--dim); margin-bottom:20px; }}
 .crit b {{ color:var(--ink); }}
 .bar {{ position:sticky; top:0; background:var(--bg); padding:12px 0;
         border-bottom:1px solid #2c2825; z-index:10; }}
 .track {{ height:5px; background:#2c2825; border-radius:3px; overflow:hidden; }}
 .fill {{ height:100%; background:var(--gold); width:0%; transition:width .2s; }}
 .card {{ background:var(--card); border:1px solid #2c2825; border-radius:12px;
          padding:20px; margin:14px 0; }}
 .hz {{ font-size:56px; line-height:1; font-family:"Noto Sans TC",serif; }}
 .meta {{ color:var(--dim); font-size:13px; margin-top:6px; }}
 .row {{ display:flex; gap:18px; align-items:center; flex-wrap:wrap; }}
 button {{ font:inherit; padding:9px 16px; border-radius:8px; cursor:pointer;
           border:1px solid #3f3a35; background:#262220; color:var(--ink); }}
 button:hover {{ border-color:var(--gold); }}
 .judge {{ display:flex; gap:10px; margin-top:14px; }}
 .judge button {{ flex:1; font-weight:600; padding:12px; }}
 .a.on {{ background:var(--ok); color:#06240f; border-color:var(--ok); }}
 .r.on {{ background:var(--no); color:#2b0606; border-color:var(--no); }}
 .done {{ border-color:var(--gold); }}
 .kbd {{ font-size:12px; color:var(--dim); margin-top:8px; }}
 .export {{ position:fixed; bottom:0; left:0; right:0; background:var(--card);
            border-top:1px solid #2c2825; padding:12px; text-align:center; }}
 .export button {{ background:var(--gold); color:#231a00; font-weight:700;
                   border-color:var(--gold); padding:11px 26px; }}
 @media (prefers-color-scheme: light) {{
   :root {{ --bg:#faf7f2; --card:#fff; --ink:#1c1917; --dim:#6b6560; }}
   .card, .bar, .export, .crit {{ border-color:#e7e0d6; background:#fff; }}
   button {{ background:#f2ede5; border-color:#ddd5c8; }}
 }}
</style></head><body><div class="wrap">
<h1>Does this segment support tone analysis?</h1>
<div class="crit">
 <b>ACCEPT</b> — the intended syllable is there, and the voiced part that tone
 analysis needs is sufficiently complete. A little extra silence or neighbouring
 context is fine.<br><br>
 <b>REJECT</b> — wrong syllable, or an important part of the target is cut off,
 or so much adjacent speech bleeds in that a tone measurement would be unsafe.
 <br><br>
 This is <b>not</b> about whether the boundary is tidy. Only whether the clip
 would give an honest tone measurement.
</div>
<div class="bar"><div class="track"><div class="fill" id="fill"></div></div>
<div class="meta" id="prog">0 judged</div></div>
<div id="list"></div></div>
<div class="export"><button onclick="save()">Download judgments CSV</button>
<span class="meta" id="status" style="margin-left:12px"></span></div>
<script>
const ITEMS = [
{payload}
];
const KEY = "ompal_binary_review";
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
  ["a","r"].forEach(c => card.querySelector("." + c).classList.remove("on"));
  card.querySelector("." + (j === "ACCEPT" ? "a" : "r")).classList.add("on");
  progress();
}}
function note(id, v) {{
  votes[id] = Object.assign({{}}, votes[id], {{ n: v }});
  localStorage.setItem(KEY, JSON.stringify(votes));
}}
function play(sel) {{ const a = document.querySelector(sel); a.currentTime = 0; a.play(); }}
function save() {{
  const skipped = ITEMS.filter(it => !(votes[it.trial_id] || {{}}).j);
  if (skipped.length && !confirm(
      skipped.length + " trial(s) have no judgment and will be MISSING:\\n\\n" +
      skipped.map(s => s.trial_id).join(", ") + "\\n\\nDownload anyway?")) return;
  let out = "trial_id,human_usability_judgment,human_note\\n";
  ITEMS.forEach(it => {{
    const v = votes[it.trial_id] || {{}};
    if (!v.j) return;
    out += `${{it.trial_id}},${{v.j}},"${{esc(v.n || "")}}"\\n`;
  }});
  const blob = new Blob([out], {{ type: "text/csv;charset=utf-8" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ompal_binary_human_review.csv";
  a.click();
  document.getElementById("status").textContent = "saved — put it in data/";
}}
document.getElementById("list").innerHTML = ITEMS.map(it => `
 <div class="card" id="c_${{it.trial_id}}">
  <div class="row">
   <div><div class="hz">${{it.word}}</div>
    <div class="meta">${{it.expected_pinyin}}</div></div>
   <div style="flex:1">
    <div class="row">
     <button onclick="play('#s_${{it.trial_id}}')">▶ clip</button>
     <button onclick="play('#u_${{it.trial_id}}')">▶ full utterance</button>
    </div>
    <div class="meta">${{it.trial_id}}</div>
   </div>
  </div>
  <audio id="s_${{it.trial_id}}" src="${{it.segment_path}}" preload="none"></audio>
  <audio id="u_${{it.trial_id}}" src="${{it.utterance_path}}" preload="none"></audio>
  <div class="judge">
   <button class="a" onclick="vote('${{it.trial_id}}','ACCEPT')">ACCEPT</button>
   <button class="r" onclick="vote('${{it.trial_id}}','REJECT')">REJECT</button>
  </div>
  <input type="text" placeholder="optional note" style="width:100%;margin-top:10px;
    padding:9px;border-radius:8px;border:1px solid #3f3a35;background:#171412;
    color:inherit" oninput="note('${{it.trial_id}}', this.value)">
  <div class="kbd">a = clip · s = utterance · 1 accept · 2 reject</div>
 </div>`).join("");
ITEMS.forEach(it => {{
  const v = votes[it.trial_id];
  if (!v) return;
  if (v.j) vote(it.trial_id, v.j);
  if (v.n) document.querySelector("#c_" + it.trial_id + " input").value = v.n;
}});
progress();
function current() {{
  let best = null, dist = 1e9;
  ITEMS.forEach(it => {{
    const r = document.getElementById("c_" + it.trial_id).getBoundingClientRect();
    const d = Math.abs(r.top + r.height / 2 - innerHeight / 2);
    if (d < dist) {{ dist = d; best = it; }}
  }});
  return best;
}}
addEventListener("keydown", e => {{
  if (e.target.tagName === "INPUT") return;
  const it = current(); if (!it) return;
  if (e.key === "a") play("#s_" + it.trial_id);
  if (e.key === "s") play("#u_" + it.trial_id);
  if (e.key === "1") vote(it.trial_id, "ACCEPT");
  if (e.key === "2") vote(it.trial_id, "REJECT");
}});
</script></body></html>
"""


if __name__ == "__main__":
    main()
