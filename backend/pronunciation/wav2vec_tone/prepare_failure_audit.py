"""Blinded failure-mode audit of rejected original-boundary segments.

Existing features top out at 88% precision, and six rejected tokens are long,
well-scored and healthily voiced -- invisible to every indicator available. So
before engineering another feature, find out what is actually wrong with the
audio.

All 24 REJECT tokens, plus ~24 ACCEPT controls matched on duration, tone,
speaker and alignment score. The controls are the point: if a suspected defect
turns up just as often in segments that were judged usable, it is not what
drives rejection, and a QC feature built on it would fire on good data.

Presented blind, and the earlier verdict is hidden, so the ACCEPT/REJECT answer
is also a second measurement of the criterion's repeatability on exactly the
material where it matters most.

    python -m pronunciation.wav2vec_tone.prepare_failure_audit
    python -m pronunciation.wav2vec_tone.serve_review --round audit
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

from pronunciation.wav2vec_tone.segment_qc_diagnostic import collect

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"
TRIAL_DIR = DATA_DIR / "audit_trial_segments"
KEY_CSV = DATA_DIR / "audit_trial_key.csv"
PAGE = DATA_DIR / "review_audit.html"
SAMPLE_RATE = 16000

REASONS = (
    ("WRONG_TOKEN", "The segment is mostly a different syllable"),
    ("TRUNCATED_ONSET", "The start of the intended syllable is materially cut"),
    ("TRUNCATED_RHYME", "The vowel/voiced part tone analysis needs is cut"),
    ("ADJACENT_SPEECH", "Too much neighbouring speech contaminates it"),
    ("TOO_SHORT_OR_INCOMPLETE", "Token is present but too incomplete to analyse"),
    ("LOW_AUDIO_QUALITY", "Noise, clipping or audibility prevents reliable use"),
    ("OTHER", "Something else — please note it"),
)


def match_controls(rejects, accepts):
    """Greedy nearest-neighbour matching, one control per reject.

    Same tone first, then close duration and alignment score, then a nudge
    toward the same speaker. Matching matters here: rejected tokens are much
    shorter on average, so unmatched controls would differ on the very
    dimension under investigation and any comparison would be about duration
    rather than about failure modes.
    """
    remaining = list(accepts)
    pairs = []
    for reject in sorted(rejects, key=lambda r: r["duration_seconds"]):
        if not remaining:
            break
        def distance(candidate):
            tone_penalty = 0.0 if candidate["expected_tone"] == reject["expected_tone"] else 1.5
            speaker_penalty = 0.0 if candidate["speaker_id"] == reject["speaker_id"] else 0.4
            duration_gap = abs(candidate["duration_seconds"] - reject["duration_seconds"]) / 0.08
            score_gap = abs(candidate["alignment_score"] - reject["alignment_score"]) / 0.20
            return tone_penalty + speaker_penalty + duration_gap + score_gap
        best = min(remaining, key=distance)
        remaining.remove(best)
        pairs.append((reject, best))
    return pairs


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()

    import soundfile as sf

    rows, _ = collect()
    detail = {}
    for row in csv.DictReader(PILOT_CSV.open(encoding="utf-8")):
        if row["start_seconds"]:
            detail[f"{row['utterance_id']}_{int(row['token_index']):02d}"] = row
    for row in rows:
        source = detail[row["token_id"]]
        row["expected_tone"] = source["expected_tone"]
        row["speaker_id"] = source["speaker_id"]
        row["word"] = source["word"]
        row["expected_pinyin"] = source["expected_pinyin"]
        row["utterance_id"] = source["utterance_id"]
        row["start_seconds"] = float(source["start_seconds"])
        row["end_seconds"] = float(source["end_seconds"])

    rejects = [r for r in rows if r["verdict"] == "REJECT"]
    accepts = [r for r in rows if r["verdict"] == "ACCEPT"]
    pairs = match_controls(rejects, accepts)

    selected = []
    for reject, control in pairs:
        selected.append({**reject, "role": "reject"})
        selected.append({**control, "role": "control"})

    rng = np.random.default_rng(args.seed)
    rng.shuffle(selected)

    TRIAL_DIR.mkdir(parents=True, exist_ok=True)
    for old in TRIAL_DIR.glob("*.wav"):
        old.unlink()

    cache: dict[str, np.ndarray] = {}
    key_rows, page_items = [], []
    for number, item in enumerate(selected, start=1):
        utterance_id = item["utterance_id"]
        if utterance_id not in cache:
            cache[utterance_id] = load_audio(
                OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav")
        audio = cache[utterance_id]
        begin = max(0, int(round(item["start_seconds"] * SAMPLE_RATE)))
        finish = min(len(audio), int(round(item["end_seconds"] * SAMPLE_RATE)))
        segment = audio[begin:finish]

        trial_id = f"A{number:03d}"
        sf.write(TRIAL_DIR / f"{trial_id}.wav", segment, SAMPLE_RATE)

        key_rows.append({
            "trial_id": trial_id,
            "token_id": item["token_id"],
            "role": item["role"],
            "previous_verdict": item["verdict"],
            "word": item["word"],
            "expected_pinyin": item["expected_pinyin"],
            "expected_tone": item["expected_tone"],
            "speaker_id": item["speaker_id"],
            "utterance_id": utterance_id,
            "duration_seconds": f"{item['duration_seconds']:.4f}",
            "alignment_score": f"{item['alignment_score']:.4f}",
            "voiced_proportion": f"{item['voiced_proportion']:.3f}",
            "alignment_status": item["alignment_status"],
        })
        page_items.append({
            "trial_id": trial_id,
            "word": item["word"],
            "expected_pinyin": item["expected_pinyin"],
            "segment_path": f"audit_trial_segments/{trial_id}.wav",
            "utterance_path":
                f"../../../private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
        })

    with KEY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0].keys()))
        writer.writeheader()
        writer.writerows(key_rows)
    PAGE.write_text(render(page_items), encoding="utf-8")

    reject_durations = [r["duration_seconds"] for r, _ in pairs]
    control_durations = [c["duration_seconds"] for _, c in pairs]
    reject_scores = [r["alignment_score"] for r, _ in pairs]
    control_scores = [c["alignment_score"] for _, c in pairs]
    same_tone = sum(1 for r, c in pairs if r["expected_tone"] == c["expected_tone"])
    same_speaker = sum(1 for r, c in pairs if r["speaker_id"] == c["speaker_id"])

    print(f"REJECT tokens        : {len(rejects)}")
    print(f"matched controls     : {len(pairs)}")
    print(f"total trials         : {len(selected)}")
    # Per-pair gaps, not median-vs-median: rejects cluster at 0.08-0.10 s with
    # a long tail, so comparing the two medians overstates the mismatch while
    # each control actually tracks its own partner closely.
    duration_gaps = np.abs(np.asarray(reject_durations) - np.asarray(control_durations))
    score_gaps = np.abs(np.asarray(reject_scores) - np.asarray(control_scores))
    print(f"match quality (per pair):")
    print(f"  |duration gap|     : median {np.median(duration_gaps):.3f}s  "
          f"p75 {np.percentile(duration_gaps, 75):.3f}s  "
          f"max {duration_gaps.max():.3f}s")
    print(f"  |score gap|        : median {np.median(score_gaps):.3f}  "
          f"max {score_gaps.max():.3f}")
    print(f"  group medians      : duration reject {np.median(reject_durations):.3f}s "
          f"vs control {np.median(control_durations):.3f}s "
          f"(only {sum(1 for a in accepts if a['duration_seconds'] <= 0.15)} "
          f"ACCEPT tokens are <=0.15s, so the short end is pool-limited)")
    print(f"  same tone          : {same_tone}/{len(pairs)}")
    print(f"  same speaker       : {same_speaker}/{len(pairs)}")
    print(f"  tones covered      : "
          + ", ".join(f"T{k}={v}" for k, v in
                      sorted(Counter(i['expected_tone'] for i in selected).items())))
    print(f"\nkey (do NOT open before reviewing): {KEY_CSV}")
    print(f"page: {PAGE}")
    print("\n  python -m pronunciation.wav2vec_tone.serve_review --round audit")


def render(items) -> str:
    payload = ",\n".join(
        "{" + ", ".join(
            f'{k}: "{html.escape(str(item[k]), quote=True)}"'
            for k in ("trial_id", "word", "expected_pinyin",
                      "segment_path", "utterance_path")
        ) + "}"
        for item in items
    )
    reason_buttons = "".join(
        f'<button class="rsn" data-r="{code}" title="{html.escape(desc)}">'
        f'{code.replace("_", " ").title()}</button>'
        for code, desc in REASONS
    )
    reason_help = "".join(
        f"<div><b>{code}</b> — {html.escape(desc)}</div>" for code, desc in REASONS
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Failure-mode audit</title>
<style>
 :root {{ --bg:#12100e; --card:#1c1917; --ink:#f5f0e8; --dim:#a8a29e;
          --gold:#c9a227; --ok:#4ade80; --no:#f87171; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--ink);
        font:15px/1.5 system-ui,-apple-system,"Noto Sans TC",sans-serif; }}
 .wrap {{ max-width:760px; margin:0 auto; padding:24px 20px 90px; }}
 h1 {{ font-size:17px; font-weight:600; margin:0 0 8px; }}
 .crit {{ background:var(--card); border:1px solid #2c2825; border-radius:10px;
          padding:14px 16px; font-size:13px; color:var(--dim); margin-bottom:18px; }}
 .crit b {{ color:var(--ink); }}
 .crit div {{ margin:3px 0; }}
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
 .reasons {{ display:none; flex-wrap:wrap; gap:8px; margin-top:12px;
             padding-top:12px; border-top:1px dashed #3f3a35; }}
 .reasons.show {{ display:flex; }}
 .rsn {{ font-size:13px; padding:7px 12px; }}
 .rsn.on {{ background:var(--gold); color:#231a00; border-color:var(--gold);
            font-weight:700; }}
 .need {{ color:var(--no); font-size:12px; margin-top:8px; display:none; }}
 .need.show {{ display:block; }}
 .done {{ border-color:var(--gold); }}
 .kbd {{ font-size:12px; color:var(--dim); margin-top:8px; }}
 input[type=text] {{ width:100%; margin-top:10px; padding:9px; border-radius:8px;
                     border:1px solid #3f3a35; background:#171412; color:inherit; }}
 .export {{ position:fixed; bottom:0; left:0; right:0; background:var(--card);
            border-top:1px solid #2c2825; padding:12px; text-align:center; }}
 .export button {{ background:var(--gold); color:#231a00; font-weight:700;
                   border-color:var(--gold); padding:11px 26px; }}
 @media (prefers-color-scheme: light) {{
   :root {{ --bg:#faf7f2; --card:#fff; --ink:#1c1917; --dim:#6b6560; }}
   .card,.bar,.export,.crit {{ border-color:#e7e0d6; background:#fff; }}
   button {{ background:#f2ede5; border-color:#ddd5c8; }}
   input[type=text] {{ background:#fff; border-color:#ddd5c8; }}
 }}
</style></head><body><div class="wrap">
<h1>Failure-mode audit</h1>
<div class="crit">
 First: <b>is this token usable for tone analysis?</b> Same criterion as before —
 the intended syllable is there and its voiced part is sufficiently complete.
 <br><br>
 If you REJECT, pick the <b>one</b> reason that mattered most:
 <br>
 {reason_help}
 <br>
 <b>Do not</b> reject for tidiness. Only when the clip is genuinely unsafe for
 an acoustic tone measurement.
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
const KEY = "ompal_audit_review";
let votes = JSON.parse(localStorage.getItem(KEY) || "{{}}");
function esc(s) {{ return String(s).replace(/"/g, '""'); }}
function complete(v) {{
  if (!v || !v.j) return false;
  if (v.j === "ACCEPT") return true;
  if (!v.r) return false;
  return v.r !== "OTHER" || (v.n || "").trim().length > 0;
}}
function progress() {{
  const n = ITEMS.filter(it => complete(votes[it.trial_id])).length;
  document.getElementById("prog").textContent = n + " of " + ITEMS.length + " complete";
  document.getElementById("fill").style.width = (100 * n / ITEMS.length) + "%";
}}
function paint(id) {{
  const v = votes[id] || {{}}, card = document.getElementById("c_" + id);
  ["a","r"].forEach(c => card.querySelector("." + c).classList.remove("on"));
  if (v.j) card.querySelector("." + (v.j === "ACCEPT" ? "a" : "r")).classList.add("on");
  card.querySelector(".reasons").classList.toggle("show", v.j === "REJECT");
  card.querySelectorAll(".rsn").forEach(b =>
    b.classList.toggle("on", v.j === "REJECT" && b.dataset.r === v.r));
  // A REJECT without a reason, or OTHER without a note, is incomplete and the
  // export will skip it — say so at the point of entry, not at download.
  card.querySelector(".need").classList.toggle("show", !!v.j && !complete(v));
  card.classList.toggle("done", complete(v));
  progress();
}}
function vote(id, j) {{
  votes[id] = Object.assign({{}}, votes[id], {{ j: j }});
  if (j === "ACCEPT") {{ delete votes[id].r; }}
  localStorage.setItem(KEY, JSON.stringify(votes)); paint(id);
}}
function reason(id, r) {{
  votes[id] = Object.assign({{}}, votes[id], {{ r: r }});
  localStorage.setItem(KEY, JSON.stringify(votes)); paint(id);
}}
function note(id, v) {{
  votes[id] = Object.assign({{}}, votes[id], {{ n: v }});
  localStorage.setItem(KEY, JSON.stringify(votes)); paint(id);
}}
function play(sel) {{ const a = document.querySelector(sel); a.currentTime = 0; a.play(); }}
function save() {{
  const bad = ITEMS.filter(it => !complete(votes[it.trial_id]));
  if (bad.length && !confirm(
      bad.length + " trial(s) are incomplete (no verdict, REJECT without a " +
      "reason, or OTHER without a note) and will be MISSING:\\n\\n" +
      bad.map(b => b.trial_id).join(", ") + "\\n\\nDownload anyway?")) return;
  let out = "trial_id,human_usability_judgment,failure_reason,human_note\\n";
  ITEMS.forEach(it => {{
    const v = votes[it.trial_id] || {{}};
    if (!complete(v)) return;
    out += `${{it.trial_id}},${{v.j}},${{v.r || ""}},"${{esc(v.n || "")}}"\\n`;
  }});
  const blob = new Blob([out], {{ type: "text/csv;charset=utf-8" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "ompal_audit_human_review.csv"; a.click();
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
  <div class="reasons">{reason_buttons}</div>
  <div class="need">Incomplete — a REJECT needs one reason (and OTHER needs a note).</div>
  <input type="text" placeholder="note (required for OTHER)"
     oninput="note('${{it.trial_id}}', this.value)">
  <div class="kbd">a = clip · s = utterance · 1 accept · 2 reject</div>
 </div>`).join("");
document.querySelectorAll(".card").forEach(card => {{
  const id = card.id.slice(2);
  card.querySelectorAll(".rsn").forEach(b =>
    b.addEventListener("click", () => reason(id, b.dataset.r)));
}});
ITEMS.forEach(it => {{
  const v = votes[it.trial_id];
  if (!v) return;
  if (v.n) document.querySelector("#c_" + it.trial_id + " input").value = v.n;
  paint(it.trial_id);
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
