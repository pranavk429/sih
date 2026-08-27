"""
The speaker check: "is this the enrolled person?"

This module owns SPEC Gap 2. Resemblyzer's similarity() returns higher = SAME
person. Every score in Sentinel is a risk where higher = MORE SUSPICIOUS. The
inversion happens on the marked line below and nowhere else in the codebase.

It also owns half of Gap 3, and the reality there is worse than the SPEC
predicted. The SPEC expected Resemblyzer to CRASH on a silent window. It does
not. Fed pure digital silence it emits a perfectly well-formed embedding --
unit norm, 103 of 256 components non-zero, structurally indistinguishable from
a real one -- which scores 0.31 risk against a genuine enrolment. That is below
low_thr, so untreated silence would be reported as VERIFIED. The system would
confidently confirm the enrolled speaker while listening to nothing.

A crash would have been the kinder failure. Because the bad embedding cannot be
detected after the fact, the only possible guard is on input energy, and that
is what min_rms below does. The pipeline's VAD is the primary gate; this is the
backstop underneath it. test_vad_silence.py pins the behaviour.
"""
from __future__ import annotations

import numpy as np

from sentinel.models import registry


class SilentAudio(Exception):
    """Not enough voiced audio to embed. Expected during a call, not an error."""


class ResemblyzerSpeakerEncoder:
    """SpeakerEncoder: embeddings for enrolment, impostor risk for verification."""

    model_id = "resemblyzer-voice-encoder-v1"

    def __init__(self, min_rms: float = 0.0015) -> None:
        self._embed, self._similarity = registry.speaker_fns()
        self.min_rms = min_rms

    def embed(self, pcm: np.ndarray, sr: int) -> np.ndarray:
        pcm = np.asarray(pcm, dtype=np.float32)
        if pcm.size == 0:
            raise SilentAudio("empty window")

        # The load-bearing guard. See the module docstring: a silent window
        # produces a confident, wrong answer rather than an error, so it has to
        # be refused before it reaches the encoder.
        level = float(np.sqrt(np.mean(np.square(pcm.astype(np.float64)))))
        if level < self.min_rms:
            raise SilentAudio(
                f"window RMS {level:.5f} below min_embed_rms {self.min_rms:.5f}"
            )

        try:
            emb = self._embed(pcm, sr)
        except (ValueError, IndexError, RuntimeError, AssertionError) as exc:
            # preprocess_wav's own VAD removed everything. AssertionError is a
            # real failure mode too -- webrtcvad/librosa raise it on some
            # edge-case frames, and it must degrade the same way as the rest.
            raise SilentAudio(f"no voiced audio to embed ({exc})") from exc

        emb = np.asarray(emb, dtype=np.float32)
        if not np.isfinite(emb).all():
            raise SilentAudio("encoder produced a non-finite embedding")
        return emb

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
