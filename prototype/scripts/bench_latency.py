"""
End-of-trigger-phrase -> verdict-on-screen latency (SPEC §10, IMPLEMENTATION-
PLAN 4.4).

A measurement tool, not a gate -- SPEC §9 is explicit that this asserts
nothing. Whatever number the machine produces is the number to quote.

The trigger fires at a known stream time (config.yaml's
trigger.scripted_overlay: 16000 / 21000 / 26000 ms), so this is timeable
without instrumenting the UI: replay the demo call flat out (realtime=False,
same as test_pipeline_golden.py -- audio-clock time is irrelevant here, only
wall-clock compute time is), and record the wall-clock moment the first
trigger fires and the wall-clock moment the verdict first reaches the call's
decisive state (LIKELY_IMPERSONATION for the attack call, VERIFIED for a
genuine one). The gap between those two moments is real CPU time actually
spent scoring windows and deciding -- the sum of exactly the per-stage costs
SPEC §10's budget table lists.

ASR is off, for the same reason test_pipeline_golden.py keeps it off: the
scripted overlay fires independently of transcription, and faster-whisper is
the one non-deterministic, highly variable stage. This isolates deep-
verification latency from ASR latency rather than conflating the two.

    python scripts/bench_latency.py [--runs 10] [--demo attack]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _percentile(sorted_values, pct: float) -> float:
    """Nearest-rank percentile. No numpy needed for ten numbers."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = min(len(sorted_values) - 1, int(round(pct * (len(sorted_values) - 1))))
    return sorted_values[idx]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--demo", default="attack", help="demo id from artifacts/demo/manifest.json")
    ap.add_argument("--out", default="artifacts/latency.json")
    args = ap.parse_args()

    from sentinel.audio.source import FileSource
    from sentinel.cli import build_runtime, demo_manifest
    from sentinel.config import Config
    from sentinel.enrolment.store import EnrolmentStore
    from sentinel.types import LIKELY_IMPERSONATION, VERIFIED

    cfg = Config.load()
    manifest = demo_manifest(cfg)
    if manifest is None:
        raise SystemExit("no demo manifest -- run: python scripts/make_demo_calls.py")
    call = next((c for c in manifest["calls"] if c["id"] == args.demo), None)
    if call is None:
        ids = ", ".join(c["id"] for c in manifest["calls"])
        raise SystemExit(f"unknown demo {args.demo!r}; available: {ids}")

    path = os.path.join(cfg.paths.demo_dir, call["file"])
    ground_truth = call["ground_truth"]
    decisive_state = LIKELY_IMPERSONATION if ground_truth == "spoof" else VERIFIED

    speaker_id = manifest["speaker_id"]
    reference = EnrolmentStore(cfg.paths.enrolments_dir).get(speaker_id)
    if reference is None:
        raise SystemExit(
            f"{speaker_id} is not enrolled -- run: "
            "python -m sentinel.cli enrol --demo enrol"
        )

    print(f"loading models (once, {args.runs} runs will reuse them)...")
    orchestrator, cal = build_runtime(cfg, with_asr=False)

    print(f"\n{call['title']}  ({path})")
    print(f"ground truth: {ground_truth}  ->  decisive state: {decisive_state}")
    print("-" * 68)

    samples_ms = []
    trigger_stream_ms = None

    for i in range(args.runs):
        source = FileSource(
            path,
            sample_rate=cfg.audio.sample_rate,
            frame_ms=cfg.audio.frame_ms,
            realtime=False,
        )
        marks = {}

        def on_event(event, marks=marks):
            kind = event.get("type")
            if kind == "trigger" and "trigger_wall" not in marks:
                marks["trigger_wall"] = time.monotonic()
                marks["trigger_t_ms"] = event["t_ms"]
            elif (
                kind == "verdict"
                and event["state"] == decisive_state
                and "verdict_wall" not in marks
            ):
                marks["verdict_wall"] = time.monotonic()

        orchestrator.run(
            source, reference_embedding=reference, speaker_id=speaker_id,
            ground_truth=ground_truth, on_event=on_event,
        )
        source.close()

        if "trigger_wall" not in marks or "verdict_wall" not in marks:
            print(f"  run {i + 1:2d}: trigger or {decisive_state} never reached -- skipped")
            continue

        latency_ms = (marks["verdict_wall"] - marks["trigger_wall"]) * 1000
        samples_ms.append(latency_ms)
        trigger_stream_ms = marks["trigger_t_ms"]
        print(f"  run {i + 1:2d}: trigger at stream {marks['trigger_t_ms']} ms "
              f"-> {decisive_state} after {latency_ms:.0f} ms wall clock")

    if not samples_ms:
        raise SystemExit("no successful runs -- nothing to report")

    samples_ms.sort()
    median_ms = statistics.median(samples_ms)
    p95_ms = _percentile(samples_ms, 0.95)

    print("-" * 68)
    print(f"n={len(samples_ms)}  median={median_ms:.0f} ms  p95={p95_ms:.0f} ms  "
          f"min={samples_ms[0]:.0f} ms  max={samples_ms[-1]:.0f} ms")
    print(f"SPEC §10 target: < 1500 ms")

    result = {
        "measured_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "demo": args.demo,
        "file": os.path.basename(path),
        "ground_truth": ground_truth,
        "decisive_state": decisive_state,
        "trigger_stream_ms": trigger_stream_ms,
        "n_runs": len(samples_ms),
        "n_requested": args.runs,
        "samples_ms": [round(v, 1) for v in samples_ms],
        "median_ms": round(median_ms, 1),
        "p95_ms": round(p95_ms, 1),
        "min_ms": round(samples_ms[0], 1),
        "max_ms": round(samples_ms[-1], 1),
        "target_ms": 1500,
        "calibration_id": cal.calibration_id,
        "note": (
            "Wall-clock time from the first trigger event to the first verdict "
            "in the call's decisive state, replayed flat out (realtime=False) "
            "with ASR off. This is a measurement, not an assertion -- SPEC §9."
        ),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    print(f"\nwritten: {os.path.relpath(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
