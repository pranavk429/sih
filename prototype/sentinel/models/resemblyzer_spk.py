"""
The speaker check: "is this the enrolled person?"

This module owns SPEC Gap 2. Resemblyzer's similarity() returns higher = SAME
person. Every score in Sentinel is a risk where higher = MORE SUSPICIOUS. The
inversion happens on the marked line below and nowhere else in the codebase.

It also owns half of Gap 3. Resemblyzer's preprocess_wav runs its own VAD and
returns an empty array on a silent window; embed_utterance then raises. A
streaming system hits silent windows constantly -- pauses, hold music, line
noise -- so embed() raises a typed SilentAudio rather than letting an opaque
numpy error escape into the pipeline loop.
"""
from __future__ import annotations

import numpy as np

from sentinel.models import registry


class SilentAudio(Exception):
    """Not enough voiced audio to embed. Expected during a call, not an error."""


class ResemblyzerSpeakerEncoder:
    """SpeakerEncoder: embeddings for enrolment, impostor risk for verification."""

    model_id = "resemblyzer-voice-encoder-v1"

    def __init__(self) -> None:
        self._embed, self._similarity = registry.speaker_fns()

    def embed(self, pcm: np.ndarray, sr: int) -> np.ndarray:
        pcm = np.asarray(pcm, dtype=np.float32)
        try:
            return self._embed(pcm, sr)
        except (ValueError, IndexError, RuntimeError) as exc:
            # preprocess_wav VAD'd the whole window away.
            raise SilentAudio(f"no voiced audio to embed ({exc})") from exc

    def similarity(self, ref: np.ndarray, test: np.ndarray) -> float:
        """[0,1]; higher = same speaker. Exposed for tests and debugging only."""
        return float(self._similarity(ref, test))

    def risk(self, ref: np.ndarray, test: np.ndarray) -> float:
        """
        [0,1]; higher = more likely an impostor.

        >>> THE ONE INVERSION IN THE SYSTEM. SPEC Gap 2. <<<
        Do not add another one downstream. If a verdict looks inverted, this
        line and test_score_orientation.py are where to look.
        """
        return float(np.clip(1.0 - self.similarity(ref, test), 0.0, 1.0))
