"""
Build the three demo WAVs: an enrolment clip, a genuine call, an attack call.

SPEC §11, safe path: detector/data/pilot/ holds ASVspoof2019-LA clips -- genuine
and spoofed recordings OF THE SAME SPEAKERS, with ground truth. Zero setup risk.

One thing the plan did not anticipate: those clips are short. Median 2.9s, max
7.9s, and the best-provisioned speaker has only ~12s of non-enrolment audio.
A demo that has to show monitoring -> trigger -> pre-roll -> verdict inside 12
seconds looks rushed and leaves the risk timeline almost empty.

So a "call" here is a concatenation of that speaker's clips separated by line
noise, cycling through them again if needed to reach the target duration. Every
segment -- including every repeat -- is written into manifest.json with its
source file and its repeat index. Nothing is hidden; a judge who asks "where did
35 seconds of audio come from?" gets an exact answer from the manifest.

The enrolment clip stays CLEAN and the calls are degraded, which is also what
happens in reality: you enrol once in a branch on a decent microphone, and then
the calls arrive over a mobile network.

    ../detector/venv/bin/python scripts/make_demo_calls.py
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

from sentinel.config import ROOT, Config  # noqa: E402
from sentinel.models import registry  # noqa: E402

PILOT_DIR = os.path.normpath(os.path.join(ROOT, "..", "detector", "data", "pilot"))
DEGRADE_PROFILE = "mobile_voip"
DEGRADE_SEED = 1337
# Line noise between segments: audible as a live line, far below the VAD floor
# (config audio.vad_rms_floor = 0.006) so those windows correctly report SILENT.
NOISE_RMS = 0.0008
GAP_MIN_S, GAP_MAX_S = 0.45, 0.95


def load_audio(fname: str) -> np.ndarray:
    return np.load(os.path.join(PILOT_DIR, fname)).astype(np.float32)


def duration_s(row) -> float:
    return len(load_audio(row["file"])) / row["sr"]


def pick_speaker(manifest, forced=None):
    """
    The speaker who gives the demo the most room.

    Needs >=2 bonafide (one is spent on enrolment) and >=1 spoof. Among those,
    maximise the smaller of the two call pools -- a speaker with 15s of genuine
    audio and 3s of spoof makes a lopsided pair of demo calls.
    """
    by_speaker = {}
    for row in manifest:
        by_speaker.setdefault(row["speaker_id"], {"bonafide": [], "spoof": []})
        by_speaker[row["speaker_id"]][row["label"]].append(row)

    candidates = []
    for spk, v in by_speaker.items():
        if len(v["bonafide"]) < 2 or not v["spoof"]:
            continue
        bona = sorted(v["bonafide"], key=duration_s, reverse=True)
        enrol, spare = bona[0], bona[1:]
        genuine_pool = sum(duration_s(r) for r in spare)
        spoof_pool = sum(duration_s(r) for r in v["spoof"])
        candidates.append(
            {
                "speaker_id": spk,
                "enrol": enrol,
                "genuine": spare,
                "spoof": v["spoof"],
                "enrol_s": duration_s(enrol),
                "genuine_s": genuine_pool,
                "spoof_s": spoof_pool,
                "score": min(genuine_pool, spoof_pool) + 0.25 * duration_s(enrol),
            }
        )
    if not candidates:
        raise RuntimeError("no speaker in the pilot slice has >=2 bonafide and >=1 spoof")

    if forced:
        for c in candidates:
            if c["speaker_id"] == forced:
                return c, candidates
        raise SystemExit(f"speaker {forced} is not a usable demo speaker")
    return max(candidates, key=lambda c: c["score"]), candidates


def build_call(rows, target_s: float, sr: int, rng: np.random.Generator):
    """
    Concatenate clips with line-noise gaps until target_s, cycling if short.

    Returns (pcm, segments) where every segment records where its audio came
    from and, if the pool had to be reused, which pass it was on.
    """
    chunks, segments = [], []
    t_ms, i = 0, 0
    while t_ms < target_s * 1000:
        row = rows[i % len(rows)]
        audio = load_audio(row["file"])
        chunks.append(audio)
        seg_ms = int(round(len(audio) / sr * 1000))
        segments.append(
            {
                "t_start_ms": t_ms,
                "t_end_ms": t_ms + seg_ms,
                "source": row["file"],
                "label": row["label"],
                "repeat": i // len(rows),
            }
        )
        t_ms += seg_ms
        i += 1
        if t_ms >= target_s * 1000:
            break
        gap_s = float(rng.uniform(GAP_MIN_S, GAP_MAX_S))
        gap_n = int(gap_s * sr)
        chunks.append(rng.normal(0.0, NOISE_RMS, gap_n).astype(np.float32))
        t_ms += int(round(gap_s * 1000))

    pcm = np.concatenate(chunks).astype(np.float32)
    return pcm, segments


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--speaker", default=None, help="force a speaker id, e.g. LA_0022")
    ap.add_argument("--target-s", type=float, default=35.0)
    args = ap.parse_args()

    cfg = Config.load(args.config)
    degrade = registry.degrade_fn()
    sr = cfg.audio.sample_rate

    with open(os.path.join(PILOT_DIR, "manifest.json")) as fh:
        manifest = json.load(fh)

    chosen, candidates = pick_speaker(manifest, args.speaker)
    print(f"{len(candidates)} usable demo speakers; picked {chosen['speaker_id']}")
    print(f"  enrolment clip : {chosen['enrol_s']:.1f}s  ({chosen['enrol']['file']})")
    print(f"  genuine pool   : {chosen['genuine_s']:.1f}s across {len(chosen['genuine'])} clips")
    print(f"  spoof pool     : {chosen['spoof_s']:.1f}s across {len(chosen['spoof'])} clips")
    print(f"  target call    : {args.target_s:.0f}s (pools are cycled to reach it)\n")

    out_dir = cfg.paths.demo_dir
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(DEGRADE_SEED)

    # Enrolment: clean, as a branch recording would be.
    enrol_pcm = load_audio(chosen["enrol"]["file"])
    sf.write(os.path.join(out_dir, "enrol.wav"), enrol_pcm, sr)
    print(f"enrol.wav    {len(enrol_pcm)/sr:5.1f}s  clean (enrolment is not a phone call)")

    calls = []
    for call_id, rows, truth, title in (
        ("genuine", chosen["genuine"], "bonafide",
         "Genuine call — the enrolled speaker, over a mobile line"),
        ("attack", chosen["spoof"], "spoof",
         "Attack call — synthesised voice of the same speaker"),
    ):
        pcm, segments = build_call(rows, args.target_s, sr, rng)
        degraded, deg_sr = degrade(pcm, sr, profile=DEGRADE_PROFILE, seed=DEGRADE_SEED)
        if deg_sr != sr:
            raise RuntimeError(f"{DEGRADE_PROFILE} returned {deg_sr}Hz, expected {sr}Hz")
        path = os.path.join(out_dir, f"{call_id}.wav")
        sf.write(path, degraded, deg_sr)
        repeats = max(s["repeat"] for s in segments)
        print(f"{call_id + '.wav':12s} {len(degraded)/deg_sr:5.1f}s  "
              f"{DEGRADE_PROFILE}  {len(segments)} segments"
              f"{f' ({repeats + 1} passes over a {len(rows)}-clip pool)' if repeats else ''}")
        calls.append(
            {
                "id": call_id,
                "title": title,
                "file": f"{call_id}.wav",
                "ground_truth": truth,
                "duration_s": round(len(degraded) / deg_sr, 3),
                "degraded": True,
                "degrade_profile": DEGRADE_PROFILE,
                "segments": segments,
                "source_clips": sorted({s["source"] for s in segments}),
                "passes_over_pool": repeats + 1,
            }
        )

    demo_manifest = {
        "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "dataset": "ASVspoof2019-LA pilot slice",
        "speaker_id": chosen["speaker_id"],
        "sample_rate": sr,
        "degrade_profile": DEGRADE_PROFILE,
        "degrade_seed": DEGRADE_SEED,
        "target_duration_s": args.target_s,
        "enrolment": {
            "file": "enrol.wav",
            "source": chosen["enrol"]["file"],
            "duration_s": round(len(enrol_pcm) / sr, 3),
            "degraded": False,
        },
        "calls": calls,
        "honesty": (
            "Simulated live call. These are recorded ASVspoof2019-LA clips from "
            "one speaker, concatenated with line-noise gaps and cycled to reach "
            f"{args.target_s:.0f}s, then passed through a {DEGRADE_PROFILE} "
            "channel simulation. Every segment and every repeat is listed above. "
            "This is not a live phone call and must never be described as one."
        ),
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(demo_manifest, fh, indent=2)
    print(f"\nmanifest.json written to {out_dir}")
    print("Listen to genuine.wav and attack.wav — you should hear the phone-line "
          "degradation, and the attack clip should sound like the same person.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
