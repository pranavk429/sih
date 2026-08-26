"""
The three-number experiment, redone leak-free.

v1 (run_experiment.py) used a pretrained classifier that turned out to have
memorized this exact benchmark (0.0% EER, near-zero-variance genuine scores --
see README's "known issue" note). This version fixes that by:

  1. Using facebook/wav2vec2-base as a frozen, task-naive feature extractor
     (see probe_model.py for why this specifically fixes the leakage).
  2. Fitting our OWN logistic-regression classifier on a FIT speaker group
     (40 speakers, 117 files) that has ZERO overlap with the TEST speaker
     group (25 speakers) used for every reported number below.

Same three-pass structure as before:
  1. CLEAN baseline   -- probe-based CM on clean audio
  2. DEGRADED         -- same, after Opus 8kbps + 5% packet loss
  3. DEGRADED + ENROLL -- degraded audio, fused with speaker-similarity
                          against a genuine enrollment recording

PILOT SCALE. 25 test speakers, ~119 trials. Directionally honest, not
statistically final -- see README.md before quoting any number.
"""
from __future__ import annotations
import os
import sys
import json
import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.dirname(__file__))
from channel_sim import degrade
from probe_model import ProbeBackbone
from speaker_id import embed as spk_embed, similarity
from metrics import eer

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "pilot")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
DEGRADE_PROFILE = "mobile_voip"


def load_manifest():
    with open(os.path.join(CACHE_DIR, "manifest.json")) as f:
        return json.load(f)


def load_audio(fname):
    return np.load(os.path.join(CACHE_DIR, fname)).astype(np.float32)


def main():
    manifest = load_manifest()
    by_speaker = {}
    for row in manifest:
        by_speaker.setdefault(row["speaker_id"], {"bonafide": [], "spoof": []})
        by_speaker[row["speaker_id"]][row["label"]].append(row)

    test_speakers = {
        spk: v for spk, v in by_speaker.items()
        if len(v["bonafide"]) >= 2 and len(v["spoof"]) >= 1
    }
    fit_rows = [r for r in manifest if r["speaker_id"] not in test_speakers]

    print(f"FIT group: {len(set(r['speaker_id'] for r in fit_rows))} speakers, "
          f"{len(fit_rows)} files")
    print(f"TEST group: {len(test_speakers)} speakers "
          f"(zero speaker overlap with FIT group, verified below)")
    overlap = set(r["speaker_id"] for r in fit_rows) & set(test_speakers)
    assert not overlap, f"speaker leakage between fit/test: {overlap}"
    print("speaker-disjointness verified: no leakage between fit and test sets\n")

    print("loading task-naive backbone (facebook/wav2vec2-base)...")
    backbone = ProbeBackbone()

    print("extracting FIT embeddings...")
    X_fit, y_fit = [], []
    for row in fit_rows:
        audio = load_audio(row["file"])
        X_fit.append(backbone.embed(audio, row["sr"]))
        y_fit.append(1 if row["label"] == "spoof" else 0)
    X_fit, y_fit = np.array(X_fit), np.array(y_fit)

    print("fitting logistic regression probe on FIT embeddings...")
    clf = LogisticRegression(max_iter=2000, C=1.0)
    clf.fit(X_fit, y_fit)
    train_acc = clf.score(X_fit, y_fit)
    print(f"  fit-set training accuracy: {train_acc*100:.1f}% (n={len(y_fit)})\n")

    # build TEST trials exactly as v1 did: held-out enrollment ref per
    # speaker, remaining bonafide = genuine trials, all spoof = impostor trials
    trials = []
    enroll_embeddings = {}
    for spk, v in test_speakers.items():
        ref_row = v["bonafide"][0]
        ref_audio = load_audio(ref_row["file"])
        enroll_embeddings[spk] = spk_embed(ref_audio, ref_row["sr"])
        for row in v["bonafide"][1:]:
            trials.append({**row, "target_speaker": spk})
        for row in v["spoof"]:
            trials.append({**row, "target_speaker": spk})

    print(f"{len(trials)} TEST trials "
          f"({sum(1 for t in trials if t['label']=='bonafide')} genuine / "
          f"{sum(1 for t in trials if t['label']=='spoof')} spoof)")

    labels = np.array([1 if t["label"] == "spoof" else 0 for t in trials])

    print("\n--- pass 1: CLEAN baseline (probe CM only) ---")
    cm_scores_clean = []
    for t in trials:
        audio = load_audio(t["file"])
        emb = backbone.embed(audio, t["sr"])
        cm_scores_clean.append(clf.predict_proba(emb.reshape(1, -1))[0, 1])
    cm_scores_clean = np.array(cm_scores_clean)
    eer_clean, _ = eer(cm_scores_clean, labels)
    print(f"  bonafide score stats: mean={cm_scores_clean[labels==0].mean():.3f} "
          f"std={cm_scores_clean[labels==0].std():.3f}")
    print(f"  spoof score stats:    mean={cm_scores_clean[labels==1].mean():.3f} "
          f"std={cm_scores_clean[labels==1].std():.3f}")

    print("\n--- pass 2: DEGRADED (Opus 8kbps + 5% packet loss), probe CM only ---")
    cm_scores_degraded = []
    spk_scores_degraded = []
    for t in trials:
        audio = load_audio(t["file"])
        degraded_audio, degraded_sr = degrade(audio, t["sr"], profile=DEGRADE_PROFILE, seed=42)
        emb = backbone.embed(degraded_audio, degraded_sr)
        cm_scores_degraded.append(clf.predict_proba(emb.reshape(1, -1))[0, 1])
        test_spk_emb = spk_embed(degraded_audio, degraded_sr)
        sim = similarity(enroll_embeddings[t["target_speaker"]], test_spk_emb)
        spk_scores_degraded.append(1.0 - sim)
    cm_scores_degraded = np.array(cm_scores_degraded)
    spk_scores_degraded = np.array(spk_scores_degraded)
    eer_degraded, _ = eer(cm_scores_degraded, labels)

    print("\n--- pass 3: DEGRADED + ENROLLMENT FUSION ---")
    fused_scores = (cm_scores_degraded + spk_scores_degraded) / 2.0
    eer_fused, _ = eer(fused_scores, labels)

    print("\n" + "=" * 60)
    print(f"LEAK-FREE PILOT RESULTS  (n={len(trials)} test trials, "
          f"{len(test_speakers)} test speakers, {len(y_fit)} fit examples)")
    print("=" * 60)
    print(f"1. Clean baseline EER (probe CM only)..... {eer_clean*100:.1f}%")
    print(f"2. Degraded EER (probe CM only)............ {eer_degraded*100:.1f}%")
    print(f"3. Degraded + enrollment fusion EER........ {eer_fused*100:.1f}%")
    print("=" * 60)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = {
        "n_test_trials": len(trials),
        "n_test_speakers": len(test_speakers),
        "n_fit_examples": len(y_fit),
        "n_fit_speakers": len(set(r["speaker_id"] for r in fit_rows)),
        "fit_train_accuracy": train_acc,
        "degrade_profile": DEGRADE_PROFILE,
        "backbone": "facebook/wav2vec2-base (self-supervised, task-naive)",
        "eer_clean_cm_only": eer_clean,
        "eer_degraded_cm_only": eer_degraded,
        "eer_degraded_plus_enrollment": eer_fused,
        "note": "PILOT SCALE, leak-free version. v1 used a pretrained classifier "
                "that had memorized ASVspoof2019 (0.0% EER, std=0.003 on bonafide "
                "scores -- textbook overfitting). This version fits its own linear "
                "probe on a speaker-disjoint fit set using a backbone that never "
                "saw the spoof-detection task. Still pilot scale (~119 test trials, "
                "English-centric benchmark, CPU-only). Full-scale run on "
                "Indian-language data happens on Kaggle -- see "
                "notebooks/kaggle_full_run.py.",
    }
    with open(os.path.join(RESULTS_DIR, "pilot_results_v2_leakfree.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nsaved to {RESULTS_DIR}/pilot_results_v2_leakfree.json")


if __name__ == "__main__":
    main()
