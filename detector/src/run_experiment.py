"""
The three-number experiment, as promised:

  1. CLEAN BASELINE   -- blind CM detector on clean studio-quality audio
  2. DEGRADED         -- same detector, audio pushed through a simulated
                         Indian phone line (Opus 8kbps + packet loss)
  3. DEGRADED + ENROLL -- same degraded audio, but fused with a speaker-
                         similarity check against a genuine enrollment
                         recording (captured cleanly, in advance)

Thesis: (2) should be much worse than (1) -- proving the phone line destroys
the evidence a blind detector needs. (3) should recover most of that loss --
proving the enrollment reframe is the right architectural answer.

PILOT SCALE: ~25 speakers, ~100 trials. Enough to prove the mechanism and
get a directionally honest number. NOT enough for a statistically tight EER
estimate -- that's the Kaggle full-scale run. Every number this script prints
is labeled with its trial count so nobody mistakes pilot for final.
"""
from __future__ import annotations
import os
import sys
import json
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from channel_sim import degrade
from cm_model import CountermeasureModel
from speaker_id import embed, similarity
from metrics import eer

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "pilot")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
DEGRADE_PROFILE = "mobile_voip"  # Opus 8kbps + 5% packet loss -- see channel_sim.py


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

    # keep only speakers with a usable enrollment ref + at least one genuine
    # test trial + at least one spoof (impostor) trial
    speakers = {
        spk: v for spk, v in by_speaker.items()
        if len(v["bonafide"]) >= 2 and len(v["spoof"]) >= 1
    }
    print(f"{len(speakers)} speakers usable for the enrollment experiment")

    print("loading CM model (wav2vec2-XLSR spoof classifier)...")
    cm = CountermeasureModel()

    trials = []  # each: {speaker, audio, sr, label, is_enroll_holdout}
    enroll_embeddings = {}

    print("computing enrollment embeddings from held-out clean references...")
    for spk, v in speakers.items():
        ref_row = v["bonafide"][0]  # first bonafide utt = the enrollment recording
        ref_audio = load_audio(ref_row["file"])
        enroll_embeddings[spk] = embed(ref_audio, ref_row["sr"])
        # remaining bonafide = genuine test trials, all spoof = impostor trials
        for row in v["bonafide"][1:]:
            trials.append({**row, "target_speaker": spk})
        for row in v["spoof"]:
            trials.append({**row, "target_speaker": spk})

    print(f"{len(trials)} test trials "
          f"({sum(1 for t in trials if t['label']=='bonafide')} genuine / "
          f"{sum(1 for t in trials if t['label']=='spoof')} spoof)")

    labels = np.array([1 if t["label"] == "spoof" else 0 for t in trials])

    print("\n--- pass 1: CLEAN baseline (CM only) ---")
    cm_scores_clean = []
    for t in trials:
        audio = load_audio(t["file"])
        cm_scores_clean.append(cm.spoof_score(audio, t["sr"]))
    cm_scores_clean = np.array(cm_scores_clean)
    eer_clean, _ = eer(cm_scores_clean, labels)

    print("--- pass 2: DEGRADED (Opus 8kbps + 5% packet loss), CM only ---")
    cm_scores_degraded = []
    spk_scores_degraded = []
    for t in trials:
        audio = load_audio(t["file"])
        degraded_audio, degraded_sr = degrade(audio, t["sr"], profile=DEGRADE_PROFILE, seed=42)
        cm_scores_degraded.append(cm.spoof_score(degraded_audio, degraded_sr))
        test_emb = embed(degraded_audio, degraded_sr)
        sim = similarity(enroll_embeddings[t["target_speaker"]], test_emb)
        spk_scores_degraded.append(1.0 - sim)  # higher = more impostor-like
    cm_scores_degraded = np.array(cm_scores_degraded)
    spk_scores_degraded = np.array(spk_scores_degraded)
    eer_degraded, _ = eer(cm_scores_degraded, labels)

    print("--- pass 3: DEGRADED + ENROLLMENT FUSION ---")
    # simple unweighted mean fusion -- no dev set available at pilot scale to
    # learn fusion weights; the full-scale run should fit logistic-regression
    # fusion on a held-out dev split instead (see runbook)
    fused_scores = (cm_scores_degraded + spk_scores_degraded) / 2.0
    eer_fused, _ = eer(fused_scores, labels)

    print("\n" + "=" * 60)
    print(f"PILOT RESULTS  (n={len(trials)} trials, {len(speakers)} speakers)")
    print("=" * 60)
    print(f"1. Clean baseline EER (CM only)........... {eer_clean*100:.1f}%")
    print(f"2. Degraded EER (CM only)................. {eer_degraded*100:.1f}%")
    print(f"3. Degraded + enrollment fusion EER....... {eer_fused*100:.1f}%")
    print("=" * 60)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = {
        "n_trials": len(trials),
        "n_speakers": len(speakers),
        "n_genuine": int((labels == 0).sum()),
        "n_spoof": int((labels == 1).sum()),
        "degrade_profile": DEGRADE_PROFILE,
        "eer_clean_cm_only": eer_clean,
        "eer_degraded_cm_only": eer_degraded,
        "eer_degraded_plus_enrollment": eer_fused,
        "note": "PILOT SCALE on ASVspoof2019 LA (English-centric benchmark, CPU-only "
                "inference, no GPU). Directionally honest, not statistically final. "
                "Full-scale run on Indian-language data happens on Kaggle -- see "
                "notebooks/kaggle_full_run.ipynb.",
    }
    with open(os.path.join(RESULTS_DIR, "pilot_results.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nsaved to {RESULTS_DIR}/pilot_results.json")


if __name__ == "__main__":
    main()
