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


# --------------------------------------------------------------------------
# run — the Day 2 deliverable: quiet, then a trigger, then a verdict
# --------------------------------------------------------------------------
STATE_COLOUR = {
    "MONITORING": DIM,
    "VERIFIED": GREEN,
    "UNCERTAIN": YELLOW,
    "LIKELY_IMPERSONATION": RED,
}


def build_runtime(cfg: Config, with_asr: bool = True):
    """Load everything once. Returns (orchestrator, calibration)."""
    from sentinel.decision.calibration import Calibration
    from sentinel.pipeline.orchestrator import Orchestrator
    from sentinel.trigger.engine import TriggerEngine

    cal = Calibration.load(cfg.models.calibration_path)
    warning = cal.check_band(cfg.decision.low_thr, cfg.decision.high_thr)
    if warning:
        print(f"! {warning}", file=sys.stderr)

    cm, spk = registry.build_models(cfg)
    trigger_engine = TriggerEngine(cfg.trigger, cfg.models)

    factory = None
    if with_asr:
        from sentinel.asr.transcriber import AsrThread, Transcriber

        transcriber = Transcriber(cfg.models)

        def factory(on_utterance):  # noqa: F811
            return AsrThread(
                transcriber, cfg.audio, on_utterance,
                maxsize=cfg.server.asr_queue_size,
            )

    return Orchestrator(cfg, cm, spk, cal, trigger_engine, factory), cal


def cmd_run(args, cfg: Config) -> int:
    import datetime as dt

    from sentinel.evidence.log import EvidenceLog

    path = resolve_audio(cfg, args.audio, args.demo)
    speaker_id = args.speaker or default_speaker(cfg)
    paint = _colour(not args.no_colour)

    manifest = demo_manifest(cfg)
    ground_truth = None
    if manifest and args.demo:
        for call in manifest["calls"]:
            if call["id"] == args.demo:
                ground_truth = call["ground_truth"]

    store = EnrolmentStore(cfg.paths.enrolments_dir)
    ref = store.get(speaker_id) if speaker_id else None

    print(paint(DIM, "loading models..."))
    orchestrator, cal = build_runtime(cfg, with_asr=not args.no_asr)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(cfg.paths.evidence_dir, f"run-{stamp}.jsonl")
    orchestrator.evidence = EvidenceLog(log_path)

    source = FileSource(
        path,
        sample_rate=cfg.audio.sample_rate,
        frame_ms=cfg.audio.frame_ms,
        realtime=not args.fast,
    )

    print()
    print(paint(BOLD, f"  {os.path.basename(path)}  ·  {source.duration_s:.1f}s"))
    print(paint(DIM, "  Simulated live call — recorded audio streamed in real time."))
    print(paint(DIM, f"  calibration {cal.calibration_id} · {cal.dataset} · "
                     f"EER {cal.eer * 100:.1f}% on {cal.n_test_trials} trials"))
    print(paint(DIM, f"  mode={args.mode}  speaker={speaker_id or '-'}  "
                     f"ground truth={ground_truth or 'unknown'}"))
    print(paint(DIM, "  " + "-" * 68))

    last_state = [None]

    def on_event(event):
        kind = event.get("type")
        if kind == "utterance":
            tag = paint(YELLOW, "[SCRIPTED]") if event["scripted"] else "          "
            print(f"  {event['t_end_ms'] / 1000:6.1f}s {tag} {event['text']}")
        elif kind == "trigger":
            print()
            print(paint(RED + BOLD, f"  {event['t_ms'] / 1000:6.1f}s  "
                                    f"{event['description']}"))
            print()
        elif kind == "verdict":
            state = event["state"]
            if state == last_state[0]:
                return
            last_state[0] = state
            colour = STATE_COLOUR[state]
            print(paint(colour + BOLD,
                        f"  {event['t_ms'] / 1000:6.1f}s  ── {state} ── "
                        f"risk {event['risk']:.3f}  confidence {event['confidence']:.2f}"))
            for reason in event["reasons"]:
                print(paint(DIM, f"          · {reason}"))

    stats = orchestrator.run(
        source,
        reference_embedding=ref,
        speaker_id=speaker_id,
        mode=args.mode,
        ground_truth=ground_truth,
        on_event=on_event,
    )

    verdict = stats.verdict
    colour = STATE_COLOUR[verdict.state]
    print(paint(DIM, "  " + "-" * 68))
    print()
    print(paint(colour + BOLD, f"  FINAL: {verdict.state}   risk {verdict.risk:.3f}   "
                               f"confidence {verdict.confidence:.2f}"))
    for reason in verdict.reasons:
        print(paint(DIM, f"    · {reason}"))
    print()
    print(f"  recommended action: {verdict.recommended_action}")
    if verdict.segments:
        print(f"\n  suspicious segments ({len(verdict.segments)}):")
        for seg in verdict.segments[:5]:
            tag = "" if seg.n_inputs >= 2 else "  (single-signal, not a true fusion)"
            print(f"    {seg.t_start_ms / 1000:6.1f}-{seg.t_end_ms / 1000:5.1f}s  "
                  f"fused {seg.fused_risk:.3f}  "
                  f"cm {seg.cm_risk if seg.cm_risk is None else round(seg.cm_risk, 3)}  "
                  f"spk {seg.speaker_risk if seg.speaker_risk is None else round(seg.speaker_risk, 3)}"
                  f"{tag}")
    print()
    print(paint(DIM, f"  {stats.windows_total} windows "
                     f"({stats.windows_scored} scored, {stats.windows_silent} silent, "
                     f"{stats.windows_deep} deep) · {stats.utterances} utterances · "
                     f"{stats.triggers} triggers"))
    print(paint(DIM, f"  alerts {stats.alerts}"
                     + (f" · FALSE ALARMS {stats.false_alarms}" if ground_truth == "bonafide" else "")
                     + f" · max pipeline lag {stats.max_lag_ms} ms"))
    print(paint(DIM, f"  {stats.wall_s:.1f}s wall clock for {stats.stream_s:.1f}s of audio"))
    print(paint(DIM, f"  evidence: {os.path.relpath(log_path)}"))
    return 0


def cmd_serve(args, cfg: Config) -> int:
    from sentinel.server.app import serve

    host = args.host or cfg.server.host
    port = args.port or cfg.server.port
    print("loading models (once, so the demo has no pause in the middle)...")
    print(f"\n  Sentinel UI:  http://{host}:{port}\n")
    serve(cfg, host=host, port=port, with_asr=not args.no_asr)
    return 0


def cmd_verify(args, cfg: Config) -> int:
    from sentinel.evidence.log import verify

    path = args.log
    if path is None:
        logs = sorted(
            os.path.join(cfg.paths.evidence_dir, f)
            for f in os.listdir(cfg.paths.evidence_dir)
            if f.endswith(".jsonl")
        ) if os.path.isdir(cfg.paths.evidence_dir) else []
        if not logs:
            raise SystemExit("no evidence logs found")
        path = logs[-1]

    ok, problems = verify(path)
    print(f"{os.path.relpath(path)}")
    if ok:
        print("  hash chain intact")
        return 0
    print("  CHAIN BROKEN:")
    for problem in problems:
        print(f"    {problem}")
    return 1


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

    p_run = sub.add_parser("run", help="run the full pipeline on a call")
    audio_args(p_run)
    p_run.add_argument("--mode", choices=("triggered", "always_on"), default=None,
                       help="triggered = Sentinel; always_on = the naive design")
    p_run.add_argument("--console", action="store_true",
                       help="accepted for symmetry; run always prints to console")
    p_run.add_argument("--fast", action="store_true",
                       help="replay flat out instead of at real speed")
    p_run.add_argument("--no-asr", action="store_true",
                       help="skip transcription; scripted overlay still fires")
    p_run.add_argument("--no-colour", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_serve = sub.add_parser("serve", help="run the web UI")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--no-asr", action="store_true",
                         help="skip transcription; scripted overlay still fires")
    p_serve.set_defaults(func=cmd_serve)

    p_verify = sub.add_parser("verify", help="check an evidence log's hash chain")
    p_verify.add_argument("--log", default=None, help="defaults to the newest log")
    p_verify.set_defaults(func=cmd_verify)

    return ap


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = Config.load(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
