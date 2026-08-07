"""Blind padding diagnostic: is the aligner wrong, or just cropping too tight?

Round 2 put auto-good at 63.4% GOOD by ear, so the acceptance rule failed. But
"the boundary is in the wrong place" and "the boundary is right and the clip is
clipped" sound different and need different fixes, and the review so far cannot
tell them apart.

So the alignment is left exactly as it is. The same timestamps are re-cut with
0, 20, 40 and 60 ms of symmetric context, clipped to the utterance. Nothing is
re-aligned and no centre moves; the only thing that changes is how much air
surrounds the syllable.

Blinding matters more than usual here, because the four versions of a token are
nearly identical and expectation would fill the gap. Trials carry opaque ids,
segment files are named after the trial rather than the condition, the four
versions of a token are spread apart in the running order, and the page never
shows the padding, the earlier judgment, the automatic status, or the tone
label.

    python -m pronunciation.wav2vec_tone.prepare_padding_review
    python -m pronunciation.wav2vec_tone.serve_review --round padding
"""

from __future__ import annotations

import argparse
import csv
import html
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
ITEMS_ROUND2 = DATA_DIR / "ompal_alignment_review_items_round2.csv"
REVIEW_ROUND2 = DATA_DIR / "ompal_alignment_human_review_round2.csv"
TRIAL_DIR = DATA_DIR / "padding_trial_segments"
KEY_CSV = DATA_DIR / "padding_trial_key.csv"
PAGE = DATA_DIR / "review_padding.html"
SAMPLE_RATE = 16000

PADDING_MS = (0, 20, 40, 60)
MIN_SEPARATION = 12          # trials between two versions of the same token


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


def select_tokens(controls: int, seed: int):
    """All QUESTIONABLE and WRONG, plus a spread of GOOD controls.

    The controls are the half of the diagnostic that can fail: padding that
    rescues bad segments while spoiling good ones is not an improvement, and
    without controls that would be invisible.
    """
    items = {r["review_id"]: r
             for r in csv.DictReader(ITEMS_ROUND2.open(encoding="utf-8"))}
    judged = []
    for row in csv.DictReader(REVIEW_ROUND2.open(encoding="utf-8")):
        item = items.get(row["review_id"])
        verdict = row["human_boundary_judgment"].strip().upper()
        if item and verdict in ("GOOD", "QUESTIONABLE", "WRONG"):
            judged.append({**item, "original_judgment": verdict})

    chosen = [r for r in judged if r["original_judgment"] in ("QUESTIONABLE", "WRONG")]

    # Controls spread over tone and duration so they are not all easy cases.
    pool = [r for r in judged if r["original_judgment"] == "GOOD"]
    rng = np.random.default_rng(seed)
    rng.shuffle(pool)
    tones, durations = Counter(), Counter()

    def bucket(row):
        value = float(row["duration_seconds"])
        return "short" if value < 0.14 else "mid" if value < 0.22 else "long"

    picked = []
    while len(picked) < controls and pool:
        pool.sort(key=lambda r: (tones[r["expected_tone"]], durations[bucket(r)]))
        row = pool.pop(0)
        picked.append(row)
        tones[row["expected_tone"]] += 1
        durations[bucket(row)] += 1
    return chosen + picked


def build_trials(tokens, seed: int):
    """One trial per (token, padding), ordered so versions sit far apart.

    Random shuffling does not do this reliably -- with 44 tokens heard four
    times each, some pair always lands adjacent, and hearing the same syllable
    twice in a row invites comparison instead of an independent judgement.
    So each slot goes to whichever token has been waiting longest, which
    spreads the four versions almost maximally.
    """
    rng = np.random.default_rng(seed)
    remaining = {}
    for token in tokens:
        paddings = list(PADDING_MS)
        rng.shuffle(paddings)
        remaining[token["review_id"]] = {"token": token, "paddings": paddings}

    order, last_seen = [], {key: -10**6 for key in remaining}
    position = 0
    while any(entry["paddings"] for entry in remaining.values()):
        available = [k for k, e in remaining.items() if e["paddings"]]
        # Longest-waiting first; ties broken randomly so the order is not
        # itself a pattern the ear could latch onto.
        oldest = min(last_seen[k] for k in available)
        candidates = [k for k in available if last_seen[k] == oldest]
        key = candidates[int(rng.integers(len(candidates)))]
        entry = remaining[key]
        order.append({"token": entry["token"], "padding_ms": entry["paddings"].pop()})
        last_seen[key] = position
        position += 1
    return order


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", type=int, default=18)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    import soundfile as sf

    if not REVIEW_ROUND2.exists():
        sys.exit(f"Round-2 judgments not found at {REVIEW_ROUND2}")

    tokens = select_tokens(args.controls, args.seed)
    trials = build_trials(tokens, args.seed)
    TRIAL_DIR.mkdir(parents=True, exist_ok=True)

    cache: dict[str, np.ndarray] = {}
    key_rows, page_items = [], []
    clipped = 0

    for number, trial in enumerate(trials, start=1):
        token = trial["token"]
        utterance_id = token["utterance_id"]
        if utterance_id not in cache:
            cache[utterance_id] = load_audio(
                OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav")
        audio = cache[utterance_id]

        pad = trial["padding_ms"] / 1000.0
        start = float(token["start_seconds"]) - pad
        end = float(token["end_seconds"]) + pad
        # Clipped to the utterance: a padded window must never run past the
        # recording, and a token at the very edge simply gets less context.
        begin_sample = max(0, int(round(start * SAMPLE_RATE)))
        end_sample = min(len(audio), int(round(end * SAMPLE_RATE)))
        if begin_sample == 0 or end_sample == len(audio):
            clipped += 1
        segment = audio[begin_sample:end_sample]

        trial_id = f"P{number:03d}"
        # Named after the trial, never the condition: a filename like
        # "..._pad40" would give the answer away in the network panel.
        sf.write(TRIAL_DIR / f"{trial_id}.wav", segment, SAMPLE_RATE)

        key_rows.append({
            "trial_id": trial_id,
            "review_id": token["review_id"],
            "token_id": token["token_id"],
            "padding_ms": trial["padding_ms"],
            "original_judgment": token["original_judgment"],
            "alignment_status": token["alignment_status"],
            "majority_tone_correct": token["majority_tone_correct"],
            "word": token["word"],
            "expected_pinyin": token["expected_pinyin"],
            "expected_tone": token["expected_tone"],
            "speaker_id": token["speaker_id"],
            "utterance_id": utterance_id,
            "orig_start": token["start_seconds"],
            "orig_end": token["end_seconds"],
            "padded_start": f"{begin_sample / SAMPLE_RATE:.4f}",
            "padded_end": f"{end_sample / SAMPLE_RATE:.4f}",
            "duration_seconds": f"{len(segment) / SAMPLE_RATE:.4f}",
        })
        page_items.append({
            "trial_id": trial_id,
            "word": token["word"],
            "expected_pinyin": token["expected_pinyin"],
            "segment_path": f"padding_trial_segments/{trial_id}.wav",
            "utterance_path":
                f"../../../private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
        })

    with KEY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0].keys()))
        writer.writeheader()
        writer.writerows(key_rows)
    PAGE.write_text(render(page_items), encoding="utf-8")

    by_original = Counter(t["original_judgment"] for t in tokens)
    print(f"tokens selected : {len(tokens)}  "
          + ", ".join(f"{k}={v}" for k, v in sorted(by_original.items())))
    print(f"padding levels  : {', '.join(str(p) + 'ms' for p in PADDING_MS)}")
    print(f"trials          : {len(trials)}  "
          f"(~{len(trials) * 6 / 60:.0f} min at 6 s each)")
    print(f"edge-clipped    : {clipped} trials hit the utterance boundary")
    print(f"tones           : "
          + ", ".join(f"T{t}={c}" for t, c in
                      sorted(Counter(t['expected_tone'] for t in tokens).items())))
    print(f"speakers        : {len({t['speaker_id'] for t in tokens})}")
    print(f"\nkey (do NOT open before reviewing): {KEY_CSV}")
    print(f"page: {PAGE}")
    print("\n  python -m pronunciation.wav2vec_tone.serve_review --round padding")


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
<title>Padding diagnostic — blind review</title>
<style>
 :root {{ --bg:#12100e; --card:#1c1917; --ink:#f5f0e8; --dim:#a8a29e;
          --gold:#c9a227; --good:#4ade80; --warn:#fbbf24; --bad:#f87171; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--ink);
        font:15px/1.5 system-ui,-apple-system,"Noto Sans TC",sans-serif; }}
 .wrap {{ max-width:720px; margin:0 auto; padding:24px 20px 90px; }}
 h1 {{ font-size:17px; font-weight:600; margin:0 0 4px; }}
 .sub {{ color:var(--dim); font-size:13px; margin-bottom:20px; }}
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
 .judge button {{ flex:1; min-width:120px; font-weight:600; }}
 .g.on {{ background:var(--good); color:#06240f; border-color:var(--good); }}
 .q.on {{ background:var(--warn); color:#2b1d00; border-color:var(--warn); }}
 .w.on {{ background:var(--bad);  color:#2b0606; border-color:var(--bad); }}
 .done {{ border-color:var(--gold); }}
 .kbd {{ font-size:12px; color:var(--dim); margin-top:8px; }}
 .export {{ position:fixed; bottom:0; left:0; right:0; background:var(--card);
            border-top:1px solid #2c2825; padding:12px; text-align:center; }}
 .export button {{ background:var(--gold); color:#231a00; font-weight:700;
                   border-color:var(--gold); padding:11px 26px; }}
 @media (prefers-color-scheme: light) {{
   :root {{ --bg:#faf7f2; --card:#fff; --ink:#1c1917; --dim:#6b6560; }}
   .card, .bar, .export {{ border-color:#e7e0d6; }}
   button {{ background:#f2ede5; border-color:#ddd5c8; }}
 }}
</style></head><body><div class="wrap">
<h1>Padding diagnostic — blind</h1>
<div class="sub">Same question as before: does the clip contain the intended
syllable, cleanly? You will hear each token several times in versions that
differ only in how much surrounding audio is included — which version is which
is hidden, and so is every earlier judgment. Judge each clip on its own.</div>
<div class="bar"><div class="track"><div class="fill" id="fill"></div></div>
<div class="meta" id="prog">0 judged</div></div>
<div id="list"></div></div>
<div class="export"><button onclick="save()">Download judgments CSV</button>
<span class="meta" id="status" style="margin-left:12px"></span></div>
<script>
const ITEMS = [
{payload}
];
const KEY = "ompal_padding_review";
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
  const skipped = ITEMS.filter(it => !(votes[it.trial_id] || {{}}).j);
  if (skipped.length && !confirm(
      skipped.length + " trial(s) have no judgment and will be MISSING:\\n\\n" +
      skipped.map(s => s.trial_id).join(", ") + "\\n\\nDownload anyway?")) return;
  let out = "trial_id,human_boundary_judgment,human_note\\n";
  ITEMS.forEach(it => {{
    const v = votes[it.trial_id] || {{}};
    if (!v.j) return;
    out += `${{it.trial_id}},${{v.j}},"${{esc(v.n || "")}}"\\n`;
  }});
  const blob = new Blob([out], {{ type: "text/csv;charset=utf-8" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ompal_padding_human_review.csv";
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
   <button class="g" onclick="vote('${{it.trial_id}}','GOOD')">GOOD</button>
   <button class="q" onclick="vote('${{it.trial_id}}','QUESTIONABLE')">QUESTIONABLE</button>
   <button class="w" onclick="vote('${{it.trial_id}}','WRONG')">WRONG</button>
  </div>
  <input type="text" placeholder="optional note" style="width:100%;margin-top:10px;
    padding:9px;border-radius:8px;border:1px solid #3f3a35;background:#171412;
    color:inherit" oninput="note('${{it.trial_id}}', this.value)">
  <div class="kbd">a = clip · s = utterance · 1 good · 2 questionable · 3 wrong</div>
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
  if (e.key === "1") vote(it.trial_id, "GOOD");
  if (e.key === "2") vote(it.trial_id, "QUESTIONABLE");
  if (e.key === "3") vote(it.trial_id, "WRONG");
}});
</script></body></html>
"""


if __name__ == "__main__":
    main()
