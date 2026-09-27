"""Compare the system with OMPAL's expert raters, on the raters' own terms.

The question "is the system better or worse" only has an answer relative to
how well the experts agree with EACH OTHER, so every system number here is
paired with the same statistic computed between human raters:

* Syllable tone (binary correct/incorrect): the system is compared with each
  rater separately and averaged, exactly like the three rater-vs-rater pairs.
  Cohen's kappa is reported with Gwet's AC1 because ~86% of syllables are
  correct and kappa is known to understate agreement at that prevalence.
* Sentence scores (1-5): each rater is correlated with the mean of the other
  two (leave-one-rater-out), and the system with that same mean, so both
  predict the identical target.

Uncertainty comes from a speaker-cluster bootstrap (whole speakers are
resampled, because one learner's syllables are not independent), giving a
95% CI for (system - human). A CI entirely below zero means the system is
reliably weaker than a single expert; one straddling zero means it is within
the human range; entirely above zero means better.

Example, from ``backend/``::

    python -m scripts.research.ompal.analyze --out output/ompal
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, spearmanr

RATER_PAIRS = ((0, 1), (0, 2), (1, 2))
UNCERTAIN_POLICIES = {"uncertain_as_correct": 1, "uncertain_as_incorrect": 0}


# ── agreement statistics ────────────────────────────────────────────────────

def cohen_kappa(a: np.ndarray, b: np.ndarray) -> float:
    po = np.mean(a == b)
    pa, pb = a.mean(), b.mean()
    pe = pa * pb + (1 - pa) * (1 - pb)
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def gwet_ac1(a: np.ndarray, b: np.ndarray) -> float:
    po = np.mean(a == b)
    pi = (a.mean() + b.mean()) / 2
    pe = 2 * pi * (1 - pi)
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def fleiss_kappa(votes: np.ndarray) -> float:
    n = votes.shape[1]
    ones = votes.sum(axis=1)
    per_item = (ones * (ones - 1) + (n - ones) * (n - ones - 1)) / (n * (n - 1))
    p1 = ones.sum() / votes.size
    pe = p1**2 + (1 - p1) ** 2
    return float((per_item.mean() - pe) / (1 - pe))


def auc(labels: np.ndarray, scores: np.ndarray) -> float:
    ranks = rankdata(scores)
    positives = labels == 1
    n_pos, n_neg = positives.sum(), (~positives).sum()
    return float((ranks[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def icc_2(ratings: np.ndarray) -> tuple[float, float]:
    """ICC(2,1) and ICC(2,k): two-way random effects, absolute agreement."""
    n, k = ratings.shape
    grand = ratings.mean()
    ms_rows = k * np.sum((ratings.mean(axis=1) - grand) ** 2) / (n - 1)
    ms_cols = n * np.sum((ratings.mean(axis=0) - grand) ** 2) / (k - 1)
    ss_err = np.sum((ratings - ratings.mean(axis=1, keepdims=True) - ratings.mean(axis=0) + grand) ** 2)
    ms_err = ss_err / ((n - 1) * (k - 1))
    single = (ms_rows - ms_err) / (ms_rows + (k - 1) * ms_err + k * (ms_cols - ms_err) / n)
    average = (ms_rows - ms_err) / (ms_rows + (ms_cols - ms_err) / n)
    return float(single), float(average)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    return float(spearmanr(a, b)[0])


# ── data assembly ───────────────────────────────────────────────────────────

def load(out: Path, config: str) -> tuple[dict, dict]:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    outputs = {r["id"]: r for r in json.loads((out / "system_outputs.json").read_text(encoding="utf-8"))}
    syllables = {k: [] for k in ("speaker", "votes", "majority", "verdict", "score", "expected_tone")}
    sentences = {k: [] for k in ("speaker", "accuracy", "fluency", "prosody", "tone_accuracy", "speech_rate", "fluency_score")}
    skipped = {"system_error": 0, "token_mismatch": 0, "not_scorable": 0}
    for item in manifest:
        result = outputs.get(item["id"], {}).get(config, {})
        if not result or "error" in result:
            skipped["system_error"] += 1
            continue
        if result.get("can_score_pronunciation") is False:
            skipped["not_scorable"] += 1
            continue
        words = result["words"]
        if [w["token"] for w in words] != [c["char"] for c in item["characters"]]:
            skipped["token_mismatch"] += 1
            continue
        for word, char in zip(words, item["characters"]):
            syllables["speaker"].append(item["speaker"])
            syllables["votes"].append(char["tone_votes"])
            syllables["majority"].append(char["tone_ok"])
            syllables["verdict"].append(word["verdict"] or "NONE")
            syllables["score"].append(word["tone_accuracy"] if word["tone_accuracy"] is not None else np.nan)
            syllables["expected_tone"].append(char["expected_tone"] or 0)
        sentences["speaker"].append(item["speaker"])
        for dim in ("accuracy", "fluency", "prosody"):
            sentences[dim].append(item[f"rater_{dim}"])
        for key in ("tone_accuracy", "speech_rate", "fluency_score"):
            sentences[key].append(result.get(key) if result.get(key) is not None else np.nan)
    syl = {k: np.array(v) for k, v in syllables.items()}
    sen = {k: np.array(v, dtype=float if k != "speaker" else object) for k, v in sentences.items()}
    return {"syllables": syl, "sentences": sen}, skipped


def system_labels(verdicts: np.ndarray, uncertain_as: int) -> np.ndarray:
    labels = np.where(verdicts == "INCORRECT", 0, 1)
    return np.where(verdicts == "UNCERTAIN", uncertain_as, labels)


# ── metric families (each returns system value and human value) ─────────────

def tone_metrics(syl: dict, idx: np.ndarray, uncertain_as: int, stat) -> tuple[float, float]:
    votes = syl["votes"][idx]
    sys_lab = system_labels(syl["verdict"][idx], uncertain_as)
    human = np.mean([stat(votes[:, i], votes[:, j]) for i, j in RATER_PAIRS])
    system = np.mean([stat(sys_lab, votes[:, i]) for i in range(3)])
    return float(system), float(human)


def sentence_metrics(sen: dict, idx: np.ndarray, human_dim: str, system_key: str) -> tuple[float, float]:
    ratings = sen[human_dim][idx]
    system_scores = sen[system_key][idx]
    ok = ~np.isnan(system_scores)
    human, system = [], []
    for r in range(3):
        others = np.delete(ratings, r, axis=1).mean(axis=1)
        human.append(spearman(ratings[ok, r], others[ok]))
        system.append(spearman(system_scores[ok], others[ok]))
    return float(np.mean(system)), float(np.mean(human))


def bootstrap(metric, groups: np.ndarray, n_boot: int, seed: int = 7) -> tuple[float, float, float, float]:
    """Point estimates plus a speaker-cluster 95% CI for (system - human)."""
    speakers = np.unique(groups)
    index_by_speaker = {s: np.flatnonzero(groups == s) for s in speakers}
    system, human = metric(np.arange(len(groups)))
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        drawn = rng.choice(speakers, size=len(speakers), replace=True)
        s, h = metric(np.concatenate([index_by_speaker[d] for d in drawn]))
        diffs.append(s - h)
    low, high = np.nanpercentile(diffs, [2.5, 97.5])
    return system, human, float(low), float(high)


def verdict_word(low: float, high: float) -> str:
    if high < 0:
        return "WEAKER than a single expert"
    if low > 0:
        return "BETTER than a single expert"
    return "within the human range"


# ── report ──────────────────────────────────────────────────────────────────

def report(out: Path, config: str, n_boot: int) -> dict:
    data, skipped = load(out, config)
    syl, sen = data["syllables"], data["sentences"]
    votes = syl["votes"]
    result: dict = {"config": config, "skipped_utterances": skipped,
                    "n_syllables": int(len(votes)), "n_sentences": int(len(sen["accuracy"])),
                    "n_speakers": int(len(np.unique(syl["speaker"])))}

    result["human_reliability"] = {
        "tone_percent_agreement": float(np.mean([np.mean(votes[:, i] == votes[:, j]) for i, j in RATER_PAIRS])),
        "tone_fleiss_kappa": fleiss_kappa(votes),
        "tone_mean_pairwise_kappa": float(np.mean([cohen_kappa(votes[:, i], votes[:, j]) for i, j in RATER_PAIRS])),
        "tone_mean_pairwise_ac1": float(np.mean([gwet_ac1(votes[:, i], votes[:, j]) for i, j in RATER_PAIRS])),
        "tone_error_rate_majority": float(1 - syl["majority"].mean()),
        **{f"{dim}_icc2_single_average": icc_2(sen[dim]) for dim in ("accuracy", "fluency", "prosody")},
    }
    result["system_verdict_counts"] = {v: int(c) for v, c in zip(*np.unique(syl["verdict"], return_counts=True))}

    comparisons = {}
    for policy, uncertain_as in UNCERTAIN_POLICIES.items():
        for name, stat in (("kappa", cohen_kappa), ("ac1", gwet_ac1)):
            comparisons[f"tone_{name}_{policy}"] = bootstrap(
                lambda idx, u=uncertain_as, s=stat: tone_metrics(syl, idx, u, s), syl["speaker"], n_boot)
    confident = np.flatnonzero(np.isin(syl["verdict"], ["CORRECT", "INCORRECT"]))
    sub = {k: v[confident] for k, v in syl.items()}
    comparisons["tone_kappa_confident_verdicts_only"] = bootstrap(
        lambda idx: tone_metrics(sub, idx, 1, cohen_kappa), sub["speaker"], n_boot)
    result["confident_verdict_coverage"] = float(len(confident) / len(votes))
    for human_dim, system_key in (("accuracy", "tone_accuracy"), ("prosody", "tone_accuracy"),
                                  ("fluency", "speech_rate"), ("fluency", "fluency_score")):
        comparisons[f"sentence_{system_key}_vs_{human_dim}_spearman"] = bootstrap(
            lambda idx, d=human_dim, k=system_key: sentence_metrics(sen, idx, d, k), sen["speaker"], n_boot)
    result["comparisons"] = {
        name: {"system": s, "human": h, "diff_ci95": [lo, hi], "verdict": verdict_word(lo, hi)}
        for name, (s, h, lo, hi) in comparisons.items()
    }

    scored = ~np.isnan(syl["score"].astype(float))
    result["syllable_score_auc_vs_majority"] = auc(syl["majority"][scored], syl["score"][scored].astype(float))
    by_tone = {}
    for tone in (1, 2, 3, 4, 5):
        mask = syl["expected_tone"] == tone
        if mask.sum() < 50:
            continue
        m = mask & scored
        by_tone[str(tone)] = {
            "n": int(mask.sum()),
            "human_error_rate": float(1 - syl["majority"][mask].mean()),
            "human_pairwise_kappa": float(np.mean([cohen_kappa(votes[mask, i], votes[mask, j]) for i, j in RATER_PAIRS])),
            "system_kappa_uncertain_as_correct": tone_metrics(syl, np.flatnonzero(mask), 1, cohen_kappa)[0],
            "system_score_auc": auc(syl["majority"][m], syl["score"][m].astype(float)) if len(set(syl["majority"][m])) == 2 else None,
        }
    result["by_expected_tone"] = by_tone
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=Path("output/ompal"), type=Path)
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()
    reports = [report(args.out, config, args.bootstrap) for config in ("template", "native")]
    (args.out / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
