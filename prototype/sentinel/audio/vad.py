"""
Is there speech in this window? Closes SPEC Gap 3.

This is a crash guard, not a research problem. Resemblyzer's preprocess_wav runs
its own VAD internally and can return an empty array on a silent window;
embed_utterance then raises on it. A streaming system hits silent windows
constantly -- pauses between sentences, hold, line noise, the gaps our own demo
audio deliberately contains. Without this gate the pipeline dies partway through
a call, on stage.

The rule: a frame is voiced if its RMS clears a floor, and a window is speech if
enough of its frames are voiced. Two numbers, both in config.yaml, deliberately
simple. Energy VAD is wrong sometimes -- it will call loud line noise "speech" --
but the cost of that is one wasted embedding, whereas the cost of the opposite
error is a fabricated score on silence.

Windows that fail this gate produce a RiskScore with status SILENT. Not a crash,
and not a number we made up.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from sentinel.config import AudioConfig


def rms(pcm: np.ndarray) -> float:
    pcm = np.asarray(pcm, dtype=np.float32)
    if pcm.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(pcm), dtype=np.float64)))


def voiced_ratio(pcm: np.ndarray, sr: int, frame_ms: int, floor: float) -> float:
    """Fraction of short frames whose RMS clears the floor."""
    pcm = np.asarray(pcm, dtype=np.float32)
    n = max(1, int(sr * frame_ms / 1000))
    if pcm.size < n:
        return 1.0 if rms(pcm) >= floor else 0.0
    usable = (len(pcm) // n) * n
    frames = pcm[:usable].reshape(-1, n)
    energies = np.sqrt(np.mean(np.square(frames.astype(np.float64)), axis=1))
    return float(np.mean(energies >= floor))


class EnergyVad:
    """Config-driven energy gate. Returns (is_speech, voiced_ratio)."""

    def __init__(self, cfg: AudioConfig) -> None:
        self.sr = cfg.sample_rate
        self.frame_ms = cfg.frame_ms
        self.floor = cfg.vad_rms_floor
        self.min_ratio = cfg.vad_min_voiced_ratio

    def measure(self, pcm: np.ndarray, sr: int) -> Tuple[bool, float]:
        ratio = voiced_ratio(pcm, sr, self.frame_ms, self.floor)
        return ratio >= self.min_ratio, ratio

    def is_speech(self, pcm: np.ndarray, sr: int) -> bool:
        return self.measure(pcm, sr)[0]
