"""Shared fixtures. Models are session-scoped -- loading them is the slow part."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel.config import Config  # noqa: E402


@pytest.fixture(scope="session")
def cfg() -> Config:
    return Config.load()


@pytest.fixture(scope="session")
def demo_dir(cfg) -> str:
    path = cfg.paths.demo_dir
    if not os.path.exists(os.path.join(path, "manifest.json")):
        pytest.skip("demo audio missing -- run scripts/make_demo_calls.py")
    return path


@pytest.fixture(scope="session")
def speaker_encoder(cfg):
    from sentinel.models.resemblyzer_spk import ResemblyzerSpeakerEncoder

    return ResemblyzerSpeakerEncoder(min_rms=cfg.audio.min_embed_rms)


@pytest.fixture(scope="session")
def countermeasure(cfg):
    from sentinel.models.probe_cm import ProbeCountermeasure

    if not os.path.exists(cfg.models.probe_head_path):
        pytest.skip("probe head missing -- run scripts/fit_probe.py")
    return ProbeCountermeasure(cfg.models.probe_head_path, cfg.models.device)


def read_wav(path: str):
    pcm, sr = sf.read(path, dtype="float32", always_2d=False)
    return np.asarray(pcm, dtype=np.float32), sr


def tone(seconds: float, sr: int = 16000, freq: float = 220.0, amp: float = 0.2):
    """A voiced-looking signal: loud enough to clear the VAD floor."""
    t = np.arange(int(seconds * sr), dtype=np.float32) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence(seconds: float, sr: int = 16000, noise_rms: float = 0.0):
    n = int(seconds * sr)
    if noise_rms <= 0:
        return np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(7)
    return rng.normal(0.0, noise_rms, n).astype(np.float32)
