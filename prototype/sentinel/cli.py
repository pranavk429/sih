"""
sentinel — the command line.

    sentinel enrol  --speaker LA_0022 --audio artifacts/demo/enrol.wav
    sentinel scores --audio artifacts/demo/genuine.wav --speaker LA_0022
    sentinel run    --demo attack --console
    sentinel serve

Run it as a module so imports resolve without installing the package:

    ../detector/venv/bin/python -m sentinel.cli scores --demo genuine
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel.audio.framing import Framer  # noqa: E402
from sentinel.audio.source import FileSource, MicSource  # noqa: E402
from sentinel.audio.vad import EnergyVad  # noqa: E402
from sentinel.config import Config  # noqa: E402
from sentinel.enrolment.store import EnrolmentStore  # noqa: E402
from sentinel.models import registry  # noqa: E402
from sentinel.models.resemblyzer_spk import SilentAudio  # noqa: E402

DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"


def _colour(enabled: bool):
    if enabled and sys.stdout.isatty():
        return lambda code, text: f"{code}{text}{RESET}"
    return lambda code, text: text


def demo_manifest(cfg: Config) -> Optional[dict]:
    path = os.path.join(cfg.paths.demo_dir, "manifest.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def resolve_audio(cfg: Config, audio: Optional[str], demo: Optional[str]) -> str:
    """--audio takes a path; --demo takes an id from the demo manifest."""
    if audio and demo:
        raise SystemExit("use --audio or --demo, not both")
    if audio:
        return audio
    manifest = demo_manifest(cfg)
    if manifest is None:
        raise SystemExit(
            "no demo manifest -- run: python scripts/make_demo_calls.py"
        )
    ids = [c["id"] for c in manifest["calls"]] + ["enrol"]
    if demo is None:
        raise SystemExit(f"pass --audio <wav> or --demo <{'|'.join(ids)}>")
    if demo == "enrol":
        return os.path.join(cfg.paths.demo_dir, manifest["enrolment"]["file"])
    for call in manifest["calls"]:
        if call["id"] == demo:
            return os.path.join(cfg.paths.demo_dir, call["file"])
    raise SystemExit(f"unknown demo {demo!r}; available: {', '.join(ids)}")


def default_speaker(cfg: Config) -> Optional[str]:
    manifest = demo_manifest(cfg)
    return manifest["speaker_id"] if manifest else None


# --------------------------------------------------------------------------
# enrol
# --------------------------------------------------------------------------
def cmd_enrol(args, cfg: Config) -> int:
    from sentinel.models.resemblyzer_spk import ResemblyzerSpeakerEncoder

    path = resolve_audio(cfg, args.audio, args.demo)
    speaker_id = args.speaker or default_speaker(cfg)
    if not speaker_id:
        raise SystemExit("--speaker is required")

    import soundfile as sf

    from sentinel.audio.resample import prepare

    pcm, sr_in = sf.read(path, dtype="float32", always_2d=False)
    pcm = prepare(pcm, sr_in, cfg.audio.sample_rate)

    encoder = ResemblyzerSpeakerEncoder(min_rms=cfg.audio.min_embed_rms)
    store = EnrolmentStore(cfg.paths.enrolments_dir)
    meta = store.enrol(speaker_id, pcm, cfg.audio.sample_rate, encoder)

    print(f"enrolled {speaker_id}")
    print(f"  source     : {os.path.relpath(path)}  ({meta['duration_s']}s)")
    print(f"  model      : {meta['model_id']}")
    print(f"  stored     : {meta['embedding_dim']}-dim vector in {cfg.paths.enrolments_dir}")
    print(f"  {meta['privacy']}")
    return 0


def cmd_enrolments(args, cfg: Config) -> int:
    store = EnrolmentStore(cfg.paths.enrolments_dir)
    ids = store.list()
    if not ids:
        print("no enrolments yet")
        return 0
    for speaker_id in ids:
        meta = store.meta(speaker_id) or {}
        print(f"{speaker_id:12s} {meta.get('duration_s', '?')}s  "
              f"{meta.get('embedding_dim', '?')}-dim  {meta.get('created_utc', '')}")
    return 0


# --------------------------------------------------------------------------
# scores — the Day 1 deliverable: a live stream of timestamped risk
# --------------------------------------------------------------------------
def cmd_scores(args, cfg: Config) -> int:
    path = resolve_audio(cfg, args.audio, args.demo)
    speaker_id = args.speaker or default_speaker(cfg)
    paint = _colour(not args.no_colour)

    store = EnrolmentStore(cfg.paths.enrolments_dir)
    ref = store.get(speaker_id) if speaker_id else None
    if ref is None and speaker_id:
        print(paint(YELLOW, f"! {speaker_id} is not enrolled -- speaker risk unavailable."))
        print(paint(DIM, f"  run: python -m sentinel.cli enrol --speaker {speaker_id} "
                         f"--demo enrol"))

    print(paint(DIM, "loading models..."))
    cm, spk = registry.build_models(cfg)
    vad = EnergyVad(cfg.audio)

    source = FileSource(
        path,
        sample_rate=cfg.audio.sample_rate,
        frame_ms=cfg.audio.frame_ms,
        realtime=not args.fast,
    )
    framer = Framer(
        sample_rate=cfg.audio.sample_rate,
        window_s=cfg.audio.window_s,
        hop_s=cfg.audio.hop_s,
    )

    print(f"\n{paint(BOLD, os.path.basename(path))}  {source.duration_s:.1f}s  "
          f"{'replaying at real speed' if not args.fast else 'fast replay'}")
    print(paint(DIM, f"speaker={speaker_id or '-'}  cm={'on' if args.cm else 'off (use --cm)'}"))
    print(paint(DIM, "-" * 62))

    started = time.monotonic()
    n_scored = n_silent = 0
    spk_values, cm_values = [], []

    for frame in source.frames():
        for window in framer.push(frame):
            is_speech, ratio = vad.measure(window.pcm, window.sr)
            t_s = window.t_end_ms / 1000.0

            if not is_speech:
                n_silent += 1
                if not args.quiet:
                    print(f"t={t_s:6.1f}s  {paint(DIM, 'spk_risk=  —   cm_risk=  —   vad=silent')}"
                          f" {paint(DIM, f'({ratio:.0%} voiced)')}")
                continue

            spk_risk = None
            if ref is not None:
                try:
                    spk_risk = spk.risk(ref, spk.embed(window.pcm, window.sr))
                    spk_values.append(spk_risk)
                except SilentAudio:
                    pass

            cm_risk = None
            if args.cm:
                cm_risk = cm.risk(window.pcm, window.sr)
                cm_values.append(cm_risk)

            n_scored += 1
            spk_txt = f"{spk_risk:.3f}" if spk_risk is not None else "  —  "
            cm_txt = f"{cm_risk:.3f}" if cm_risk is not None else "  —  "
            hot = (spk_risk or 0) > 0.5 or (cm_risk or 0) > 0.7
            line = f"t={t_s:6.1f}s  spk_risk={spk_txt}  cm_risk={cm_txt}  vad=speech"
            print(paint(RED, line) if hot else line)

    elapsed = time.monotonic() - started
    print(paint(DIM, "-" * 62))
    print(f"{n_scored} windows scored, {n_silent} silent, "
          f"{elapsed:.1f}s wall clock for {source.duration_s:.1f}s of audio")
    if spk_values:
        print(f"  speaker risk  mean {np.mean(spk_values):.3f}  "
              f"median {np.median(spk_values):.3f}")
    if cm_values:
        print(f"  cm risk       mean {np.mean(cm_values):.3f}  "
              f"median {np.median(cm_values):.3f}")
    if spk_values and cm_values:
        fused = (np.array(spk_values[:len(cm_values)]) + np.array(cm_values[:len(spk_values)])) / 2
        print(f"  fused         mean {fused.mean():.3f}  "
              f"(band [{cfg.decision.low_thr}, {cfg.decision.high_thr}])")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sentinel", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="path to config.yaml")
    sub = ap.add_subparsers(dest="command", required=True)

    def audio_args(p):
        p.add_argument("--audio", help="path to a WAV")
        p.add_argument("--demo", help="demo id from artifacts/demo/manifest.json")
        p.add_argument("--speaker", help="enrolled speaker id")

    p_enrol = sub.add_parser("enrol", help="enrol a speaker from an audio clip")
    audio_args(p_enrol)
    p_enrol.set_defaults(func=cmd_enrol)

    p_list = sub.add_parser("enrolments", help="list enrolled speakers")
    p_list.set_defaults(func=cmd_enrolments)

    p_scores = sub.add_parser("scores", help="replay audio and stream risk scores")
    audio_args(p_scores)
    p_scores.add_argument("--cm", action="store_true",
                          help="also run the countermeasure on every window")
    p_scores.add_argument("--fast", action="store_true",
                          help="replay flat out instead of at real speed")
    p_scores.add_argument("--quiet", action="store_true", help="hide silent windows")
    p_scores.add_argument("--no-colour", action="store_true")
    p_scores.set_defaults(func=cmd_scores)

    return ap


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = Config.load(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
