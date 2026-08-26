"""
Enrolment: feature vectors only. Never audio. Not once, not temporarily.

SPEC §7.5: "Privacy is a code property, not a slide claim." Slide 2 says we do
not store customer voice recordings. This module is the only thing that makes
that sentence true, and tests/test_privacy.py walks the whole output tree after
a full run and fails if any audio-bearing file exists.

What gets written per speaker:
    <id>.npy    a 256-float Resemblyzer embedding
    <id>.json   created_utc, model_id, duration_s, sample_rate, n_samples

The embedding is not reversible into speech. The JSON records the duration of
the enrolment audio but not the audio, which is the honest line: we keep enough
to verify a voice and audit the enrolment, and nothing you could play back.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np

SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class EnrolmentStore:
    """Persisted speaker embeddings, keyed by speaker id."""

    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def _paths(self, speaker_id: str):
        if not SAFE_ID.match(speaker_id):
            raise ValueError(
                f"invalid speaker id {speaker_id!r}: "
                "use letters, digits, and _ . : - only (max 64 chars)"
            )
        base = os.path.join(self.root, speaker_id)
        return base + ".npy", base + ".json"

    def enrol(
        self,
        speaker_id: str,
        pcm: np.ndarray,
        sr: int,
        encoder: Any,
    ) -> Dict[str, Any]:
        """
        Embed and persist. `pcm` is used and dropped -- it is never written out.
        """
        pcm = np.asarray(pcm, dtype=np.float32)
        embedding = np.asarray(encoder.embed(pcm, sr), dtype=np.float32)
        emb_path, meta_path = self._paths(speaker_id)

        meta = {
            "speaker_id": speaker_id,
            "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "model_id": getattr(encoder, "model_id", "unknown"),
            "embedding_dim": int(embedding.shape[0]),
            "duration_s": round(len(pcm) / float(sr), 3),
            "sample_rate": int(sr),
            "n_samples": int(len(pcm)),
            "privacy": "feature vector only; no audio is stored by this system",
        }
        np.save(emb_path, embedding)
        with open(meta_path, "w") as fh:
            json.dump(meta, fh, indent=2)
        return meta

    def get(self, speaker_id: str) -> Optional[np.ndarray]:
        emb_path, _ = self._paths(speaker_id)
        if not os.path.exists(emb_path):
            return None
        return np.load(emb_path).astype(np.float32)

    def meta(self, speaker_id: str) -> Optional[Dict[str, Any]]:
        _, meta_path = self._paths(speaker_id)
        if not os.path.exists(meta_path):
            return None
        with open(meta_path) as fh:
            return json.load(fh)

    def list(self) -> List[str]:
        if not os.path.isdir(self.root):
            return []
        return sorted(
            os.path.splitext(f)[0] for f in os.listdir(self.root) if f.endswith(".npy")
        )

    def remove(self, speaker_id: str) -> bool:
        removed = False
        for path in self._paths(speaker_id):
            if os.path.exists(path):
                os.remove(path)
                removed = True
        return removed
