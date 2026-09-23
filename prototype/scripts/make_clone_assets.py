"""
Build the synthetic-voice assets the clone demo plays. Build-time only.

This script is NOT part of the running system: nothing under `sentinel/` imports
it, and it is never invoked during a demo. It exists so that whoever prepares
the demo can produce a labelled synthetic WAV without hand-editing a manifest.

Two generators it supports today:

    --say                      macOS `say`, a system TTS voice. It is synthetic
                               speech but NOT a clone of any enrolled person --
                               useful as a "does the countermeasure notice
                               machine speech at all" probe.

    --from-file <wav>          a clone generated elsewhere (XTTS, OpenVoice, an
                               online tool). The script records the provenance
                               you give it; it does not generate the clone.

A real clone of a consenting person is Tier A/B in PLAN-LIVE.md §2 and is
generated once, off the critical path. Whichever generator produced it, the
provenance block written here is what the UI and the clone report read, so an
unlabelled synthetic asset cannot slip into the demo.

    ../detector/venv/bin/python scripts/make_clone_assets.py --say
    ../detector/venv/bin/python scripts/make_clone_assets.py \\
        --from-file ~/xtts-out.wav --id clone-priya --source-speaker "Priya" \\
        --generator xtts-v2 --consent "written consent, 2026-09-20"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel.config import ROOT  # noqa: E402

CLONE_DIR = os.path.join(ROOT, "artifacts", "clones")
MANIFEST = os.path.join(CLONE_DIR, "manifest.json")

FRAUD_SCRIPT = (
    "Sir, this is regarding the vendor settlement we discussed. "
    "I need you to transfer two crore to this account tonight. "
    "Please do not call the branch, there is no time for the usual approval."
)

DEFAULT_VOICES = ("Samantha", "Daniel", "Karen")


def _load_manifest() -> dict:
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            return json.load(fh)
    return {"created_utc": None, "assets": []}


def _save_manifest(manifest: dict) -> None:
    manifest["updated_utc"] = dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0).isoformat()
    # `_load_manifest` seeds created_utc as None, so setdefault would keep the
    # None. The first save is what dates the collection.
    if not manifest.get("created_utc"):
        manifest["created_utc"] = manifest["updated_utc"]
    os.makedirs(CLONE_DIR, exist_ok=True)
    with open(MANIFEST, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")


def _add(manifest: dict, entry: dict) -> None:
    manifest["assets"] = [a for a in manifest["assets"] if a["id"] != entry["id"]]
    manifest["assets"].append(entry)
    manifest["assets"].sort(key=lambda a: a["id"])


def make_say(voice: str, text: str, manifest: dict) -> str:
    if shutil.which("say") is None:
        raise SystemExit("`say` is not on PATH -- this generator is macOS only")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is not on PATH; it converts say's output to 16 kHz WAV")

    os.makedirs(CLONE_DIR, exist_ok=True)
    asset_id = f"say-{voice.lower()}"
    out_path = os.path.join(CLONE_DIR, f"{asset_id}.wav")
    aiff = out_path + ".aiff"

    subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", aiff,
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out_path],
        check=True,
    )
    os.remove(aiff)

    _add(manifest, {
        "id": asset_id,
        "file": os.path.basename(out_path),
        "generator": "macOS say",
        "generator_detail": f"system TTS voice '{voice}'",
        "source_speaker": None,
        "consent": "not applicable -- a system voice, not a person",
        "text": text,
        "ground_truth": "synthetic_tts",
        "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "note": "Synthetic speech, but not a clone of any enrolled person. "
                "Report it with make_clone_report.py before demoing it.",
    })
    return out_path


def add_from_file(args, manifest: dict) -> str:
    if not os.path.exists(args.from_file):
        raise SystemExit(f"no such file: {args.from_file}")
    if not args.source_speaker or not args.consent:
        raise SystemExit(
            "--source-speaker and --consent are required for a clone asset. "
            "An asset whose provenance cannot be stated cannot be demoed."
        )
    os.makedirs(CLONE_DIR, exist_ok=True)
    asset_id = args.id or f"clone-{args.source_speaker.lower().replace(' ', '-')}"
    out_path = os.path.join(CLONE_DIR, f"{asset_id}.wav")

    # Normalise to 16 kHz mono PCM16 so the report and the pipeline agree.
    if args.from_file != out_path:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", args.from_file,
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out_path],
            check=True,
        )

    _add(manifest, {
        "id": asset_id,
        "file": os.path.basename(out_path),
        "generator": args.generator or "unknown",
        "generator_detail": args.generator_detail or "",
        "source_speaker": args.source_speaker,
        "consent": args.consent,
        "text": args.text or "",
        "ground_truth": "clone",
        "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "note": "Generated off the critical path. Report it with "
                "make_clone_report.py before demoing it.",
    })
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--say", action="store_true",
                        help="generate macOS say assets for the default voices")
    parser.add_argument("--voices", default=",".join(DEFAULT_VOICES),
                        help="comma-separated say voices (default: %(default)s)")
    parser.add_argument("--text", default=FRAUD_SCRIPT)
    parser.add_argument("--from-file", default=None,
                        help="add a clone generated elsewhere")
    parser.add_argument("--id", default=None)
    parser.add_argument("--source-speaker", default=None)
    parser.add_argument("--generator", default=None)
    parser.add_argument("--generator-detail", default=None)
    parser.add_argument("--consent", default=None)
    args = parser.parse_args()

    if not args.say and not args.from_file:
        parser.print_help()
        return 2

    manifest = _load_manifest()
    written = []
    if args.say:
        for voice in [v.strip() for v in args.voices.split(",") if v.strip()]:
            try:
                written.append(make_say(voice, args.text, manifest))
            except subprocess.CalledProcessError as exc:
                print(f"  say failed for {voice}: {exc}")
    if args.from_file:
        written.append(add_from_file(args, manifest))

    _save_manifest(manifest)
    print(f"\nwrote {len(written)} asset(s) to {os.path.relpath(CLONE_DIR, ROOT)}:")
    for path in written:
        print(f"  {os.path.basename(path)}")
    print(f"manifest: {os.path.relpath(MANIFEST, ROOT)}")
    print("\nNext: measure them before anyone claims they are caught --")
    print("  ../detector/venv/bin/python scripts/make_clone_report.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
