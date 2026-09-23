"""
Measure every synthetic asset against the real pipeline. PLAN-LIVE M4.

This is the gate that keeps the clone demo honest. A modern neural clone is
exactly the "new tool" from Truth 1 in PROJECT-EXPLAINED.md, and a detector
fitted on ASVspoof2019-LA may not catch it. So the demo plays what this report
says is caught, and the report's misses go on the limitations slide.

For every WAV under artifacts/clones/ and every demo call, it runs the same
3 s / 0.5 s windows, VAD, probe countermeasure and speaker check the live
pipeline uses, and writes `artifacts/clone_report.json`:

    per file: mean / max fused risk over voiced windows, the fraction of
              windows above the evidence floor, and honest_fused = the same
              arithmetic with any missing signal treated as MISSING (a clone
              with no speaker reference is judged on the countermeasure alone).

It measures. It does not tune, and it does not assert.

    ../detector/venv/bin/python scripts/make_clone_report.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel.audio.framing import Framer  # noqa: E402
from sentinel.audio.resample import prepare  # noqa: E402
from sentinel.audio.vad import EnergyVad  # noqa: E402
from sentinel.config import ROOT, Config  # noqa: E402
from sentinel.decision.calibration import Calibration  # noqa: E402
from sentinel.enrolment.store import EnrolmentStore  # noqa: E402
from sentinel.models import registry  # noqa: E402

CLONE_DIR = os.path.join(ROOT, "artifacts", "clones")
CLONE_MANIFEST = os.path.join(CLONE_DIR, "manifest.json")


def _assets(cfg) -> list:
    out = []
    manifest = {"assets": []}
    if os.path.exists(CLONE_MANIFEST):
        with open(CLONE_MANIFEST) as fh:
            manifest = json.load(fh)
    for asset in manifest.get("assets", []):
        path = os.path.join(CLONE_DIR, asset["file"])
        if os.path.exists(path):
            out.append({**asset, "path": path})
    demo_manifest_path = os.path.join(cfg.paths.demo_dir, "manifest.json")
    if os.path.exists(demo_manifest_path):
        with open(demo_manifest_path) as fh:
            demo = json.load(fh)
        for call in demo.get("calls", []):
            path = os.path.join(cfg.paths.demo_dir, call["file"])
            if os.path.exists(path):
                out.append({
                    "id": call["id"], "path": path,
                    "generator": "ASVspoof2019-LA",
                    "generator_detail": f"dataset {call.get('degrade_profile') or 'clean'}",
                    "ground_truth": ("bonafide" if call["ground_truth"] == "bonafide"
                                     else "spoof_dataset"),
                    "file": call["file"],
                })
    return out


def _frame_source(path, cfg):
    pcm, sr = sf.read(path, dtype="float32", always_2d=False)
    pcm = prepare(pcm, sr, cfg.audio.sample_rate)
    from sentinel.types import Frame

    n = int(cfg.audio.sample_rate * cfg.audio.frame_ms / 1000)
    for seq, start in enumerate(range(0, max(0, len(pcm) - n + 1), n)):
        yield Frame(pcm=pcm[start:start + n], sr=cfg.audio.sample_rate,
                    t_start_ms=int(round(start / cfg.audio.sample_rate * 1000)), seq=seq)


def measure(path, cfg, cm, spk, reference, vad) -> dict:
    framer = Framer(sample_rate=cfg.audio.sample_rate, window_s=cfg.audio.window_s,
                    hop_s=cfg.audio.hop_s)
    cm_scores, spk_scores, fused = [], [], []
    for frame in _frame_source(path, cfg):
        for window in framer.push(frame):
            is_speech, _ratio = vad.measure(window.pcm, window.sr)
            if not is_speech:
                continue
            cm_risk = None
            try:
                cm_risk = float(cm.risk(window.pcm, window.sr))
            except Exception:  # noqa: BLE001
                pass
            spk_risk = None
            if reference is not None:
                try:
                    spk_risk = float(spk.risk(reference, spk.embed(window.pcm, window.sr)))
                except Exception:  # noqa: BLE001
                    pass
            usable = [v for v in (cm_risk, spk_risk) if v is not None]
            if not usable:
                continue
            if cm_risk is not None:
                cm_scores.append(cm_risk)
            if spk_risk is not None:
                spk_scores.append(spk_risk)
            fused.append(float(np.mean(usable)))

    fused_arr = np.asarray(fused, dtype=np.float64) if fused else np.zeros(0)
    return {
        "windows": int(fused_arr.size),
        "mean_fused": round(float(fused_arr.mean()), 4) if fused_arr.size else None,
        "max_fused": round(float(fused_arr.max()), 4) if fused_arr.size else None,
        "mean_cm": round(float(np.mean(cm_scores)), 4) if cm_scores else None,
        "mean_speaker": round(float(np.mean(spk_scores)), 4) if spk_scores else None,
        "fraction_above_floor": round(float((fused_arr >= cfg.decision.evidence_risk_floor).mean()), 3)
        if fused_arr.size else None,
        "caught": bool(fused_arr.size and fused_arr.mean() >= cfg.decision.low_thr),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(ROOT, "artifacts", "clone_report.json"))
    args = parser.parse_args()

    cfg = Config.load()
    cal = Calibration.load(cfg.models.calibration_path)
    cm, spk = registry.build_models(cfg)
    vad = EnergyVad(cfg.audio)

    reference = None
    demo_manifest = os.path.join(cfg.paths.demo_dir, "manifest.json")
    if os.path.exists(demo_manifest):
        with open(demo_manifest) as fh:
            speaker_id = json.load(fh).get("speaker_id")
        if speaker_id:
            reference = EnrolmentStore(cfg.paths.enrolments_dir).get(speaker_id)
    if reference is None:
        print("! no enrolment found -- files are judged on the countermeasure alone")

    assets = _assets(cfg)
    if not assets:
        raise SystemExit(
            "no assets found. Generate some first:\n"
            "  scripts/make_clone_assets.py --say\n"
            "  scripts/make_clone_assets.py --from-file <clone.wav> --source-speaker ... --consent ..."
        )

    print(f"band [{cfg.decision.low_thr}, {cfg.decision.high_thr}] · "
          f"evidence floor {cfg.decision.evidence_risk_floor} · "
          f"calibration {cal.calibration_id}\n")
    print(f"{'asset':22s} {'truth':16s} {'win':>4s} {'fused':>7s} {'max':>7s} "
          f"{'cm':>7s} {'spk':>7s}  verdict")
    print("-" * 96)

    results = []
    for asset in assets:
        row = measure(asset["path"], cfg, cm, spk, reference, vad)
        verdict = ("CAUGHT (above the band)" if row["mean_fused"] is not None
                   and row["mean_fused"] >= cfg.decision.high_thr
                   else "above low_thr, in the abstention band"
                   if row["mean_fused"] is not None
                   and row["mean_fused"] >= cfg.decision.low_thr
                   else "BELOW the band — not caught by this pipeline")
        results.append({
            "id": asset.get("id"),
            "file": asset.get("file"),
            "ground_truth": asset.get("ground_truth"),
            "generator": asset.get("generator"),
            "generator_detail": asset.get("generator_detail"),
            "source_speaker": asset.get("source_speaker"),
            "consent": asset.get("consent"),
            "measured": row,
            "verdict": verdict,
        })
        print(f"{str(asset.get('id'))[:22]:22s} {str(asset.get('ground_truth'))[:16]:16s} "
              f"{row['windows']:4d} "
              f"{(row['mean_fused'] if row['mean_fused'] is not None else float('nan')):7.3f} "
              f"{(row['max_fused'] if row['max_fused'] is not None else float('nan')):7.3f} "
              f"{(row['mean_cm'] if row['mean_cm'] is not None else float('nan')):7.3f} "
              f"{(row['mean_speaker'] if row['mean_speaker'] is not None else float('nan')):7.3f}  "
              f"{verdict}")

    payload = {
        "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "calibration_id": cal.calibration_id,
        "band": [cfg.decision.low_thr, cfg.decision.high_thr],
        "evidence_risk_floor": cfg.decision.evidence_risk_floor,
        "enrolled_reference": reference is not None,
        "method": "the live pipeline's own framing, VAD, probe CM and speaker check; "
                  "fused = mean of the usable signals per window",
        "assets": results,
        "caveats": [
            "Mean fused risk per file, not a per-window decision. The pipeline's "
            "verdict also depends on a trigger and gating.",
            "A file below the band is a MISS for this calibration. Say so; do not "
            "demo it as caught.",
            "Speaker risk barely separates a voice conversion aimed at the "
            "enrolled speaker; the countermeasure is the signal doing the work.",
        ],
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(args.out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
