"""
Fit the linear probe exactly as the pilot experiment does, then PERSIST it.

Closes SPEC Gap 1. detector/src/run_experiment_v2.py fits a LogisticRegression
in memory and throws it away. A live system cannot refit on startup, so this
script does the same fit and writes out:

    artifacts/probe_head.npz    coef_, intercept_, provenance
    artifacts/calibration.json  eer threshold, per-class score stats,
                                fusion weights, and where all of it came from

The acceptance criterion from IMPLEMENTATION-PLAN 0.3 is the important part:
after saving, we RELOAD the head through the production code path
(sentinel.models.probe_cm.LogisticHead) and re-score the same test trials. The
fused EER must reproduce the experiment's to within 0.1pp. If persistence is
subtly wrong -- a transposed coefficient vector, a dropped intercept -- it shows
up here on day 0 rather than as a mysteriously inverted verdict on day 3.

    ../detector/venv/bin/python scripts/fit_probe.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel.config import ROOT, Config  # noqa: E402
from sentinel.models import registry  # noqa: E402
from sentinel.models.probe_cm import LogisticHead  # noqa: E402

# The number run_experiment_v2.py produced, which slide 4 quotes.
REFERENCE_RESULTS = os.path.normpath(
    os.path.join(ROOT, "..", "detector", "results", "pilot_results_v2_leakfree.json")
)
DEGRADE_PROFILE = "mobile_voip"
DEGRADE_SEED = 42
TOLERANCE_PP = 0.1  # percentage points


def _pilot_dir() -> str:
    return os.path.normpath(os.path.join(ROOT, "..", "detector", "data", "pilot"))


def load_audio(fname: str) -> np.ndarray:
    return np.load(os.path.join(_pilot_dir(), fname)).astype(np.float32)


def split_fit_test(manifest):
    """
    The speaker-disjoint split from run_experiment_v2.py, unchanged.

    TEST speakers are those with >=2 bonafide (one becomes the enrolment
    reference) and >=1 spoof. FIT is everyone else. Any overlap is leakage and
    invalidates every number below, so it is asserted, not assumed.
    """
    by_speaker = {}
    for row in manifest:
        by_speaker.setdefault(row["speaker_id"], {"bonafide": [], "spoof": []})
        by_speaker[row["speaker_id"]][row["label"]].append(row)

    test_speakers = {
        spk: v
        for spk, v in by_speaker.items()
        if len(v["bonafide"]) >= 2 and len(v["spoof"]) >= 1
    }
    fit_rows = [r for r in manifest if r["speaker_id"] not in test_speakers]

    overlap = set(r["speaker_id"] for r in fit_rows) & set(test_speakers)
    assert not overlap, f"speaker leakage between fit/test: {overlap}"
    return fit_rows, test_speakers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument(
        "--tolerance-pp",
        type=float,
        default=TOLERANCE_PP,
        help="max allowed EER drift vs the experiment, in percentage points",
    )
    args = ap.parse_args()

    cfg = Config.load(args.config)
    from sklearn.linear_model import LogisticRegression

    degrade = registry.degrade_fn()
    eer = registry.eer_fn()
    spk_embed, similarity = registry.speaker_fns()

    with open(os.path.join(_pilot_dir(), "manifest.json")) as fh:
        manifest = json.load(fh)

    fit_rows, test_speakers = split_fit_test(manifest)
    n_fit_speakers = len(set(r["speaker_id"] for r in fit_rows))
    print(f"FIT  : {n_fit_speakers} speakers, {len(fit_rows)} files")
    print(f"TEST : {len(test_speakers)} speakers (speaker-disjointness verified)\n")

    print(f"loading task-naive backbone ({cfg.models.cm_backbone_id})...")
    backbone = registry.probe_backbone(cfg.models.device, model_id=cfg.models.cm_backbone_id)

    print("extracting FIT embeddings...")
    X_fit, y_fit = [], []
    for row in fit_rows:
        X_fit.append(backbone.embed(load_audio(row["file"]), row["sr"]))
        y_fit.append(1 if row["label"] == "spoof" else 0)
    X_fit, y_fit = np.array(X_fit), np.array(y_fit)

    print("fitting logistic probe...")
    clf = LogisticRegression(max_iter=2000, C=1.0)
    clf.fit(X_fit, y_fit)
    train_acc = float(clf.score(X_fit, y_fit))
    print(f"  fit-set training accuracy: {train_acc * 100:.1f}% (n={len(y_fit)})\n")

    # Test trials, built exactly as the experiment builds them.
    trials, enroll_embeddings = [], {}
    for spk, v in test_speakers.items():
        ref_row = v["bonafide"][0]
        enroll_embeddings[spk] = spk_embed(load_audio(ref_row["file"]), ref_row["sr"])
        for row in v["bonafide"][1:] + v["spoof"]:
            trials.append({**row, "target_speaker": spk})
    labels = np.array([1 if t["label"] == "spoof" else 0 for t in trials])
    print(f"{len(trials)} TEST trials ({int((labels == 0).sum())} genuine / "
          f"{int((labels == 1).sum())} spoof)")

    # --- persist, then score through the PRODUCTION load path -------------
    head = LogisticHead(clf.coef_, float(clf.intercept_[0]))
    head_path = cfg.models.probe_head_path
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    head.save(
        head_path,
        backbone=cfg.models.cm_backbone_id,
        created_utc=created,
        n_fit_examples=int(len(y_fit)),
        n_fit_speakers=n_fit_speakers,
        fit_train_accuracy=train_acc,
        sklearn_C=1.0,
    )
    print(f"\nsaved {head_path}")

    reloaded = LogisticHead.load(head_path)
    print("re-scoring TEST trials through the RELOADED head "
          "(this is the persistence check, not a formality)...")

    cm_degraded, spk_degraded = [], []
    for t in trials:
        audio = load_audio(t["file"])
        deg, deg_sr = degrade(audio, t["sr"], profile=DEGRADE_PROFILE, seed=DEGRADE_SEED)
        cm_degraded.append(reloaded.proba(backbone.embed(deg, deg_sr)))
        sim = similarity(enroll_embeddings[t["target_speaker"]], spk_embed(deg, deg_sr))
        spk_degraded.append(1.0 - sim)  # risk orientation, as resemblyzer_spk does
    cm_degraded = np.array(cm_degraded)
    spk_degraded = np.array(spk_degraded)

    fused = (cm_degraded + spk_degraded) / 2.0
    eer_cm, thr_cm = eer(cm_degraded, labels)
    eer_fused, thr_fused = eer(fused, labels)

    print(f"\n  degraded CM-only EER  : {eer_cm * 100:.2f}%")
    print(f"  degraded fused EER    : {eer_fused * 100:.2f}%  (threshold {thr_fused:.4f})")

    # --- the acceptance criterion ----------------------------------------
    with open(REFERENCE_RESULTS) as fh:
        reference = json.load(fh)
    expected = float(reference["eer_degraded_plus_enrollment"])
    drift_pp = abs(eer_fused - expected) * 100
    print(f"\n  experiment reported   : {expected * 100:.2f}%")
    print(f"  drift after persist   : {drift_pp:.3f} pp (tolerance {args.tolerance_pp} pp)")
    if drift_pp > args.tolerance_pp:
        print(
            "\nFAIL: the persisted head does not reproduce the experiment.\n"
            "Something is wrong with persistence -- find it now, not on day 3.",
            file=sys.stderr,
        )
        return 1
    print("  PASS: persisted head reproduces the experiment.")

    # --- the abstention band ----------------------------------------------
    # SPEC §7.4 makes UNCERTAIN a first-class outcome, so the band around the
    # EER threshold has to come from the data rather than from taste. Rule:
    # widen from the EER threshold by half a standard deviation of each class,
    # in the direction of that class. Written into calibration.json so
    # config.yaml can cite where its thresholds came from.
    bona = fused[labels == 0]
    spoof_f = fused[labels == 1]
    low_thr = float(max(0.0, thr_fused - 0.5 * bona.std()))
    high_thr = float(min(1.0, thr_fused + 0.5 * spoof_f.std()))
    outcomes = {
        "genuine_verified": int((bona < low_thr).sum()),
        "genuine_uncertain": int(((bona >= low_thr) & (bona <= high_thr)).sum()),
        "genuine_flagged": int((bona > high_thr).sum()),
        "spoof_flagged": int((spoof_f > high_thr).sum()),
        "spoof_uncertain": int(((spoof_f >= low_thr) & (spoof_f <= high_thr)).sum()),
        "spoof_verified": int((spoof_f < low_thr).sum()),
    }
    print(f"\n  abstention band       : [{low_thr:.4f}, {high_thr:.4f}] around EER threshold")
    print(f"    genuine  -> verified {outcomes['genuine_verified']:3d} | "
          f"uncertain {outcomes['genuine_uncertain']:3d} | flagged {outcomes['genuine_flagged']:3d}")
    print(f"    spoof    -> flagged  {outcomes['spoof_flagged']:3d} | "
          f"uncertain {outcomes['spoof_uncertain']:3d} | verified {outcomes['spoof_verified']:3d}")

    # --- calibration.json -------------------------------------------------
    cal = {
        "created_utc": created,
        "dataset": "ASVspoof2019-LA pilot slice",
        "degrade_profile": DEGRADE_PROFILE,
        "n_fit_examples": int(len(y_fit)),
        "n_fit_speakers": n_fit_speakers,
        "n_test_trials": int(len(trials)),
        "n_test_speakers": len(test_speakers),
        "backbone": cfg.models.cm_backbone_id,
        "speaker_encoder": "resemblyzer-voice-encoder-v1",
        "eer": round(float(eer_fused), 6),
        "eer_threshold": round(float(thr_fused), 6),
        "cm_only": {"eer": round(float(eer_cm), 6), "eer_threshold": round(float(thr_cm), 6)},
        "score_stats": {
            "cm": _class_stats(cm_degraded, labels),
            "speaker": _class_stats(spk_degraded, labels),
            "fused": _class_stats(fused, labels),
        },
        "fusion": {"strategy": "mean", "weights": [0.5, 0.5]},
        "decision_band": {
            "low_thr": round(low_thr, 6),
            "high_thr": round(high_thr, 6),
            "rule": "eer_threshold -/+ 0.5 * per-class fused std",
            "outcomes_on_test_trials": outcomes,
            "note": "Copy these into config.yaml decision.low_thr/high_thr. "
                    "Anything between them is UNCERTAIN, which is the system "
                    "working, not failing.",
        },
        "reproduction_check": {
            "reference_file": os.path.relpath(REFERENCE_RESULTS, os.path.dirname(head_path)),
            "expected_eer": expected,
            "observed_eer": round(float(eer_fused), 6),
            "drift_pp": round(drift_pp, 4),
            "tolerance_pp": args.tolerance_pp,
        },
        "notes": (
            "PILOT SCALE — 119 test trials, 25 test speakers, English-only "
            "benchmark, CPU/MPS. Directionally honest, not statistically final. "
            "Replace this file when the Kaggle full run lands; every verdict in "
            "the evidence log carries the calibration_id it was decided under, "
            "so old decisions stay attributable to the old calibration."
        ),
    }
    cal_path = cfg.models.calibration_path
    os.makedirs(os.path.dirname(cal_path), exist_ok=True)
    with open(cal_path, "w") as fh:
        json.dump(cal, fh, indent=2)
    cal_id = hashlib.sha256(json.dumps(cal, sort_keys=True).encode()).hexdigest()[:12]
    print(f"\nsaved {cal_path}")
    print(f"calibration_id: {cal_id}")
    return 0


def _class_stats(scores: np.ndarray, labels: np.ndarray):
    return {
        "bonafide": {
            "mean": round(float(scores[labels == 0].mean()), 6),
            "std": round(float(scores[labels == 0].std()), 6),
        },
        "spoof": {
            "mean": round(float(scores[labels == 1].mean()), 6),
            "std": round(float(scores[labels == 1].std()), 6),
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
