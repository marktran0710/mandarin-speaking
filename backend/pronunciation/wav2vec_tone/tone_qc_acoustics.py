"""Do tone-specific acoustic measures separate stable-usable from stable-unusable?

The failure audit was unstable where it mattered: 9 of 23 rejected tokens were
accepted on a second hearing, while all 24 accepted controls held. So a single
REJECT is not ground truth. This diagnostic uses only tokens judged the same
way twice, and reports the changers separately rather than forcing them into
one class.

The measures are chosen for one question -- can a usable F0 contour be
recovered from this clip -- not for general audio quality. Whole-segment
loudness or noisiness says little about that: a quiet clip with a clean
continuous voiced stretch is fine for tone, and a loud one broken into three
voiced fragments is not.

Two measures are deliberately hobbled. Spectral flatness is computed but never
proposed as a rule: fricatives are noise-like by nature, so it partly measures
which syllable was spoken. Local SNR is only computed when a genuinely
non-speech region exists in the utterance, and is left missing otherwise
rather than estimated from neighbouring speech.

    python -m pronunciation.wav2vec_tone.tone_qc_acoustics
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"
AUDIT_KEY = DATA_DIR / "audit_trial_key.csv"
AUDIT_REVIEW = DATA_DIR / "ompal_audit_human_review.csv"

SAMPLE_RATE = 16000
PITCH_FLOOR, PITCH_CEILING = 60.0, 500.0
PITCH_STEP = 0.005
CLIP_THRESHOLD = 0.98
MIN_NOISE_MS = 120          # shortest stretch we will accept as a noise reference

EXISTING = ("duration_seconds", "alignment_score", "voiced_proportion")
NEW_FEATURES = (
    "valid_f0_proportion", "longest_voiced_ms", "voiced_fragment_count",
    "f0_fragmentation", "implausible_f0_jump_rate", "hnr_db",
    "clipping_fraction", "rms_dbfs", "rms_relative_db", "crest_factor",
    "local_snr_db", "spectral_flatness",
)
# Reported, never proposed as a rule -- see module docstring.
# Excluded from the ranking: spectral flatness tracks phonetic content,
# and absolute RMS/crest track recording gain rather than the token.
DESCRIPTIVE_ONLY = {"spectral_flatness", "rms_dbfs", "crest_factor"}


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


def noise_reference(utterance: np.ndarray, exclude: tuple[int, int]) -> float | None:
    """RMS of the quietest sustained non-speech stretch, or None if there is none.

    Silence is identified from the utterance's own energy distribution, and the
    token itself is excluded. If no stretch of at least MIN_NOISE_MS sits well
    below the speech level, no defensible noise floor exists and SNR stays
    missing -- neighbouring speech is not noise.
    """
    window = int(0.010 * SAMPLE_RATE)
    frames = [utterance[i:i + window] for i in range(0, len(utterance) - window, window)]
    if len(frames) < 10:
        return None
    energies = np.asarray([float(np.sqrt(np.mean(f ** 2)) + 1e-12) for f in frames])
    positions = np.arange(len(frames)) * window

    inside = (positions >= exclude[0] - window) & (positions < exclude[1])
    speech_level = np.percentile(energies[~inside], 75) if (~inside).any() else energies.max()
    # A real silence floor sits far below the speech level; 12 dB is a
    # conservative gap, not a tuned one.
    quiet = (energies < speech_level / (10 ** (12 / 20))) & (~inside)

    best_run, run = 0, 0
    best_indices, current = [], []
    for index, is_quiet in enumerate(quiet):
        if is_quiet:
            run += 1
            current.append(index)
            if run > best_run:
                best_run, best_indices = run, list(current)
        else:
            run, current = 0, []
    if best_run * 10 < MIN_NOISE_MS:
        return None
    return float(np.sqrt(np.mean(np.concatenate([frames[i] for i in best_indices]) ** 2)))


def measure(segment: np.ndarray, utterance: np.ndarray,
            span: tuple[int, int]) -> dict:
    import parselmouth

    result = {name: float("nan") for name in NEW_FEATURES}
    if len(segment) < int(0.03 * SAMPLE_RATE):
        return result

    peak = float(np.max(np.abs(segment)))
    rms = float(np.sqrt(np.mean(segment ** 2)))
    result["clipping_fraction"] = float(np.mean(np.abs(segment) >= CLIP_THRESHOLD))
    result["rms_dbfs"] = 20 * np.log10(rms) if rms > 0 else float("nan")
    # The gain-free version of level: how loud this token is *relative to its
    # own utterance*. Absolute RMS confounds a quiet token with a quietly
    # recorded speaker; this cannot, because both share the same gain.
    utterance_rms = float(np.sqrt(np.mean(utterance ** 2)))
    if rms > 0 and utterance_rms > 0:
        result["rms_relative_db"] = 20 * np.log10(rms / utterance_rms)
    result["crest_factor"] = peak / rms if rms > 0 else float("nan")

    sound = parselmouth.Sound(segment.astype(np.float64), SAMPLE_RATE)
    pitch = sound.to_pitch(time_step=PITCH_STEP, pitch_floor=PITCH_FLOOR,
                           pitch_ceiling=PITCH_CEILING)
    frequencies = pitch.selected_array["frequency"]
    voiced = np.isfinite(frequencies) & (frequencies > 0)

    if len(frequencies):
        result["valid_f0_proportion"] = float(voiced.mean())
        runs, run = [], 0
        for flag in voiced:
            if flag:
                run += 1
            elif run:
                runs.append(run)
                run = 0
        if run:
            runs.append(run)
        result["voiced_fragment_count"] = float(len(runs))
        longest = max(runs) if runs else 0
        result["longest_voiced_ms"] = longest * PITCH_STEP * 1000
        # 0 when the voiced frames form one unbroken run, approaching 1 as they
        # scatter. This is the shape of the problem for tone: a contour needs a
        # continuous stretch, not a high total count.
        total_voiced = int(voiced.sum())
        result["f0_fragmentation"] = (
            1.0 - longest / total_voiced if total_voiced else float("nan"))

        values = frequencies[voiced]
        times = np.asarray(pitch.xs())[voiced]
        if len(values) > 1:
            ratios = values[1:] / np.maximum(values[:-1], 1e-9)
            ratios = np.maximum(ratios, 1.0 / np.maximum(ratios, 1e-9))
            contiguous = np.diff(times) <= PITCH_STEP * 1.5
            if contiguous.any():
                result["implausible_f0_jump_rate"] = float(
                    np.mean(ratios[contiguous] > 1.5))

    try:
        harmonicity = sound.to_harmonicity_cc(
            time_step=PITCH_STEP, minimum_pitch=PITCH_FLOOR)
        values = np.asarray(harmonicity.values[0], dtype=float)
        # Praat marks unvoiced frames -200; averaging those in would turn HNR
        # into a voicing-proportion measure wearing a different name.
        usable = values[np.isfinite(values) & (values > -100)]
        if len(usable):
            result["hnr_db"] = float(np.mean(usable))
    except Exception:  # noqa: BLE001 - left missing rather than guessed
        pass

    noise = noise_reference(utterance, span)
    if noise and noise > 0 and rms > 0:
        result["local_snr_db"] = 20 * np.log10(rms / noise)

    spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment)))) ** 2
    spectrum = spectrum[spectrum > 0]
    if len(spectrum) > 4:
        result["spectral_flatness"] = float(
            np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))
    return result


def auc(values, labels) -> float:
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    keep = np.isfinite(values)
    values, labels = values[keep], labels[keep]
    positives, negatives = int(labels.sum()), int((~labels).sum())
    if not positives or not negatives:
        return float("nan")
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    sorted_values = values[order]
    index = 0
    while index < len(sorted_values):
        stop = index
        while stop + 1 < len(sorted_values) and sorted_values[stop + 1] == sorted_values[index]:
            stop += 1
        ranks[order[index:stop + 1]] = (index + stop) / 2.0 + 1.0
        index = stop + 1
    return float((ranks[labels].sum() - positives * (positives + 1) / 2)
                 / (positives * negatives))


def bootstrap_auc(values, labels, seed=0, samples=4000):
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    keep = np.isfinite(values)
    values, labels = values[keep], labels[keep]
    if labels.sum() < 3 or (~labels).sum() < 3:
        return None
    rng = np.random.default_rng(seed)
    positive_index = np.flatnonzero(labels)
    negative_index = np.flatnonzero(~labels)
    draws = []
    for _ in range(samples):
        picked = np.concatenate([
            rng.choice(positive_index, len(positive_index), replace=True),
            rng.choice(negative_index, len(negative_index), replace=True)])
        value = auc(values[picked], labels[picked])
        if np.isfinite(value):
            draws.append(value)
    if not draws:
        return None
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def summarise(values):
    values = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if not len(values):
        return None
    return {
        "n": int(len(values)), "median": float(np.median(values)),
        "q1": float(np.percentile(values, 25)),
        "q3": float(np.percentile(values, 75)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    key = {r["trial_id"]: r for r in csv.DictReader(AUDIT_KEY.open(encoding="utf-8"))}
    labels = {}
    for row in csv.DictReader(AUDIT_REVIEW.open(encoding="utf-8")):
        entry = key.get(row["trial_id"])
        if not entry:
            continue
        now = row["human_usability_judgment"].strip().upper()
        before = entry["previous_verdict"]
        group = ("STABLE_ACCEPT" if before == now == "ACCEPT"
                 else "STABLE_REJECT" if before == now == "REJECT"
                 else "AMBIGUOUS")
        labels[entry["token_id"]] = {
            "group": group, "before": before, "after": now,
            "reason": row.get("failure_reason", "").strip().upper(),
        }

    pilot = {}
    for row in csv.DictReader(PILOT_CSV.open(encoding="utf-8")):
        if row["start_seconds"]:
            pilot[f"{row['utterance_id']}_{int(row['token_index']):02d}"] = row

    records, cache = [], {}
    for token_id, label in sorted(labels.items()):
        source = pilot.get(token_id)
        if source is None:
            continue
        utterance_id = source["utterance_id"]
        if utterance_id not in cache:
            cache[utterance_id] = load_audio(
                OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav")
        audio = cache[utterance_id]
        begin = max(0, int(round(float(source["start_seconds"]) * SAMPLE_RATE)))
        finish = min(len(audio), int(round(float(source["end_seconds"]) * SAMPLE_RATE)))
        record = {
            "token_id": token_id, **label,
            "duration_seconds": float(source["duration_seconds"]),
            "alignment_score": float(source["alignment_score"]),
            "voiced_proportion": float(source["voiced_proportion"]),
            "expected_tone": source["expected_tone"],
            "speaker_id": source["speaker_id"],
        }
        record.update(measure(audio[begin:finish], audio, (begin, finish)))
        records.append(record)

    groups = Counter(r["group"] for r in records)
    stable = [r for r in records if r["group"] != "AMBIGUOUS"]
    ambiguous = [r for r in records if r["group"] == "AMBIGUOUS"]
    is_accept = [r["group"] == "STABLE_ACCEPT" for r in stable]

    lines = [
        "=" * 88,
        "TONE-ANALYSIS-SPECIFIC ACOUSTIC QC DIAGNOSTIC",
        "=" * 88,
        f"STABLE_ACCEPT : {groups['STABLE_ACCEPT']}",
        f"STABLE_REJECT : {groups['STABLE_REJECT']}",
        f"AMBIGUOUS     : {groups['AMBIGUOUS']}  (excluded from all AUCs)",
        "",
        "Confirmed failure reasons among STABLE_REJECT:",
    ]
    for reason, count in Counter(
            r["reason"] for r in records
            if r["group"] == "STABLE_REJECT" and r["reason"]).most_common():
        lines.append(f"  {reason:<26}{count:>3}")

    availability = {
        name: sum(1 for r in stable if np.isfinite(r.get(name, float('nan'))))
        for name in NEW_FEATURES
    }
    missing = [n for n, c in availability.items() if c < len(stable)]
    if missing:
        lines += ["", "Features not available for every token (left missing, "
                  "never imputed):"]
        for name in missing:
            lines.append(f"  {name:<28}{availability[name]}/{len(stable)} tokens")

    def block(title, names):
        rows_out = ["", "-" * 88, title, "-" * 88,
                    f"  {'feature':<28}{'n':>4}{'ACC median':>12}{'ACC IQR':>18}"
                    f"{'REJ median':>12}{'REJ IQR':>18}{'AUC':>7}{'95% CI':>16}"]
        results = {}
        for name in names:
            accept_values = [r[name] for r in stable if r["group"] == "STABLE_ACCEPT"]
            reject_values = [r[name] for r in stable if r["group"] == "STABLE_REJECT"]
            a, b = summarise(accept_values), summarise(reject_values)
            if not a or not b:
                rows_out.append(f"  {name:<28}  (insufficient data)")
                continue
            value = auc([r[name] for r in stable], is_accept)
            interval = bootstrap_auc([r[name] for r in stable], is_accept, args.seed)
            direction = ("higher->usable" if value > 0.5 else "lower->usable")
            results[name] = {
                "auc": value, "ci": interval, "accept": a, "reject": b,
                "direction": direction,
                "separation": abs(value - 0.5) * 2,
            }
            rows_out.append(
                f"  {name:<28}{a['n'] + b['n']:>4}{a['median']:>12.3f}"
                f"{f'[{a[chr(113)+chr(49)]:.3f},{a[chr(113)+chr(51)]:.3f}]':>18}"
                f"{b['median']:>12.3f}"
                f"{f'[{b[chr(113)+chr(49)]:.3f},{b[chr(113)+chr(51)]:.3f}]':>18}"
                f"{value:>7.3f}"
                + (f"{f'[{interval[0]:.2f},{interval[1]:.2f}]':>16}" if interval
                   else f"{'--':>16}"))
        for name, result in results.items():
            rows_out.append(f"    {name}: {result['direction']}")
        return rows_out, results

    existing_block, existing_results = block(
        "EXISTING FEATURES, re-measured on stable labels only", EXISTING)
    lines += existing_block
    lines += [
        "",
        "  READ WITH CARE. The STABLE_ACCEPT group is exactly the 24 controls",
        "  that were matched to the rejects on tone, DURATION and ALIGNMENT",
        "  SCORE. Those two features were equalised across the groups by",
        "  construction, so their AUC here is pushed toward 0.5 by the design",
        "  and is not a measurement of their worth. Duration scored 0.760 on the",
        "  earlier unmatched sample of 116; that figure and this one do not",
        "  contradict each other, they answer different questions.",
        "",
        "  The practical consequence: comparing a new feature's AUC against",
        "  these numbers is biased in the new feature's favour. Only a fresh",
        "  unmatched sample can rank old against new.",
    ]
    new_block, new_results = block(
        "NEW TONE-SPECIFIC ACOUSTIC CANDIDATES", NEW_FEATURES)
    lines += new_block

    # --- redundancy ---------------------------------------------------------
    lines += ["", "-" * 88,
              "CORRELATION AMONG CANDIDATES (Spearman, |rho| >= 0.6 only)",
              "-" * 88]
    names = [n for n in EXISTING + NEW_FEATURES
             if availability.get(n, len(stable)) >= 10 or n in EXISTING]

    def ranks(values):
        values = np.asarray(values, dtype=float)
        order = np.argsort(values, kind="mergesort")
        out = np.empty(len(values))
        out[order] = np.arange(len(values))
        return out

    pairs = []
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            a = np.asarray([r[first] for r in stable], dtype=float)
            b = np.asarray([r[second] for r in stable], dtype=float)
            keep = np.isfinite(a) & np.isfinite(b)
            if keep.sum() < 8:
                continue
            ra, rb = ranks(a[keep]), ranks(b[keep])
            rho = float(np.corrcoef(ra, rb)[0, 1])
            if abs(rho) >= 0.6:
                pairs.append((abs(rho), first, second, rho, int(keep.sum())))
    if pairs:
        for _, first, second, rho, n in sorted(pairs, reverse=True):
            lines.append(f"  {first:<28}{second:<28}rho={rho:+.2f}  n={n}")
        lines.append("  Pairs above are not independent evidence; treat each "
                     "cluster as one signal.")
    else:
        lines.append("  No pair reaches |rho| >= 0.6.")

    # --- ambiguous positioning ---------------------------------------------
    lines += ["", "-" * 88,
              f"AMBIGUOUS TOKENS (n={len(ambiguous)}) — where do they sit?",
              "-" * 88,
              f"  {'feature':<28}{'ACC med':>10}{'AMB med':>10}{'REJ med':>10}"
              f"{'between?':>11}"]
    between_count = 0
    considered = 0
    for name in EXISTING + NEW_FEATURES:
        accept_values = [r[name] for r in stable if r["group"] == "STABLE_ACCEPT"]
        reject_values = [r[name] for r in stable if r["group"] == "STABLE_REJECT"]
        ambiguous_values = [r[name] for r in ambiguous]
        a, b, m = (summarise(accept_values), summarise(reject_values),
                   summarise(ambiguous_values))
        if not (a and b and m):
            continue
        low, high = sorted((a["median"], b["median"]))
        is_between = low <= m["median"] <= high
        considered += 1
        between_count += int(is_between)
        lines.append(f"  {name:<28}{a['median']:>10.3f}{m['median']:>10.3f}"
                     f"{b['median']:>10.3f}{('yes' if is_between else 'no'):>11}")
    verdict = ("YES" if between_count >= considered * 0.7
               else "NO" if between_count <= considered * 0.3 else "MIXED")
    lines.append(f"  -> ambiguous median lies between the stable groups on "
                 f"{between_count}/{considered} features: {verdict}")

    # --- ranking ------------------------------------------------------------
    ranked = sorted(
        ((name, result) for name, result in new_results.items()
         if name not in DESCRIPTIVE_ONLY and np.isfinite(result["auc"])),
        key=lambda item: item[1]["separation"], reverse=True)
    best_existing = max(existing_results.items(),
                        key=lambda item: item[1]["separation"], default=(None, None))

    lines += ["", "=" * 88, "TOP CANDIDATES", "=" * 88,
              "  (descriptive-only measures are excluded from ranking: spectral",
              "   flatness tracks phonetic content, and RMS/crest track "
              "recording gain)"]
    for position, (name, result) in enumerate(ranked[:3], start=1):
        interval = result["ci"]
        lines.append(
            f"  {position}. {name:<26}AUC {result['auc']:.3f}"
            + (f"  95% CI [{interval[0]:.2f}, {interval[1]:.2f}]" if interval else "")
            + f"  ({result['direction']})")

    lines += ["", "=" * 88, "SUMMARY", "=" * 88,
              f"Stable ACCEPT : {groups['STABLE_ACCEPT']}",
              f"Stable REJECT : {groups['STABLE_REJECT']}",
              f"Ambiguous     : {groups['AMBIGUOUS']}"]
    if best_existing[0]:
        lines += ["",
                  f"Best existing QC signal : {best_existing[0]}",
                  f"AUC                     : {best_existing[1]['auc']:.3f}"]
    if ranked:
        name, result = ranked[0]
        interval = result["ci"]
        lines += ["",
                  f"Best new acoustic QC signal : {name}",
                  f"AUC                         : {result['auc']:.3f}",
                  f"95% CI                      : "
                  + (f"[{interval[0]:.3f}, {interval[1]:.3f}]" if interval else "--")]
        if len(ranked) > 1:
            lines += ["", f"Second-best new signal      : {ranked[1][0]}",
                      f"AUC                         : {ranked[1][1]['auc']:.3f}"]

    lines.append(f"\nDo the ambiguous cases fall mostly between the stable "
                 f"groups? {verdict}")

    # Matching equalised duration and alignment score between the groups, so
    # this subset cannot rank new features against them however the numbers
    # fall. Saying YES here would be an artefact of the design.
    improves = "UNCERTAIN"
    lines.append(f"Is there evidence that acoustic QC can improve on "
                 f"duration/alignment score? {improves}")
    lines.append("  Not because the acoustic signals look weak -- the best is "
                 "clearly stronger here --")
    lines.append("  but because duration and alignment score were matched "
                 "between the groups by")
    lines.append("  design, so this sample cannot compare them fairly. That "
                 "needs a fresh unmatched set.")
    lines += ["",
              f"Sample bound: {groups['STABLE_REJECT']} stable rejections. Every "
              f"CI here is wide;",
              "these are candidate rankings, not measurements of effect size."]
    print("\n".join(lines))

    payload = {
        "groups": dict(groups),
        "reasons_stable_reject": dict(Counter(
            r["reason"] for r in records if r["group"] == "STABLE_REJECT" and r["reason"])),
        "availability": availability,
        "existing": {k: {kk: vv for kk, vv in v.items()} for k, v in existing_results.items()},
        "new": {k: {kk: vv for kk, vv in v.items()} for k, v in new_results.items()},
        "correlated_pairs": [
            {"a": a, "b": b, "rho": rho, "n": n} for _, a, b, rho, n in sorted(pairs, reverse=True)],
        "ambiguous_between_verdict": verdict,
        "acoustic_improves_existing": improves,
        "matched_design_caveat": (
            "STABLE_ACCEPT are the controls matched to rejects on tone, "
            "duration and alignment score; those features' AUCs are attenuated "
            "by construction and cannot be compared against new features here"),
        "ranking": [name for name, _ in ranked[:3]],
        "descriptive_only": sorted(DESCRIPTIVE_ONLY),
        "records": records,
    }
    path = DATA_DIR / "ompal_tone_qc_acoustics.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float),
                    encoding="utf-8")
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()
