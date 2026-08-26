"""
The two model protocols, and the one convention the whole system depends on.

SPEC §5, Gap 2 -- stated once, here, and enforced at every adapter boundary:

    EVERY SCORE IN THIS SYSTEM IS A RISK IN [0, 1] WHERE HIGHER = MORE SUSPICIOUS.

The underlying libraries disagree about orientation. Resemblyzer's similarity
returns *higher = same person*; the countermeasure returns *higher = fake*.
run_experiment_v2.py reconciles them inline with `1.0 - sim`, which is fine in a
batch script you read top to bottom and fatal in a streaming system where that
flip can get lost and silently invert a verdict.

So: the adapter does the inversion, once. Nothing downstream ever thinks about
it. test_score_orientation.py guards this forever.
"""
from __future__ import annotations

import numpy as np

try:  # Protocol is 3.8+, but keep the import defensive for the 3.9 venv.
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


@runtime_checkable
class CountermeasureModel(Protocol):
    """Detects synthesis artifacts. Knows nothing about who is speaking."""

    model_id: str

    def risk(self, pcm: np.ndarray, sr: int) -> float:
        """[0,1]; higher = more likely synthetic."""
        ...


@runtime_checkable
class SpeakerEncoder(Protocol):
    """Answers 'is this the enrolled person?' -- our primary signal."""

    model_id: str

    def embed(self, pcm: np.ndarray, sr: int) -> np.ndarray:
        """A speaker embedding. This is the only thing we ever persist."""
        ...

    def risk(self, ref: np.ndarray, test: np.ndarray) -> float:
        """[0,1]; higher = more likely an impostor. Inversion happens here."""
        ...
