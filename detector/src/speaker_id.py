"""
Speaker verification: "does this voice match the enrolled reference?"

Uses Resemblyzer (MIT licensed) — a lightweight speaker encoder. This is a
stand-in for a production-grade ECAPA-TDNN embedding, but it's enough to prove
the enrollment thesis: fusing a speaker-similarity score with the CM score
should sharply cut errors versus CM alone.
"""
from __future__ import annotations
import numpy as np
from resemblyzer import VoiceEncoder

_encoder = None


def _get_encoder() -> VoiceEncoder:
    global _encoder
    if _encoder is None:
        _encoder = VoiceEncoder()
    return _encoder


def embed(audio: np.ndarray, sr: int) -> np.ndarray:
    """Resemblyzer's preprocess_wav resamples internally; pass raw audio + its sr."""
    from resemblyzer import preprocess_wav
    wav = preprocess_wav(audio, source_sr=sr)
    return _get_encoder().embed_utterance(wav)


def similarity(ref_embedding: np.ndarray, test_embedding: np.ndarray) -> float:
    """Cosine similarity, mapped to [0, 1]. Higher = more likely the same speaker."""
    cos = float(np.dot(ref_embedding, test_embedding) /
                (np.linalg.norm(ref_embedding) * np.linalg.norm(test_embedding) + 1e-9))
    return (cos + 1.0) / 2.0
