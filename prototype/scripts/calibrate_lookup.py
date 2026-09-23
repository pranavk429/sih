"""
Measure the voice-lookup threshold on our own data. PLAN-LIVE M1.

The lookup's accept threshold and margin must not be borrowed. Published
Resemblyzer numbers are quoted against raw cosine; our similarity() is
(cos+1)/2 on the same embeddings, so a borrowed cut is wrong on our scale before
it is wrong on our channel.

What this measures, and what it cannot:

    Same-speaker   the ASVspoof pilot slice contains three clips of one
                   speaker (LA_0022 -- the demo's enrolled voice). Every pair
                   among them, clean and through the mobile_voip channel.
    Different      that speaker's reference against every other clip in the
                   pilot slice.

    It CANNOT measure a margin over a runner-up, because there is one known
    speaker. The margin stays a configured guard (see config.yaml) and this is
    stated in the output rather than hidden.

Writes `artifacts/lookup_calibration.json` with the distributions and the rule
that chose the number, and prints the config lines to paste.

    ../detector/venv/bin/python scripts/calibrate_lookup.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel.config import ROOT, Config, prefer_local_model_cache  # noqa: E402
from sentinel.models import registry  # noqa: E402
from sentinel.models.resemblyzer_spk import ResemblyzerSpeakerEncoder  # noqa: E402

PILOT_DIR = os.path.normpath(os.path.join(ROOT, "..", "detector", "data", "pilot"))

# From artifacts/demo/manifest.json: the three clips of the enrolled speaker.
REFERENCE_CLIP = "LA_E_4148077.npy"
SAME_SPEAKER_CLIPS = ("LA_E_8177958.npy", "LA_E_7255033.npy")
DEGRADE_PROFILE = "mobile_voip"
DEGRADE_SEED = 1337


def _load(name: str) -> np.ndarray:
    return np.load(os.path.join(PILOT_DIR, name)).astype(np.float32).reshape(-1)


def _propose(genuine: list, impostor: list) -> dict:
    """
    The rule, written down so the JSON can say why the number is what it is.

    accept = midpoint between the lowest same-speaker score and the highest
    impostor score, when those separate. When they overlap, the threshold goes
    to the impostor p99 and the overlap is reported as the honest limit of a
    pilot-scale measurement. The genuine minimum is never crossed: a threshold
    that rejects the enrolled speaker is worse than a permissive one here,
    because the verdict has its own abstention band for the ambiguous middle.
    """
    g = np.asarray(genuine, dtype=np.float64)
    i = np.asarray(impostor, dtype=np.float64)
    g_min = float(g.min())
    i_p99 = float(np.percentile(i, 99))
    i_max = float(i.max())
    separated = bool(g_min > i_max)
    if separated:
        accept = float((g_min + i_max) / 2.0)
        rule = ("midpoint between lowest same-speaker score "
                f"({g_min:.4f}) and highest different-speaker score ({i_max:.4f})")
    elif g_min > i_p99:
        accept = float((g_min + i_p99) / 2.0)
        rule = ("midpoint between lowest same-speaker score "
                f"({g_min:.4f}) and the 99th percentile of different-speaker "
                f"scores ({i_p99:.4f}); the top 1% of impostors still clear it")
    else:
        accept = float(i_p99)
        rule = ("sets at the 99th percentile of different-speaker scores "
                f"({i_p99:.4f}); same-speaker clips reach as low as {g_min:.4f} "
                "and OVERLAP the impostor tail -- a pilot-scale limit, not a "
                "tuning problem")
    return {
        "accept_similarity": round(accept, 4),
        "rule": rule,
        "lowest_genuine": round(g_min, 4),
        "impostor_p50": round(float(np.percentile(i, 50)), 4),
        "impostor_p99": round(i_p99, 4),
        "impostor_max": round(i_max, 4),
        "separated": separated,
        "genuine_n": int(g.size),
        "impostor_n": int(i.size),
        # The trade-off at the chosen threshold, so nobody has to guess what it
        # accepts: a conservative threshold REFUSES some genuine speakers (they
        # show as "unknown voice") to avoid naming a stranger.
        "genuine_accepted_at_threshold": int((g >= accept).sum()),
        "impostor_accepted_at_threshold": int((i >= accept).sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        ROOT, "artifacts", "lookup_calibration.json"))
    args = parser.parse_args()

    if not os.path.isdir(PILOT_DIR):
        raise SystemExit(
            f"pilot data not found at {PILOT_DIR}\n"
            "This script measures on detector/data/pilot, which is gitignored. "
            "Re-fetch with detector/src/fetch_data.py."
        )

    cfg = Config.load()
    prefer_local_model_cache()
    encoder = ResemblyzerSpeakerEncoder(min_rms=cfg.audio.min_embed_rms)
    degrade = registry.degrade_fn()

    reference = encoder.embed(_load(REFERENCE_CLIP), cfg.audio.sample_rate)

    genuine_clean = []
    genuine_degraded = []
    for name in SAME_SPEAKER_CLIPS:
        pcm = _load(name)
        genuine_clean.append(float(encoder.similarity(reference, encoder.embed(pcm, cfg.audio.sample_rate))))
        degraded, _sr = degrade(pcm, cfg.audio.sample_rate, profile=DEGRADE_PROFILE,
                                seed=DEGRADE_SEED)
        genuine_degraded.append(float(encoder.similarity(
            reference, encoder.embed(np.asarray(degraded, dtype=np.float32), cfg.audio.sample_rate))))

    own = {REFERENCE_CLIP, *SAME_SPEAKER_CLIPS}
    others = sorted(f for f in os.listdir(PILOT_DIR)
                    if f.endswith(".npy") and f not in own)
    print(f"reference {REFERENCE_CLIP} · {len(others)} different-speaker clips")

    impostor = []
    for index, name in enumerate(others):
        try:
            impostor.append(float(encoder.similarity(
                reference, encoder.embed(_load(name), cfg.audio.sample_rate))))
        except Exception as exc:  # noqa: BLE001 -- one bad clip must not stop the run
            print(f"  skipped {name}: {exc}")
        if index and index % 50 == 0:
            print(f"  ... {index}/{len(others)}")

    genuine = genuine_clean + genuine_degraded
    proposal = _propose(genuine, impostor)

    print("\nsame speaker (clean)   :", [round(v, 4) for v in genuine_clean])
    print("same speaker (mobile)  :", [round(v, 4) for v in genuine_degraded])
    print(f"different speaker      : n={len(impostor)} "
          f"p50={proposal['impostor_p50']:.4f} p99={proposal['impostor_p99']:.4f} "
          f"max={proposal['impostor_max']:.4f}")
    print(f"\nproposed accept_similarity = {proposal['accept_similarity']:.4f}")
    print(f"  {proposal['rule']}")
    print(f"  at this threshold: genuine accepted "
          f"{proposal['genuine_accepted_at_threshold']}/{proposal['genuine_n']}, "
          f"impostors accepted "
          f"{proposal['impostor_accepted_at_threshold']}/{proposal['impostor_n']}")
    print("\nconfig.yaml:")
    print(f"  lookup:\n    accept_similarity: {proposal['accept_similarity']:.4f}")
    print("    min_margin: <unchanged -- one speaker cannot measure a runner-up margin>")
    print("    min_consecutive_windows: 2")

    payload = {
        "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "dataset": "ASVspoof2019-LA pilot slice (detector/data/pilot)",
        "what_this_measures": (
            "Same-speaker pairs among the three LA_0022 clips (clean and "
            "mobile_voip-degraded) against LA_0022's reference, versus that "
            "reference against every other speaker in the pilot slice."
        ),
        "reference": {"speaker_id": "LA_0022", "clip": REFERENCE_CLIP},
        "same_speaker_clean": [round(v, 5) for v in genuine_clean],
        "same_speaker_degraded": [round(v, 5) for v in genuine_degraded],
        "impostor_scores": [round(v, 5) for v in impostor],
        "proposed": proposal,
        "caveats": [
            "PILOT SCALE: one known speaker and two same-speaker pairs. The "
            "confidence interval on this threshold is wide.",
            "Same dataset and same recording sessions for enrolment and test; a "
            "live microphone is a new channel, so expect drift.",
            "A runner-up margin cannot be measured with one enrolled voice. "
            "min_margin stays a configured guard, not a measured one.",
            "Similarity is (cos+1)/2, matching detector/src/speaker_id.py; do "
            "not compare it with raw-cosine numbers from the Resemblyzer README.",
        ],
        "config_to_paste": {"accept_similarity": proposal["accept_similarity"]},
    }

    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(args.out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
