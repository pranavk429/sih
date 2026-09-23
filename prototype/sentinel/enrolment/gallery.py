"""
Voice lookup: which enrolled person is speaking, if any?

This is OPEN-SET identification, not the closed "is this the enrolled person?"
question that `models/resemblyzer_spk.py` answers. There is no fixed reference:
every enrolment in the store is a candidate, and the honest answers include "we
don't know".

Three rules, each with a reason:

1. *Similarity is (cos+1)/2 on Resemblyzer embeddings*, which is what
   `detector/src/speaker_id.py::similarity()` returns -- the same orientation and
   the same scale the rest of the system uses. Published Resemblyzer thresholds
   are quoted against raw cosine, so they must be remapped before use: a raw
   0.75 cut is 0.875 here. `config.yaml: lookup.*` carries OUR numbers, which the
   calibration script measures on our data, not borrowed ones.

2. *Acceptance needs a threshold AND a margin over the runner-up.* With a small
   gallery the top-1 score alone is not enough -- two similar voices, or one
   voice and a noisy embedding, can look alike. The margin is the second gate.

3. *A name is only announced after it repeats.* A single window scoring high is
   a coincidence; two consecutive windows is a speaker. `LookupTracker` owns
   that debounce and is deliberately pure so it can be unit-tested without
   models.

What this is NOT: a probability of identity. The UI must present the similarity
and the threshold that produced the decision, never a bare name -- SPEC §12.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class VoiceCandidate:
    speaker_id: str
    display_name: str
    similarity: float  # [0,1], higher = more alike. Same scale as similarity().

    def to_json(self) -> Dict[str, object]:
        return {
            "speaker_id": self.speaker_id,
            "display_name": self.display_name,
            "similarity": round(float(self.similarity), 4),
        }


@dataclass(frozen=True)
class VoiceMatch:
    """One window's lookup result, before debounce."""

    best: Optional[VoiceCandidate]
    runner_up: Optional[VoiceCandidate]
    margin: float
    accepted: bool
    reason: str

    @property
    def best_similarity(self) -> Optional[float]:
        return self.best.similarity if self.best else None

    @property
    def runner_up_similarity(self) -> Optional[float]:
        return self.runner_up.similarity if self.runner_up else None

    def to_json(self) -> Dict[str, object]:
        return {
            "best": self.best.to_json() if self.best else None,
            "runner_up": self.runner_up.to_json() if self.runner_up else None,
            "margin": round(float(self.margin), 4),
            "accepted": bool(self.accepted),
            "reason": self.reason,
        }


class Gallery:
    """The enrolments, loaded once per run and compared in one matrix product."""

    def __init__(
        self,
        ids: List[str],
        display_names: Dict[str, str],
        embeddings: np.ndarray,
        accept_similarity: float,
        min_margin: float,
    ) -> None:
        self.ids = list(ids)
        self.display_names = dict(display_names)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        self.accept_similarity = float(accept_similarity)
        self.min_margin = float(min_margin)
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self._unit = self.embeddings / np.maximum(norms, 1e-9)

    def __len__(self) -> int:
        return len(self.ids)

    def __bool__(self) -> bool:
        return len(self.ids) > 0

    @classmethod
    def load(cls, store, cfg) -> "Gallery":
        """
        Build from an EnrolmentStore. Missing vectors are skipped loudly enough
        to be visible in the run header, not silently dropped.
        """
        ids: List[str] = []
        names: Dict[str, str] = {}
        vectors: List[np.ndarray] = []
        for speaker_id in store.list():
            vector = store.get(speaker_id)
            if vector is None:
                continue
            meta = store.meta(speaker_id) or {}
            ids.append(speaker_id)
            names[speaker_id] = meta.get("display_name") or speaker_id
            vectors.append(np.asarray(vector, dtype=np.float32))
        if not vectors:
            return cls([], {}, np.zeros((0, 0), dtype=np.float32),
                       cfg.accept_similarity, cfg.min_margin)
        return cls(
            ids, names, np.vstack(vectors),
            cfg.accept_similarity, cfg.min_margin,
        )

    def lookup(self, embedding: np.ndarray) -> Optional[VoiceMatch]:
        """
        Compare one embedding against every enrolment.

        Returns None when there is nothing to compare against. Does NOT debounce
        -- that is LookupTracker's job -- so the raw per-window decision is
        visible in the evidence stream.
        """
        if not len(self.ids):
            return None
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-9 or not np.isfinite(vector).all():
            return None
        # detector.similarity() is (cos+1)/2; this reproduces it for the whole
        # gallery in one product rather than 256-dotting per candidate.
        cos = self._unit @ (vector / norm)
        sims = (cos + 1.0) / 2.0

        order = np.argsort(-sims)
        best_idx = int(order[0])
        best = VoiceCandidate(self.ids[best_idx],
                              self.display_names.get(self.ids[best_idx], self.ids[best_idx]),
                              float(sims[best_idx]))
        runner = None
        if len(order) > 1:
            r_idx = int(order[1])
            runner = VoiceCandidate(self.ids[r_idx],
                                    self.display_names.get(self.ids[r_idx], self.ids[r_idx]),
                                    float(sims[r_idx]))
        margin = best.similarity - (runner.similarity if runner else 0.0)

        if best.similarity < self.accept_similarity:
            return VoiceMatch(best, runner, margin, False,
                              f"best {best.similarity:.3f} below accept threshold "
                              f"{self.accept_similarity:.3f}")
        if runner is not None and margin < self.min_margin:
            return VoiceMatch(best, runner, margin, False,
                              f"margin {margin:.3f} over {runner.display_name} below "
                              f"required {self.min_margin:.3f}")
        return VoiceMatch(best, runner, margin, True,
                          f"clears threshold and margin ({margin:.3f})")


class LookupTracker:
    """
    Debounce: a name is announced only after `min_consecutive` accepted windows
    in a row. Pure state machine, no audio, no models.
    """

    def __init__(self, min_consecutive: int = 2) -> None:
        self.min_consecutive = int(min_consecutive)
        self._streak_id: Optional[str] = None
        self._streak = 0
        self.announced_id: Optional[str] = None

    def update(self, match: Optional[VoiceMatch]) -> Dict[str, object]:
        """
        Fold one window's match in. Returns the debounced reading:

            announced_id      the name to show, or None while undecided
            consecutive       accepted windows behind it
            pending_id        the id currently accumulating evidence
        """
        if match is None:
            return self._state(None)
        if match.accepted and match.best is not None:
            if match.best.speaker_id == self._streak_id:
                self._streak += 1
            else:
                self._streak_id = match.best.speaker_id
                self._streak = 1
            if self._streak >= self.min_consecutive:
                self.announced_id = self._streak_id
        else:
            self._streak_id = None
            self._streak = 0
            self.announced_id = None
        return self._state(match)

    def _state(self, match: Optional[VoiceMatch]) -> Dict[str, object]:
        return {
            "announced_id": self.announced_id,
            "consecutive": self._streak,
            "pending_id": self._streak_id,
            "match": match.to_json() if match else None,
        }


def top_pairs(results: List[Tuple[str, float]], k: int = 5) -> List[Tuple[str, float]]:
    """Small helper for scripts: the k highest (id, similarity) pairs."""
    return sorted(results, key=lambda pair: -pair[1])[:k]
