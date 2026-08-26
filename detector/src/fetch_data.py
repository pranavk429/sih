"""
Pull a small pilot slice of ASVspoof2019 LA eval from Hugging Face and cache it
locally as .npy files, so the experiment script doesn't need network access.

PILOT SCALE, NOT FINAL SCALE. This machine has no GPU and 32GB free disk, so we
pull a few hundred utterances -- enough to sanity-check the pipeline and get a
directionally honest number, not enough for a publication-grade EER estimate.
The full-scale run (thousands of utterances, done on Kaggle) is what actually
goes on the September slide -- see notebooks/kaggle_full_run.ipynb.

Critically: we group by speaker_id so every enrolled speaker has BOTH a genuine
enrollment utterance and at least one spoof attack targeting them. Without that
pairing, the enrollment/SASV experiment (step 3) can't run at all.
"""
from __future__ import annotations
import os
import io
import json
import numpy as np
import soundfile as sf
from datasets import load_dataset, Audio
from collections import defaultdict

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "pilot")
N_SPEAKERS = 25            # how many distinct enrolled speakers to pull
MIN_BONAFIDE_PER_SPK = 2   # 1 for enrollment reference, 1+ for genuine test trials
MIN_SPOOF_PER_SPK = 2       # spoof attacks targeting that speaker


def fetch_pilot_set():
    os.makedirs(CACHE_DIR, exist_ok=True)
    manifest_path = os.path.join(CACHE_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        print(f"pilot set already cached at {CACHE_DIR}, skipping download")
        return

    print("streaming ASVspoof2019_LA eval split from Hugging Face...")
    ds = load_dataset(
        "SpeechAntiSpoofingBenchmarks/ASVspoof2019_LA", split="test", streaming=True
    )
    # decode=False sidesteps torchcodec (needs ffmpeg<=7, this box has ffmpeg 8) --
    # we decode the raw bytes ourselves with soundfile below instead.
    ds = ds.cast_column("audio", Audio(decode=False))

    by_speaker = defaultdict(lambda: {"bonafide": [], "spoof": []})
    manifest = []
    n_saved = 0

    for row in ds:
        notes = json.loads(row["notes"])
        spk = notes["speaker_id"]
        label = "bonafide" if row["label"] == 0 else "spoof"
        bucket = by_speaker[spk]

        # stop collecting for speakers who already have enough of this class
        if len(bucket[label]) >= (MIN_BONAFIDE_PER_SPK if label == "bonafide" else MIN_SPOOF_PER_SPK) + 1:
            continue

        fname = f"{notes['utterance_id']}.npy"
        fpath = os.path.join(CACHE_DIR, fname)
        audio, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
        audio = audio.astype(np.float32)
        np.save(fpath, audio)
        bucket[label].append(fname)
        manifest.append({"file": fname, "speaker_id": spk, "label": label, "sr": sr})
        n_saved += 1

        complete_speakers = sum(
            1 for s in by_speaker.values()
            if len(s["bonafide"]) >= MIN_BONAFIDE_PER_SPK and len(s["spoof"]) >= MIN_SPOOF_PER_SPK
        )
        if complete_speakers >= N_SPEAKERS and n_saved % 20 == 0:
            print(f"  {complete_speakers}/{N_SPEAKERS} speakers complete, {n_saved} files saved...")
        if complete_speakers >= N_SPEAKERS:
            break

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"done: {n_saved} files across {len(by_speaker)} speakers -> {CACHE_DIR}")


if __name__ == "__main__":
    fetch_pilot_set()
