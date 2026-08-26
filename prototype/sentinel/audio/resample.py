"""
Get everything to 16 kHz mono float32 before it reaches a model.

Both models require exactly 16 kHz -- ProbeBackbone raises on anything else
rather than resampling silently, which is the right call. This module is where
that conversion happens, once, at the audio boundary.

Linear interpolation is deliberate. soxr/librosa would be higher quality, but
the demo audio is already Opus-8kbps narrowband -- resampler quality is far
below the noise floor of what we're measuring, and every extra dependency is
another thing that can fail to import on stage.
"""
from __future__ import annotations

import numpy as np


def to_mono(pcm: np.ndarray) -> np.ndarray:
    """Average channels. Sentinel is single-channel end to end."""
    pcm = np.asarray(pcm)
    if pcm.ndim == 1:
        return pcm.astype(np.float32, copy=False)
    if pcm.ndim == 2:
        return pcm.mean(axis=1).astype(np.float32)
    raise ValueError(f"expected 1-D or 2-D audio, got shape {pcm.shape}")


def resample(pcm: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Linear-interpolation resample. No-op when the rates already match."""
    pcm = np.asarray(pcm, dtype=np.float32)
    if sr_in == sr_out or pcm.size == 0:
        return pcm
    n_out = int(round(len(pcm) * sr_out / float(sr_in)))
    if n_out <= 1:
        return np.zeros(max(n_out, 0), dtype=np.float32)
    src = np.linspace(0.0, len(pcm) - 1.0, num=n_out, dtype=np.float64)
    return np.interp(src, np.arange(len(pcm), dtype=np.float64), pcm).astype(np.float32)


def prepare(pcm: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """mono + 16 kHz + float32, in one call. The only entry point you need."""
    return resample(to_mono(pcm), sr_in, sr_out)
