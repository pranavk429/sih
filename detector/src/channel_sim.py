"""
Telephony channel simulator.

Takes clean 16kHz audio and degrades it the way a real Indian phone call would:
  - G.711 mu-law: the codec used on PSTN / bank call-center trunks (8kHz, narrowband)
  - Opus @ 8kbps: the codec used on WhatsApp / VoIP / most modern mobile data calls
  - Packet loss: random short dropouts, simulating a shaky mobile network

Requires ffmpeg on PATH (macOS: brew install ffmpeg).
"""
from __future__ import annotations
import subprocess
import tempfile
import os
import random
import numpy as np
import soundfile as sf


def _run_ffmpeg(args):
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error"] + args,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()}")


def apply_g711(audio: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """Round-trip through G.711 mu-law at 8kHz, as a PSTN/bank call-center trunk would."""
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.wav")
        dst = os.path.join(td, "out.wav")
        sf.write(src, audio, sr)
        _run_ffmpeg(["-i", src, "-ar", "8000", "-ac", "1", "-c:a", "pcm_mulaw", dst])
        out, out_sr = sf.read(dst)
        return out.astype(np.float32), out_sr


def apply_opus_lowrate(audio: np.ndarray, sr: int, bitrate_kbps: int = 8) -> tuple[np.ndarray, int]:
    """Round-trip through low-bitrate Opus, as WhatsApp/mobile VoIP would."""
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.wav")
        enc = os.path.join(td, "enc.opus")
        dst = os.path.join(td, "out.wav")
        sf.write(src, audio, sr)
        _run_ffmpeg(["-i", src, "-ar", "16000", "-ac", "1", "-c:a", "libopus",
                     "-b:a", f"{bitrate_kbps}k", enc])
        # Opus's internal rate is 48kHz; force decode back down to 16kHz or
        # the CM model (which expects exactly 16kHz) will reject the output.
        _run_ffmpeg(["-i", enc, "-ar", "16000", dst])
        out, out_sr = sf.read(dst)
        return out.astype(np.float32), out_sr


def apply_packet_loss(audio: np.ndarray, sr: int, loss_rate: float = 0.05,
                       chunk_ms: int = 20, seed: int | None = None) -> np.ndarray:
    """Zero out random ~20ms chunks to simulate dropped packets on a mobile network."""
    rng = random.Random(seed)
    chunk = int(sr * chunk_ms / 1000)
    out = audio.copy()
    for start in range(0, len(out), chunk):
        if rng.random() < loss_rate:
            out[start:start + chunk] = 0.0
    return out


def degrade(audio: np.ndarray, sr: int, profile: str = "mobile_voip",
            seed: int | None = None) -> tuple[np.ndarray, int]:
    """
    Apply a full degradation profile.
      - 'pstn'        : G.711 only (bank call center / landline)
      - 'mobile_voip' : Opus 8kbps + 5% packet loss (WhatsApp/mobile call, average conditions)
      - 'mobile_poor' : Opus 6kbps + 12% packet loss (weak signal)
    """
    if profile == "pstn":
        out, out_sr = apply_g711(audio, sr)
    elif profile == "mobile_voip":
        out, out_sr = apply_opus_lowrate(audio, sr, bitrate_kbps=8)
        out = apply_packet_loss(out, out_sr, loss_rate=0.05, seed=seed)
    elif profile == "mobile_poor":
        out, out_sr = apply_opus_lowrate(audio, sr, bitrate_kbps=6)
        out = apply_packet_loss(out, out_sr, loss_rate=0.12, seed=seed)
    else:
        raise ValueError(f"unknown profile: {profile}")
    return out, out_sr
